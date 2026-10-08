"""Neon pgvector 검색 (색인은 scripts/18_load_pgvector.py로 넣는다).

결과 형식은 제안서 1절: {"chunk": 청크 그대로, "score": 코사인 유사도}. 쓸 색인 버전은 INDEX_VERSION으로 명시한다.
한 문서의 청크가 상위를 다 차지하지 않게 문서당 MAX_PER_DOC개까지만 남긴다 (예: "예약"에 체육시설 표 5개만 나와
홍보관·항만안내선이 빠지면 LLM이 되물을 수 없다).
법령·고시(doc_id LAW-…)는 k개 중 MAX_LAW개까지만 넣는다. 조문 수가 많아 YGPA 안내(Port-MIS·서식·연락처)를 밀어내기
때문 (예: "입항 신고는 어디서" → 근거 5개가 모두 법령이 되어 Port-MIS 안내가 빠짐, docs/handoff/22_laws.md).
법령 서식(chunk_kind whole_form, scripts/27)은 이 상한에 세지 않는다: 내려받을 서식이라 조문처럼 안내를 밀어내지 않고,
세면 "출입 신고서 어디서 받아요?"에 서식이 조문 2개에 밀려 빠진다. 대신 법령 서식끼리 MAX_FORM개 상한을 따로 둔다:
상한이 없으면 "신고서"가 들어간 다른 법령 서식이 남는 자리를 채워 LLM이 함께 소개한다
(예: "출입 신고서는 어디서" → 자유무역지역법 "사업개시 신고서", 평가 w01).
적용 대상이 한정된 문서(SCOPED_DOCS)는 질문에 그 대상을 가리키는 말이 있을 때만 후보에 넣는다. 예: 통과선박 지침은
"입항 절차"에도 1위로 올라와 LLM이 통과선박 절차를 일반 입항 절차처럼 답했다(팀원 로그 39·46·47·69, 지시문으로는 흔들림).
반대로 선박 '출입 신고'를 물으면 사람·차량 출입증 서식(PASS_FORMS)을 뺀다. "출입"·"신청서"가 겹쳐 1·2위로 올라와
LLM이 출입 신고서의 관련 서식이라고 소개했다(로그 125, 평가 r10). 출입증을 허용 조건으로 거는 쪽은 "출입즘"(오타)·
"드나드는 업체"·영어 질문을 놓쳐서 쓰지 않는다.
문서당·법령 상한은 DB 안에서 적용하고 고른 k개의 청크 원문만 가져온다 (후보 원문을 모두 받으면 느리다).
"""
import os
import re

from sqlalchemy import text

from app.db import engine

MAX_PER_DOC = 2
MAX_LAW = 2
MAX_FORM = 1
# 문서 → 질문에 이 말 중 하나가 있어야 검색 후보가 되는 문서 (대상이 한정된 지침·서식)
SCOPED_DOCS = {
    "YGPA-028": ("통과",),  # 통과선박 인정 신청서
    "YGPA-030": ("통과",),  # 여수항ㆍ광양항 통과선박 운영 지침
}

# 거리 → 문서별 순위(rn) → 문서당 상한 → 종류별 순위(rg) → 법령 조문·법령 서식 상한 → 상위 k개만 청크 원문과 합친다.
# 종류(kind): law = 법령 조문·별표, form = 법령 서식, other = 그 밖. 청크 수백 개라 전체 비교
SQL = text("""
SELECT c.chunk, 1 - r.dist AS score
FROM (
    SELECT chunk_id, dist, kind, row_number() OVER (PARTITION BY kind ORDER BY dist, chunk_id) AS rg
    FROM (
        SELECT chunk_id, dist, kind, row_number() OVER (PARTITION BY doc_id ORDER BY dist, chunk_id) AS rn
        FROM (SELECT chunk_id, doc_id, embedding <=> CAST(:q AS vector) AS dist,
                     CASE WHEN doc_id NOT LIKE 'LAW-%' THEN 'other'
                          WHEN chunk->>'chunk_kind' = 'whole_form' THEN 'form' ELSE 'law' END AS kind
              FROM rag_chunks WHERE index_version = :version AND NOT (doc_id = ANY(:excluded))) d
    ) p
    WHERE rn <= :per_doc
) r
JOIN rag_chunks c ON c.index_version = :version AND c.chunk_id = r.chunk_id
WHERE r.kind = 'other' OR (r.kind = 'law' AND r.rg <= :max_law) OR (r.kind = 'form' AND r.rg <= :max_form)
ORDER BY r.dist, r.chunk_id
LIMIT :k
""")


def law_cap() -> int:
    return int(os.getenv("RAG_MAX_LAW", MAX_LAW))  # 실험용 조정값


def form_cap() -> int:
    return int(os.getenv("RAG_MAX_FORM", MAX_FORM))


def kind(chunk: dict) -> str:
    """상한을 따로 세는 묶음 (SQL의 kind와 같은 규칙): law = 법령·고시 조문·별표, form = 법령 서식, other"""
    if not chunk["doc_id"].startswith("LAW-"):
        return "other"
    return "form" if chunk.get("chunk_kind") == "whole_form" else "law"


def is_capped_law(chunk: dict) -> bool:
    """법령 상한에 세는 청크: 법령·고시 조문·별표. 법령 서식은 세지 않는다"""
    return kind(chunk) == "law"


PASS_FORMS = ("YGPA-022", "YGPA-023", "YGPA-024", "YGPA-025")  # 출입증 분실경위서·출입업체 등록·기간연장·발급 신청서
VESSEL_REPORT = re.compile(r"출입\s*신고")


def excluded_docs(question: str) -> list[str]:
    excluded = [doc for doc, words in SCOPED_DOCS.items() if not any(w in question for w in words)]
    if VESSEL_REPORT.search(question) and "출입증" not in question:
        excluded += PASS_FORMS
    return excluded


def search(query_vector: list[float], k: int = 5, question: str = "", max_law: int | None = None) -> list[dict]:
    """max_law: 법령 조문·서식 상한을 바꿀 때 (재정렬 후보는 상한 없이 받고 재정렬 뒤에 상한을 건다, app/rerank.py)"""
    version = os.getenv("INDEX_VERSION")
    if not version:
        raise RuntimeError("INDEX_VERSION이 설정되지 않았습니다")
    q = "[" + ",".join(map(str, query_vector)) + "]"
    with engine.connect() as conn:
        max_form = form_cap() if max_law is None else max_law
        if max_law is None:
            max_law = law_cap()
        rows = conn.execute(SQL, {"q": q, "version": version, "per_doc": MAX_PER_DOC, "max_law": max_law,
                                  "max_form": max_form, "k": k, "excluded": excluded_docs(question)}).all()
    return [{"chunk": chunk, "score": float(score)} for chunk, score in rows]
