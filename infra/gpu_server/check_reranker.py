"""재정렬 서비스(vLLM, start_reranker.sh)가 실험 점수(transformers, rerank_exp.py)와 같은지 확인. 표준 라이브러리만 사용.

실험 폴더(~/llm-serve/rerank)의 cands.json(질문별 검색 후보)·rr_scores.json(실험 점수)을 써서, 같은 후보를
vLLM /v1/rerank로 다시 채점한다. 입력 길이 처리 두 가지를 비교한다: 자르지 않음 / truncate_prompt_tokens=512.
실험 점수는 로짓이라 시그모이드로 바꿔 비교한다 (vLLM relevance_score는 0~1).

실행: python3 check_reranker.py [실험 폴더]
"""
import json
import math
from pathlib import Path
import sys
import urllib.error
import urllib.request

HOME = Path.home() / "llm-serve"
KEY = (HOME / ".api_key").read_text().strip()
URL = "http://127.0.0.1:8102/v1/rerank"
N = 10  # 서비스와 같은 후보 수


def rerank(query, documents, extra):
    body = {"model": "bge-reranker", "query": query, "documents": documents, **extra}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            results = json.load(r)["results"]
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read()[:200]!r}"
    scores = [0.0] * len(documents)
    for x in results:
        scores[x["index"]] = x["relevance_score"]
    return scores


def order(scores):
    return sorted(range(len(scores)), key=lambda i: -scores[i])


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else HOME / "rerank"
    cands = json.loads((folder / "cands.json").read_text(encoding="utf-8"))
    saved = {(r["set"], r["id"]): r["rr"] for r in json.loads((folder / "rr_scores.json").read_text(encoding="utf-8"))}
    sample = cands[::6]  # 185개 중 31개
    for name, extra in (("자르지 않음", {}), ("truncate_prompt_tokens=512", {"truncate_prompt_tokens": 512})):
        diffs, same_top1, same_top5, errors = {512: [], 1024: []}, {512: 0, 1024: 0}, {512: 0, 1024: 0}, []
        for d in sample:
            docs = [c["text"] for c in d["cands"][:N]]
            got = rerank(d["q"], docs, extra)
            if isinstance(got, str):
                errors.append(got)
                continue
            for col, length in ((1, 512), (2, 1024)):
                ref = [1 / (1 + math.exp(-row[col])) for row in saved[(d["set"], d["id"])][:N]]
                diffs[length] += [abs(a - b) for a, b in zip(got, ref)]
                same_top1[length] += order(got)[0] == order(ref)[0]
                same_top5[length] += order(got)[:5] == order(ref)[:5]
        print(f"[{name}] 질문 {len(sample)}개, 오류 {len(errors)}개 {errors[:1]}")
        for length in (512, 1024):
            if diffs[length]:
                print(f"   실험 {length}토큰과 비교: 점수 차 평균 {sum(diffs[length]) / len(diffs[length]):.4f}·최대 {max(diffs[length]):.4f}"
                      f" | 1위 같음 {same_top1[length]}/{len(sample) - len(errors)} | 상위5 순서 같음 {same_top5[length]}/{len(sample) - len(errors)}")


if __name__ == "__main__":
    main()
