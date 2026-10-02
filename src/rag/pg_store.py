"""dense 색인을 PostgreSQL(Neon) + pgvector에 저장·검색한다 (실행 방식 B, 제안서 4.5절).

연결(psycopg v3)은 바깥에서 넘겨받는다. 검색 결과 형식은 dense.search와 같다: {"chunk": 청크 그대로, "score": 코사인 유사도}.
색인 버전마다 행을 따로 두어 다른 모델·데이터의 벡터가 섞이지 않는다.
"""
import json

import numpy as np

DIMENSION = 1024  # BGE-M3 dense

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS rag_index_versions (
    index_version text PRIMARY KEY,
    manifest jsonb NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS rag_chunks (
    index_version text NOT NULL REFERENCES rag_index_versions ON DELETE CASCADE,
    chunk_id text NOT NULL,
    doc_id text NOT NULL,
    embedding vector({DIMENSION}) NOT NULL,
    chunk jsonb NOT NULL,
    PRIMARY KEY (index_version, chunk_id)
);
"""


def connection_url(url: str) -> str:
    """API용 SQLAlchemy 주소(postgresql+psycopg://)도 psycopg가 읽는 형태로 맞춘다"""
    for prefix in ("postgresql+psycopg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url.removeprefix(prefix)
    return url


def vector_literal(vector) -> str:
    """pgvector 입력 형식 '[0.1,0.2,...]'. float32 값을 그대로 옮긴다"""
    return "[" + ",".join(map(str, np.asarray(vector, dtype=np.float32).tolist())) + "]"


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA)


def replace_version(conn, vectors: np.ndarray, chunks: list[dict], manifest: dict) -> None:
    """한 색인 버전을 통째로 다시 넣는다. 호출한 쪽의 트랜잭션 안에서 실행 → 중간에 실패하면 이전 상태 유지"""
    if vectors.shape != (len(chunks), DIMENSION):
        raise ValueError(f"벡터 모양 {vectors.shape} ≠ 청크 {len(chunks)} × {DIMENSION}")
    version = manifest["index_version"]
    conn.execute("DELETE FROM rag_index_versions WHERE index_version = %s", (version,))
    conn.execute("INSERT INTO rag_index_versions (index_version, manifest) VALUES (%s, %s)",
                 (version, json.dumps(manifest, ensure_ascii=False)))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO rag_chunks (index_version, chunk_id, doc_id, embedding, chunk) VALUES (%s, %s, %s, %s::vector, %s)",
            [(version, c["chunk_id"], c["doc_id"], vector_literal(v), json.dumps(c, ensure_ascii=False))
             for c, v in zip(chunks, vectors)])


def search(conn, index_version: str, query_vector, k: int = 5) -> list[dict]:
    """코사인 거리(<=>) 상위 k개. 청크 수백 개라 ANN 인덱스 없이 전체 비교 → numpy 검색과 같은 결과.
    ponytail: 청크가 수만 개로 늘면 HNSW 인덱스(vector_cosine_ops) 추가"""
    q = vector_literal(query_vector)
    rows = conn.execute(
        "SELECT chunk, 1 - (embedding <=> %s::vector) FROM rag_chunks WHERE index_version = %s "
        "ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s", (q, index_version, q, k)).fetchall()
    return [{"chunk": chunk, "score": float(score)} for chunk, score in rows]
