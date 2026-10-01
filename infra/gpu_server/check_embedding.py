"""GPU 서버 임베딩이 로컬 색인과 같은 벡터를 내는지 확인한다. 표준 라이브러리만 사용.

입력: 로컬에서 만든 비교 파일 (글 + 로컬 BGE-M3 벡터). 서버의 /v1/embeddings 결과와 코사인 유사도를 비교한다.
실행: python3 check_embedding.py bge_m3_check.json
"""
import json
import math
from pathlib import Path
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8101/v1/embeddings"
THRESHOLD = 0.999  # GPU 반정밀도 계산 차이는 허용, 모델·pooling 차이는 걸러진다


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def main():
    check = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    key = (Path.home() / "llm-serve/.api_key").read_text().strip()
    body = json.dumps({"model": "bge-m3", "input": [it["text"] for it in check["items"]]}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    start = time.time()
    data = json.load(urllib.request.urlopen(req))["data"]
    elapsed = time.time() - start

    print(f"로컬 색인 모델 revision: {check['model_revision'][:12]} | 서버 응답 {elapsed:.2f}초 | 벡터 크기 {len(data[0]['embedding'])}")
    worst = 1.0
    for it, d in zip(check["items"], data):
        c = cosine(it["vector"], d["embedding"])
        worst = min(worst, c)
        print(f"  {it['name']:<11} 글자 {len(it['text']):>5} | 코사인 {c:.6f} {'OK' if c >= THRESHOLD else '불일치'}")
    print("결과:", "일치" if worst >= THRESHOLD else f"불일치 (최저 {worst:.6f}) — 모델 revision·pooling 설정 확인 필요")


if __name__ == "__main__":
    main()
