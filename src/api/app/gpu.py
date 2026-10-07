"""GPU 서버(관문) 호출: 질문 임베딩(BGE-M3), 검색 후보 재정렬(bge-reranker-v2-m3), 답변 생성(Qwen3-32B) 스트리밍.

관문(infra/gpu_server/gateway.py)은 Cloudflare 임시 터널 때문에 스트리밍을 SSE 대신 NDJSON(한 줄에 JSON 하나)으로 보낸다.
환경변수: GPU_URL(터널 주소), GPU_API_KEY(GPU 서버 ~/llm-serve/.api_key 내용)
"""
import asyncio
import json
import os
from typing import AsyncIterator
import weakref

import httpx

EMBED_MODEL = "bge-m3"
LLM_MODEL = "qwen3-32b"
RERANK_MODEL = "bge-reranker"
# 연결 5초, 다음 조각까지 최대 60초 (긴 근거를 읽는 첫 조각이 가장 오래 걸린다)
TIMEOUT = httpx.Timeout(60, connect=5)


class GpuError(RuntimeError):
    pass


class GpuConfigError(GpuError):
    """설정 누락 — 서버가 꺼진 것과 달리 배포 실수이므로 안내로 덮지 않고 오류로 드러낸다"""


# 연결 재사용: 요청마다 새로 연결하면 터널(https) 연결 준비를 매번 다시 한다. 이벤트 루프마다 하나씩 둔다
_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = weakref.WeakKeyDictionary()


def _client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = _clients[loop] = httpx.AsyncClient(timeout=TIMEOUT)
    return client


def _config() -> tuple[str, dict]:
    url, key = os.getenv("GPU_URL", "").rstrip("/"), os.getenv("GPU_API_KEY", "")
    if not url or not key:
        raise GpuConfigError("GPU_URL·GPU_API_KEY가 설정되지 않았습니다")
    return url, {"Authorization": f"Bearer {key}"}


async def embed(text: str) -> list[float]:
    url, headers = _config()
    r = await _client().post(f"{url}/v1/embeddings", headers=headers, json={"model": EMBED_MODEL, "input": [text]})
    if r.status_code != 200:
        raise GpuError(f"임베딩 실패 {r.status_code}")
    return r.json()["data"][0]["embedding"]


async def chat_stream(messages: list[dict], max_tokens: int, temperature: float) -> AsyncIterator[str]:
    """답변 조각(content)을 차례로 내놓는다. Qwen3의 생각 과정 출력은 끈다."""
    url, headers = _config()
    body = {"model": LLM_MODEL, "messages": messages, "stream": True, "max_tokens": max_tokens,
            "temperature": temperature, "chat_template_kwargs": {"enable_thinking": False}}
    async with _client().stream("POST", f"{url}/v1/chat/completions", headers=headers, json=body) as r:
        if r.status_code != 200:
            raise GpuError(f"생성 실패 {r.status_code}")
        async for line in r.aiter_lines():
            if not line.strip():
                continue
            choice = json.loads(line)["choices"][0]
            if text := choice.get("delta", {}).get("content"):
                yield text


async def rerank(query: str, documents: list[str], timeout: float, truncate: int | None = None) -> list[float]:
    """질문-문서 쌍 관련도(0~1, 문서 순서대로). 재정렬은 실패해도 벡터 순서로 대신하므로 짧게 기다린다"""
    url, headers = _config()
    body = {"model": RERANK_MODEL, "query": query, "documents": documents}
    if truncate:
        body["truncate_prompt_tokens"] = truncate
    r = await _client().post(f"{url}/v1/rerank", headers=headers, json=body, timeout=timeout)
    if r.status_code != 200:
        raise GpuError(f"재정렬 실패 {r.status_code}")
    scores = [0.0] * len(documents)
    for item in r.json()["results"]:
        scores[item["index"]] = float(item["relevance_score"])
    return scores
