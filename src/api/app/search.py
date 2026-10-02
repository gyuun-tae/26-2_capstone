"""Neon pgvector 검색 (색인은 scripts/18_load_pgvector.py로 넣는다).

결과 형식은 제안서 1절: {"chunk": 청크 그대로, "score": 코사인 유사도}. 쓸 색인 버전은 INDEX_VERSION으로 명시한다.
한 문서의 청크가 상위를 다 차지하지 않게 문서당 MAX_PER_DOC개까지만 남긴다 (예: "예약"에 체육시설 표 5개만 나와
홍보관·항만안내선이 빠지면 LLM이 되물을 수 없다).
문서당 상한은 DB 안에서 적용하고 고른 k개의 청크 원문만 가져온다 (후보 원문을 모두 받으면 느리다).
"""
import os

from sqlalchemy import text

from app.db import engine

MAX_PER_DOC = 2

# 거리 → 문서별 순위(rn) → 문서당 상한 → 상위 k개만 청크 원문과 합친다. 청크 수백 개라 전체 비교
SQL = text("""
SELECT c.chunk, 1 - r.dist AS score
FROM (
    SELECT chunk_id, dist, row_number() OVER (PARTITION BY doc_id ORDER BY dist, chunk_id) AS rn
    FROM (SELECT chunk_id, doc_id, embedding <=> CAST(:q AS vector) AS dist
          FROM rag_chunks WHERE index_version = :version) d
) r
JOIN rag_chunks c ON c.index_version = :version AND c.chunk_id = r.chunk_id
WHERE r.rn <= :per_doc
ORDER BY r.dist, r.chunk_id
LIMIT :k
""")


def search(query_vector: list[float], k: int = 5) -> list[dict]:
    version = os.getenv("INDEX_VERSION")
    if not version:
        raise RuntimeError("INDEX_VERSION이 설정되지 않았습니다")
    q = "[" + ",".join(map(str, query_vector)) + "]"
    with engine.connect() as conn:
        rows = conn.execute(SQL, {"q": q, "version": version, "per_doc": MAX_PER_DOC, "k": k}).all()
    return [{"chunk": chunk, "score": float(score)} for chunk, score in rows]
