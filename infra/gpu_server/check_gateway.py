"""관문·터널 확인. 표준 라이브러리만 사용. 키 검사, 막힌 주소, 임베딩, 재정렬, 스트리밍(조금씩 도착하는지)을 본다.

실행: python3 check_gateway.py [주소]   (주소를 안 주면 start_tunnel.sh가 저장한 tunnel_url, 그것도 없으면 http://127.0.0.1:8200)
"""
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

HOME = Path.home() / "llm-serve"
KEY = (HOME / ".api_key").read_text().strip()
UA = {"User-Agent": "ygpa-gateway-check/1.0"}


def request(base, path, body=None, key=KEY):
    headers = {**UA, "Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    return urllib.request.Request(base + path, data=data, headers=headers, method="POST" if data else "GET")


def status(req):
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    saved = HOME / "tunnel_url"
    base = (sys.argv[1] if len(sys.argv) > 1 else saved.read_text().strip() if saved.exists() else "http://127.0.0.1:8200").rstrip("/")
    print("대상:", base)
    chat = {"model": "qwen3-32b", "messages": [{"role": "user", "content": "항만에서 컨테이너가 처리되는 과정을 5단계로 설명해 주세요."}],
            "max_tokens": 300, "chat_template_kwargs": {"enable_thinking": False}}
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  {'OK ' if ok else '실패'} {name} {detail}")

    check("상태 확인 /health", status(request(base, "/health")) == 200)
    check("키 없으면 거부", status(request(base, "/v1/embeddings", {"model": "bge-m3", "input": ["x"]}, key=None)) == 401)
    check("틀린 키 거부", status(request(base, "/v1/embeddings", {"model": "bge-m3", "input": ["x"]}, key="wrong")) == 401)
    for path in ("/tokenize", "/docs", "/v1/models", "/metrics"):
        code = status(request(base, path, {} if path == "/tokenize" else None))
        check(f"막힌 주소 {path}", code in (404, 405), f"({code})")
    check("다른 모델 이름 거부", status(request(base, "/v1/embeddings", {"model": "qwen3-32b", "input": ["x"]})) == 400)

    start = time.time()
    with urllib.request.urlopen(request(base, "/v1/embeddings", {"model": "bge-m3", "input": ["선박 입항 신고 절차"]}), timeout=30) as r:
        dim = len(json.load(r)["data"][0]["embedding"])
    check("임베딩", dim == 1024, f"(크기 {dim}, {time.time() - start:.2f}초)")

    # 재정렬: 관련 있는 글이 더 높은 점수, 후보 수 상한, 다른 모델 이름 거부
    rerank = {"model": "bge-reranker", "query": "선박 입항 신고는 어디에 하나요?",
              "documents": ["테니스장은 하루 2시간까지 예약할 수 있습니다.", "선박의 선장은 내항선 출입 신고서를 관리청에 제출하여야 한다."]}
    start = time.time()
    with urllib.request.urlopen(request(base, "/v1/rerank", rerank), timeout=30) as r:
        scores = {x["index"]: x["relevance_score"] for x in json.load(r)["results"]}
    check("재정렬", scores[1] > scores[0], f"(무관 {scores[0]:.3f} < 관련 {scores[1]:.3f}, {time.time() - start:.2f}초)")
    check("재정렬 후보 수 상한", status(request(base, "/v1/rerank", {**rerank, "documents": ["x"] * 33})) == 400)
    check("재정렬 다른 모델 거부", status(request(base, "/v1/rerank", {**rerank, "model": "bge-m3"})) == 400)

    # 답변 전 판정 모델(start_gate.sh): 같은 주소에 모델 이름만 다르다. 꺼져 있으면 API는 판정 없이 답하므로 건너뛴다
    gate = {**chat, "model": "gate-llm", "max_tokens": 12, "temperature": 0,
            "messages": [{"role": "user", "content": "다음 질문이 항만에 관한 것이면 '있음', 아니면 '없음' 한 단어로만 답하세요: 오늘 서울 날씨 어때요?"}]}
    start = time.time()
    try:
        with urllib.request.urlopen(request(base, "/v1/chat/completions", gate), timeout=30) as r:
            verdict = json.load(r)["choices"][0]["message"]["content"]
        check("판정 모델", "없음" in verdict, f"({verdict.strip()!r}, {time.time() - start:.2f}초)")
    except urllib.error.HTTPError as e:
        print(f"  건너뜀 판정 모델 ({e.code}, start_gate.sh로 켬)")

    start, arrivals, text = time.time(), [], []
    with urllib.request.urlopen(request(base, "/v1/chat/completions", {**chat, "stream": True}), timeout=120) as r:
        print("  스트리밍 응답 형식:", r.headers.get("Content-Type"))
        for line in iter(r.readline, b""):
            if line.strip():
                arrivals.append(time.time() - start)
                delta = json.loads(line)["choices"][0].get("delta", {})
                text.append(delta.get("content") or "")
    first, total = arrivals[0], arrivals[-1]
    # 조금씩 도착하면 첫 줄이 마지막 줄보다 훨씬 먼저 온다. 모아서 한 번에 오면 둘이 거의 같다
    streaming = len(arrivals) > 10 and first < total * 0.5
    check("스트리밍이 조금씩 도착", streaming, f"(줄 {len(arrivals)}개, 첫 줄 {first:.2f}초, 마지막 줄 {total:.2f}초)")
    print("  답변 앞부분:", "".join(text)[:80].replace("\n", " "))

    print("결과:", "통과" if all(results) else "실패 항목 있음")


if __name__ == "__main__":
    main()
