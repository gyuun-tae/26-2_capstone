"""Neon pgvector 검색 (색인은 scripts/18_load_pgvector.py로 넣는다).

결과 형식은 제안서 1절: {"chunk": 청크 그대로, "score": 코사인 유사도}. 쓸 색인 버전은 INDEX_VERSION으로 명시한다.
한 문서의 청크가 상위를 다 차지하지 않게 문서당 MAX_PER_DOC개까지만 남긴다 (예: "예약"에 체육시설 표 5개만 나와
홍보관·항만안내선이 빠지면 LLM이 되물을 수 없다).
법령·고시(doc_id LAW-…)는 k개 중 MAX_LAW개까지만 넣는다. 조문 수가 많아 YGPA 안내(Port-MIS·서식·연락처)를 밀어내기
때문 (예: "입항 신고는 어디서" → 근거 5개가 모두 법령이 되어 Port-MIS 안내가 빠짐, docs/handoff/22_laws.md).
법령 서식(chunk_kind whole_form, scripts/27)은 이 상한에 세지 않는다: 내려받을 서식이라 조문처럼 안내를 밀어내지 않고,
세면 "출입 신고서 어디서 받아요?"에 서식이 조문 2개에 밀려 빠진다.
적용 대상이 한정된 문서(SCOPED_DOCS)는 질문에 그 대상을 가리키는 말이 있을 때만 후보에 넣는다. 예: 통과선박 지침은
"입항 절차"에도 1위로 올라와 LLM이 통과선박 절차를 일반 입항 절차처럼 답했다(팀원 로그 39·46·47·69, 지시문으로는 흔들림).
문서당·법령 상한은 DB 안에서 적용하고 고른 k개의 청크 원문만 가져온다 (후보 원문을 모두 받으면 느리다).
"""
import os

from sqlalchemy import text

from app.db import engine

MAX_PER_DOC = 2
MAX_LAW = 2
# 문서 → 질문에 이 말 중 하나가 있어야 검색 후보가 되는 문서 (대상이 한정된 지침·서식)
SCOPED_DOCS = {
    "YGPA-028": ("통과",),  # 통과선박 인정 신청서
    "YGPA-030": ("통과",),  # 여수항ㆍ광양항 통과선박 운영 지침
}

# 거리 → 문서별 순위(rn) → 문서당 상한 → 법령 묶음 순위(rg) → 법령 상한 → 상위 k개만 청크 원문과 합친다. 청크 수백 개라 전체 비교
SQL = text("""
SELECT c.chunk, 1 - r.dist AS score
FROM (
    SELECT chunk_id, dist, is_law, row_number() OVER (PARTITION BY is_law ORDER BY dist, chunk_id) AS rg
    FROM (
        SELECT chunk_id, dist, doc_id LIKE 'LAW-%' AND chunk_kind IS DISTINCT FROM 'whole_form' AS is_law,
               row_number() OVER (PARTITION BY doc_id ORDER BY dist, chunk_id) AS rn
        FROM (SELECT chunk_id, doc_id, chunk->>'chunk_kind' AS chunk_kind, embedding <=> CAST(:q AS vector) AS dist
              FROM rag_chunks WHERE index_version = :version AND NOT (doc_id = ANY(:excluded))) d
    ) p
    WHERE rn <= :per_doc
) r
JOIN rag_chunks c ON c.index_version = :version AND c.chunk_id = r.chunk_id
WHERE NOT r.is_law OR r.rg <= :max_law
ORDER BY r.dist, r.chunk_id
LIMIT :k
""")


def excluded_docs(question: str) -> list[str]:
    return [doc for doc, words in SCOPED_DOCS.items() if not any(w in question for w in words)]


def search(query_vector: list[float], k: int = 5, question: str = "") -> list[dict]:
    version = os.getenv("INDEX_VERSION")
    if not version:
        raise RuntimeError("INDEX_VERSION이 설정되지 않았습니다")
    q = "[" + ",".join(map(str, query_vector)) + "]"
    with engine.connect() as conn:
        max_law = int(os.getenv("RAG_MAX_LAW", MAX_LAW))  # 실험용 조정값
        rows = conn.execute(SQL, {"q": q, "version": version, "per_doc": MAX_PER_DOC, "max_law": max_law, "k": k,
                                  "excluded": excluded_docs(question)}).all()
    return [{"chunk": chunk, "score": float(score)} for chunk, score in rows]
