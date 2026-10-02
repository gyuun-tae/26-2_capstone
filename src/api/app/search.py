"""Neon pgvector 검색 (색인은 scripts/18_load_pgvector.py로 넣는다. SQL은 src/rag/pg_store.py와 같다).

결과 형식은 제안서 1절: {"chunk": 청크 그대로, "score": 코사인 유사도}. 쓸 색인 버전은 INDEX_VERSION으로 명시한다.
"""
import os

from sqlalchemy import text

from app.db import engine

SQL = text(
    "SELECT chunk, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM rag_chunks "
    "WHERE index_version = :version ORDER BY embedding <=> CAST(:q AS vector), chunk_id LIMIT :k"
)


def search(query_vector: list[float], k: int = 5) -> list[dict]:
    version = os.getenv("INDEX_VERSION")
    if not version:
        raise RuntimeError("INDEX_VERSION이 설정되지 않았습니다")
    q = "[" + ",".join(map(str, query_vector)) + "]"
    with engine.connect() as conn:
        rows = conn.execute(SQL, {"q": q, "version": version, "k": k}).all()
    return [{"chunk": chunk, "score": float(score)} for chunk, score in rows]
