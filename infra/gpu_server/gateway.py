"""GPU 서버 관문: 터널 밖(Render)에서 들어오는 요청을 검사해 vLLM으로 전달한다.

- API 키(~/llm-serve/.api_key)가 맞아야 통과. vLLM은 /v1/... 만 키를 검사하므로 vLLM 포트를 직접 내보내지 않는다.
- 허용: POST /v1/embeddings → BGE-M3(8101), POST /v1/chat/completions → Qwen(8100),
  POST /v1/rerank → 재정렬 bge-reranker-v2-m3(8102, start_reranker.sh), GET /health
  /v1/chat/completions는 모델 이름으로 나눈다: qwen3-32b → 답변(8100), qwen3-8b → 답변 전 판정(8103, start_gate.sh)
- Cloudflare 임시 터널은 SSE를 지원하지 않으므로, 스트리밍 답변은 SSE 대신 한 줄에 JSON 하나(NDJSON)로 보낸다.
실행: start_gateway.sh (tmux 세션 gateway, 127.0.0.1:8200)
"""
import hmac
import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

KEY = os.getenv("GATEWAY_API_KEY") or (Path.home() / "llm-serve/.api_key").read_text().strip()
UPSTREAM = {  # (주소, 모델 이름) → vLLM
    ("/v1/embeddings", "bge-m3"): os.getenv("BGE_URL", "http://127.0.0.1:8101"),
    ("/v1/chat/completions", "qwen3-32b"): os.getenv("QWEN_URL", "http://127.0.0.1:8100"),
    ("/v1/chat/completions", "qwen3-8b"): os.getenv("GATE_URL", "http://127.0.0.1:8103"),
    ("/v1/rerank", "bge-reranker"): os.getenv("RERANKER_URL", "http://127.0.0.1:8102"),
}
MAX_BODY = 1_000_000  # 근거 5개 + 대화를 넣어도 수십 KB. 큰 요청으로 GPU를 붙잡지 못하게 막는다
MAX_TOKENS = 2048  # 답변 길이 상한
MAX_DOCUMENTS = 32  # 재정렬 한 번에 받는 후보 수 상한 (보통 10개)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # 문서 페이지도 열지 않는다
client = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5))


def sse_to_ndjson(line: str) -> str | None:
    """vLLM SSE 한 줄 → NDJSON 한 줄. 'data: [DONE]'과 빈 줄은 버린다"""
    if not line.startswith("data:"):
        return None
    data = line.removeprefix("data:").strip()
    return None if data in ("", "[DONE]") else data + "\n"


def check_body(path: str, body: dict) -> dict:
    if (path, body.get("model")) not in UPSTREAM:
        allowed = ", ".join(m for p, m in UPSTREAM if p == path)
        raise HTTPException(400, f"model은 {allowed}만 허용")
    if path == "/v1/chat/completions":
        body["max_tokens"] = min(int(body.get("max_tokens") or MAX_TOKENS), MAX_TOKENS)
    if path == "/v1/rerank" and not (isinstance(body.get("documents"), list) and 0 < len(body["documents"]) <= MAX_DOCUMENTS):
        raise HTTPException(400, f"documents는 1~{MAX_DOCUMENTS}개")
    return body


@app.get("/health")
async def health():
    """키 없이 열어 두되, 살아 있는지만 알려 준다. 재정렬·판정은 꺼져도 답변은 되므로(벡터 순서로, 판정 없이) 상태 코드에 넣지 않는다"""
    status = {}
    for name, key in (("bge", ("/v1/embeddings", "bge-m3")), ("qwen", ("/v1/chat/completions", "qwen3-32b")),
                      ("reranker", ("/v1/rerank", "bge-reranker")), ("gate", ("/v1/chat/completions", "qwen3-8b"))):
        try:
            status[name] = (await client.get(f"{UPSTREAM[key]}/health", timeout=3)).status_code == 200
        except httpx.HTTPError:
            status[name] = False
    return JSONResponse(status, status_code=200 if status["bge"] and status["qwen"] else 503)


@app.post("/v1/embeddings")
@app.post("/v1/chat/completions")
@app.post("/v1/rerank")
async def forward(request: Request):
    if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {KEY}"):
        raise HTTPException(401, "API 키가 필요합니다")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "요청이 너무 큽니다")
    try:
        body = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "JSON 형식이 아닙니다")
    path = request.url.path
    body = check_body(path, body)
    upstream = httpx.Request("POST", UPSTREAM[path, body["model"]] + path, json=body, headers={"Authorization": f"Bearer {KEY}"})

    if not body.get("stream"):
        r = await client.send(upstream)
        return Response(r.content, status_code=r.status_code, media_type="application/json")

    r = await client.send(upstream, stream=True)
    if r.status_code != 200:  # vLLM 오류(예: 입력이 너무 김)는 그대로 전달
        content = await r.aread()
        await r.aclose()
        return Response(content, status_code=r.status_code, media_type="application/json")

    async def lines():
        try:
            async for line in r.aiter_lines():
                if (out := sse_to_ndjson(line)) is not None:
                    yield out
        finally:
            await r.aclose()  # Render가 끊으면 vLLM 생성도 멈춘다

    # 버퍼링하지 말라는 표시: 프록시·터널이 모아 보내지 않게
    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
