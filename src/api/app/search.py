"""Neon pgvector 검색 (색인은 scripts/18_load_pgvector.py로 넣는다).

결과 형식은 제안서 1절: {"chunk": 청크 그대로, "score": 코사인 유사도}. 쓸 색인 버전은 INDEX_VERSION으로 명시한다.
한 문서의 청크가 상위를 다 차지하지 않게 문서당 MAX_PER_DOC개까지만 남긴다 (예: "예약"에 체육시설 표 5개만 나와
홍보관·항만안내선이 빠지면 LLM이 되물을 수 없다).
법령·고시(doc_id LAW-…)는 k개 중 MAX_LAW개까지만 넣는다. 조문 수가 많아 YGPA 안내(Port-MIS·서식·연락처)를 밀어내기
때문 (예: "입항 신고는 어디서" → 근거 5개가 모두 법령이 되어 Port-MIS 안내가 빠짐, docs/handoff/22_laws.md).
문서당·법령 상한은 DB 안에서 적용하고 고른 k개의 청크 원문만 가져온다 (후보 원문을 모두 받으면 느리다).
"""
import os

from sqlalchemy import text

from app.db import engine

MAX_PER_DOC = 2
MAX_LAW = 2

# 거리 → 문서별 순위(rn) → 문서당 상한 → 법령 묶음 순위(rg) → 법령 상한 → 상위 k개만 청크 원문과 합친다. 청크 수백 개라 전체 비교
SQL = text("""
SELECT c.chunk, 1 - r.dist AS score
FROM (
    SELECT chunk_id, dist, is_law, row_number() OVER (PARTITION BY is_law ORDER BY dist, chunk_id) AS rg
    FROM (
        SELECT chunk_id, dist, doc_id LIKE 'LAW-%' AS is_law,
               row_number() OVER (PARTITION BY doc_id ORDER BY dist, chunk_id) AS rn
        FROM (SELECT chunk_id, doc_id, embedding <=> CAST(:q AS vector) AS dist
              FROM rag_chunks WHERE index_version = :version) d
    ) p
    WHERE rn <= :per_doc
) r
JOIN rag_chunks c ON c.index_version = :version AND c.chunk_id = r.chunk_id
WHERE NOT r.is_law OR r.rg <= :max_law
ORDER BY r.dist, r.chunk_id
LIMIT :k
""")


def search(query_vector: list[float], k: int = 5) -> list[dict]:
    version = os.getenv("INDEX_VERSION")
    if not version:
        raise RuntimeError("INDEX_VERSION이 설정되지 않았습니다")
    q = "[" + ",".join(map(str, query_vector)) + "]"
    with engine.connect() as conn:
        max_law = int(os.getenv("RAG_MAX_LAW", MAX_LAW))  # 실험용 조정값
        rows = conn.execute(SQL, {"q": q, "version": version, "per_doc": MAX_PER_DOC, "max_law": max_law, "k": k}).all()
    return [{"chunk": chunk, "score": float(score)} for chunk, score in rows]
