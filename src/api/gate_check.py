"""판정만 모든 평가 질문에 돌려 기대 유형과 비교. 실행: src/api 에서 .venv/Scripts/python <이 파일> [재정렬 on/off]"""
import asyncio, glob, json, os, sys, time, collections
sys.path.insert(0, ".")
import try_real  # noqa: F401
from app import gate, gpu, rag_real, rerank, search
from app.schemas import Message


async def main():
    items = {}
    for f in sorted(glob.glob("../../evaluation/datasets/*.jsonl")):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                items.setdefault((d["id"], d["question"]), d)
    stats = collections.Counter(); times = []
    for (i, q), d in items.items():
        msgs = [Message(**h) for h in d.get("history", [])] + [Message(role="user", content=q)]
        query = rag_real.search_query(msgs)
        v = await gpu.embed(query)
        if rerank.enabled():
            pool = search.search(v, 20, query, 20)
            hits = rerank.by_vector(pool, 5)
        else:
            hits = search.search(v, 5, query)
        if not hits or (max(h["score"] for h in hits) < 0.48 and not rag_real.term_match(query, hits)):
            stats["점수로 확인불가"] += 1
            continue
        if rerank.enabled():
            hits = await rerank.rerank(query, pool, 5)
        t = time.perf_counter()
        ok = await gate.answerable(msgs, hits)
        times.append(time.perf_counter() - t)
        exp = d.get("expect_type", [])
        if not ok and "unknown" not in exp:
            stats["잘못 막음"] += 1; print("✗ 잘못 막음", i, q[:40], exp)
        elif not ok:
            stats["맞게 막음"] += 1; print("✓ 맞게 막음", i, q[:40])
        elif exp == ["unknown"]:
            stats["놓침(unknown인데 통과)"] += 1; print("· 놓침", i, q[:40])
        else:
            stats["통과"] += 1
    times.sort()
    print(dict(stats), f"판정 시간 중앙 {times[len(times)//2]:.2f}s 최대 {times[-1]:.2f}s")


asyncio.run(main())
