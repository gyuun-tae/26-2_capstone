"""Neon에 올리기 전에 로컬 색인 파일(data/index/<버전>)로 eval_dev.py를 돌린다 (측정 전용, 서비스 코드는 그대로).

app/search.py의 SQL과 같은 규칙을 파이썬으로 따라 한다: 자식(항)→부모 합침, 문서당 MAX_PER_DOC, 법령 조문·서식 상한,
질문별 제외 문서, 한국어 질문이면 외국어 청크 제외. 임베딩·재정렬·판정·생성은 실제 GPU 서버를 쓴다.

  uv run python eval_local.py --index bge-m3-dense-a08c18db6071 --dataset dev_questions_site_v1.jsonl --label site-after
"""
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def install(index: str):
    from rag import dense
    from app import search

    vectors, chunks, _ = dense.load(ROOT / "data/index" / index)
    by_id = {c["chunk_id"]: c for c in chunks}
    units = [c.get("parent_chunk_id") or c["chunk_id"] for c in chunks]
    langs = np.array([(by_id.get(u) or c).get("language", "ko") for c, u in zip(chunks, units)])

    def local(query_vector, k=5, question="", max_law=None):
        q = np.asarray(query_vector, dtype=np.float32)
        dist = 1 - vectors @ (q / np.linalg.norm(q))
        max_form = search.form_cap() if max_law is None else max_law
        max_law = search.law_cap() if max_law is None else max_law
        excluded = set(search.excluded_docs(question))
        foreign = search.is_foreign(question)
        best = {}
        for i in np.argsort(dist):
            c = chunks[i]
            if c["doc_id"] in excluded or (not foreign and langs[i] != "ko"):
                continue
            u = units[i]
            if u not in best:
                best[u] = (float(dist[i]), c["text"] if c.get("parent_chunk_id") else None)
        per_doc, per_kind, out = {}, {}, []
        for u, (d, part) in sorted(best.items(), key=lambda x: (x[1][0], x[0])):
            parent = by_id[u]
            per_doc[parent["doc_id"]] = per_doc.get(parent["doc_id"], 0) + 1
            if per_doc[parent["doc_id"]] > search.MAX_PER_DOC:
                continue
            kind = search.kind(parent)
            per_kind[kind] = per_kind.get(kind, 0) + 1
            if (kind == "law" and per_kind[kind] > max_law) or (kind == "form" and per_kind[kind] > max_form):
                continue
            out.append({"chunk": parent, "score": 1 - d} | ({"part": part} if part else {}))
            if len(out) >= k:
                break
        return out

    search.search = local
    os.environ["INDEX_VERSION"] = index


if __name__ == "__main__":
    i = sys.argv.index("--index")
    index = sys.argv.pop(i + 1)
    sys.argv.pop(i)
    import try_real  # noqa: F401  (.env를 읽고 앱 모듈을 불러온다)
    install(index)
    import asyncio
    import eval_dev
    eval_dev.search.search = __import__("app.search", fromlist=["search"]).search
    asyncio.run(eval_dev.main()) if asyncio.iscoroutinefunction(eval_dev.main) else eval_dev.main()
