"""Neon pgvector 검색 (색인은 scripts/18_load_pgvector.py로 넣는다. SQL은 src/rag/pg_store.py와 같다).

결과 형식은 제안서 1절: {"chunk": 청크 그대로, "score": 코사인 유사도}. 쓸 색인 버전은 INDEX_VERSION으로 명시한다.
한 문서의 청크가 상위를 다 차지하지 않게 문서당 MAX_PER_DOC개까지만 남긴다 (예: "예약"에 체육시설 표 5개만 나와
홍보관·항만안내선이 빠지면 LLM이 되물을 수 없다).
"""
import os

from sqlalchemy import text

from app.db import engine

MAX_PER_DOC = 2
CANDIDATES = 4  # k의 몇 배를 먼저 가져와 문서당 상한을 적용할지

SQL = text(
    "SELECT chunk, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM rag_chunks "
    "WHERE index_version = :version ORDER BY embedding <=> CAST(:q AS vector), chunk_id LIMIT :n"
)


def diversify(rows: list[dict], k: int, max_per_doc: int = MAX_PER_DOC) -> list[dict]:
    """점수 순서를 지키면서 문서당 max_per_doc개까지만 골라 k개를 채운다"""
    picked, per_doc = [], {}
    for r in rows:
        doc = r["chunk"]["doc_id"]
        if per_doc.get(doc, 0) < max_per_doc:
            picked.append(r)
            per_doc[doc] = per_doc.get(doc, 0) + 1
            if len(picked) == k:
                break
    return picked


def search(query_vector: list[float], k: int = 5) -> list[dict]:
    version = os.getenv("INDEX_VERSION")
    if not version:
        raise RuntimeError("INDEX_VERSION이 설정되지 않았습니다")
    q = "[" + ",".join(map(str, query_vector)) + "]"
    with engine.connect() as conn:
        rows = conn.execute(SQL, {"q": q, "version": version, "n": k * CANDIDATES}).all()
    return diversify([{"chunk": chunk, "score": float(score)} for chunk, score in rows], k)
