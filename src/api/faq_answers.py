"""FAQ 최종 평가용: 질문을 V1·V2 설정으로 실제 RAG에 넣고 답변만 모은다. 채점하지 않고 정답도 읽지 않는다.

실행: uv run python faq_answers.py --version v1|v2 [--index <색인>] [--only F01,F02]
입력: evaluation/private/ygpa_faq/faq_questions.jsonl (FAQ CSV의 질문 열만 뽑은 것)
결과: evaluation/private/ygpa_faq/answers_<버전>_<날짜>.jsonl — 한 줄씩 바로 추가하고, 다시 실행하면 이미 있는 id는 건너뛴다.
FAQ는 Git·색인 밖(evaluation/private, docs/contracts/evaluation_boundary.md)에만 둔다. 대화 로그는 남기지 않는다.

채점은 evaluation/score_faq.py로 평가팀이 한다(골든셋은 평가팀만 보관). 채점용으로 청크 ID도 남긴다.

버전 (색인은 기본값 = 실서비스 색인, 11/2 수집분은 c8f1fc61affe):
- v1 = 홈페이지 청크만: 법령 조문·법령 서식 상한 0, 재정렬·판정 끔
- v2 = 실서비스 그대로: 법령 + 재정렬 + 판정 (10/14~)
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

INDEX = "bge-m3-dense-7747f421d88d"  # 기본값. --index로 바꿈
VERSIONS = {
    "v1": {"RAG_MAX_LAW": "0", "RAG_MAX_FORM": "0", "RAG_RERANK": "off", "RAG_GATE": "off"},
    "v2": {"RAG_RERANK": "on", "RAG_GATE": "on"},
}
ROOT = Path(__file__).resolve().parents[2]
FAQ = ROOT / "evaluation/private/ygpa_faq"


async def run_one(item: dict) -> dict:
    from app import rag_real, rerank, search
    from app.schemas import Message

    hits = []
    original, original_rerank = search.search, rerank.rerank
    k = int(os.getenv("RAG_K", rag_real.K))

    # 조립 코드가 실제로 쓴 근거를 기록 (eval_dev.py와 같은 방식: unknown이면 sources가 비므로)
    def recording(vector, n, question="", max_law=None):
        found = original(vector, n, question, max_law)
        hits[:] = found if max_law is None else rerank.by_vector(found, k)
        return found

    async def recording_rerank(query, pool, n):
        hits[:] = await original_rerank(query, pool, n)
        return list(hits)

    search.search, rerank.rerank = recording, recording_rerank
    try:
        start, first, pieces = time.perf_counter(), None, []
        result = rag_real.answer([Message(role="user", content=item["question"])])
        async for piece in result.tokens:
            first = first or time.perf_counter() - start
            pieces.append(piece)
        total = time.perf_counter() - start
    finally:
        search.search, rerank.rerank = original, original_rerank

    return {"id": item["id"], "faq_no": item["faq_no"], "question": item["question"],
            "answer_type": result.answer_type, "error": result.error, "answer": "".join(pieces).strip(),
            "sources": [f"[{i}] {s.doc_id} {s.title}" + (f" · {s.locator}" if s.locator else "")
                        for i, s in enumerate(result.sources, 1)],
            "searched": [f"{h['chunk']['doc_id']} {h['chunk']['title']} ({h['score']:.3f})" for h in hits],
            "source_chunks": [s.chunk_id for s in result.sources],
            "searched_chunks": [h["chunk"]["chunk_id"] for h in hits],
            "buttons": [f"{a.type}: {a.label}" for a in result.actions], "options": [o.label for o in result.options],
            "first_token_s": round(first or total, 2), "total_s": round(total, 2), "timings": result.timings}


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", choices=VERSIONS, required=True)
    ap.add_argument("--only", help="쉼표로 구분한 id만 실행")
    ap.add_argument("--index", default=INDEX, help="색인 버전 (기본: 실서비스)")
    ap.add_argument("--date", default=f"{datetime.now():%Y%m%d}", help="이어서 실행할 결과 파일 날짜")
    args = ap.parse_args()

    # .env보다 먼저 정해 둔다 (try_real은 setdefault라 이미 있는 값은 덮지 않는다)
    os.environ |= {"INDEX_VERSION": args.index, **VERSIONS[args.version]}
    import try_real  # noqa: F401  (.env를 읽고 앱 모듈을 불러온다)

    items = [json.loads(line) for line in (FAQ / "faq_questions.jsonl").read_text(encoding="utf-8").splitlines()]
    if args.only:
        items = [i for i in items if i["id"] in args.only.split(",")]
    out = FAQ / f"answers_{args.version}_{args.date}.jsonl"
    done = set()
    if out.exists():
        done = {json.loads(line).get("id") for line in out.read_text(encoding="utf-8").splitlines()}
    else:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        meta = {"meta": True, "version": args.version, "index_version": args.index, "env": VERSIONS[args.version],
                "commit": commit, "run_at": datetime.now(timezone.utc).isoformat()}
        out.write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")

    for item in items:
        if item["id"] in done:
            continue
        r = await run_one(item)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{r['id']} {r['answer_type']:<7} 첫 {r['first_token_s']}초 전체 {r['total_s']}초"
              + (f" 오류 {r['error']}" if r["error"] else "") + f" | {r['question']}", flush=True)
    print("저장:", out.relative_to(ROOT))


if __name__ == "__main__":
    asyncio.run(main())
