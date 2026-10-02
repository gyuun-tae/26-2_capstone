"""16번 dense 색인을 Neon(PostgreSQL + pgvector)에 넣고, 로컬 numpy 검색과 같은 결과가 나오는지 확인한다.

실행: .\\.venv\\Scripts\\python.exe -B .\\scripts\\18_load_pgvector.py [--index data/index/<버전>]
DB 주소: 환경변수 DATABASE_URL, 없으면 저장소 루트 .env(Git 제외)의 DATABASE_URL. 주소는 화면에 출력하지 않는다.
"""
import argparse
import os
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag import dense, pg_store  # noqa: E402

SCORE_TOLERANCE = 1e-5  # float32 저장·계산 순서 차이만 허용


def latest_index():
    folders = sorted((ROOT / "data/index").glob("*/manifest.json"), key=lambda p: p.stat().st_mtime)
    if not folders:
        sys.exit("색인이 없습니다. 먼저 16_build_index.py를 실행하세요.")
    return folders[-1].parent


def database_url():
    url = os.getenv("DATABASE_URL")
    env = ROOT / ".env"
    if not url and env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL":
                url = value.strip().strip("'\"")
    if not url or not url.startswith(("postgres", "postgresql")):
        sys.exit("DATABASE_URL이 없습니다. 저장소 루트 .env에 DATABASE_URL=<Neon 주소>를 넣으세요.")
    return pg_store.connection_url(url)


def compare(conn, version, vectors, chunks, k=5):
    """모든 청크 벡터를 질의로 써서 DB 검색과 numpy 검색의 순위·점수를 비교한다 (모델 불필요)"""
    mismatches, worst, times = [], 0.0, []
    for v in vectors:
        start = time.perf_counter()
        db_hits = pg_store.search(conn, version, v, k)
        times.append(time.perf_counter() - start)
        local_hits = dense.search(v, vectors, chunks, k)
        db_ids = [h["chunk"]["chunk_id"] for h in db_hits]
        local_ids = [h["chunk"]["chunk_id"] for h in local_hits]
        diff = max(abs(a["score"] - b["score"]) for a, b in zip(db_hits, local_hits))
        worst = max(worst, diff)
        # 점수가 허용오차 안에서 같은 청크끼리는 순서가 바뀌어도 같은 결과로 본다
        if db_ids != local_ids and diff > SCORE_TOLERANCE:
            mismatches.append((local_ids[0], db_ids, local_ids))
    return mismatches, worst, times


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path)
    args = ap.parse_args()

    folder = args.index or latest_index()
    vectors, chunks, manifest = dense.load(folder)  # 벡터 파일 해시 확인 포함
    version = manifest["index_version"]
    print(f"색인 {version}: 청크 {len(chunks)}개, 벡터 {vectors.shape}, 승인 {manifest['approved_count']}개")

    with psycopg.connect(database_url()) as conn:
        with conn.transaction():
            pg_store.ensure_schema(conn)
            pg_store.replace_version(conn, vectors, chunks, manifest)
        extension = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
        print(f"저장 완료 (pgvector {extension})")

        count = conn.execute("SELECT count(*) FROM rag_chunks WHERE index_version = %s", (version,)).fetchone()[0]
        stored = {cid: chunk for cid, chunk in conn.execute(
            "SELECT chunk_id, chunk FROM rag_chunks WHERE index_version = %s", (version,))}
        same_chunks = sum(stored.get(c["chunk_id"]) == c for c in chunks)
        print(f"행 수 {count}/{len(chunks)} | 청크 내용 일치 {same_chunks}/{len(chunks)}")

        mismatches, worst, times = compare(conn, version, np.asarray(vectors), chunks)
        print(f"검색 비교 {len(vectors)}개 질의: 상위 5개 불일치 {len(mismatches)}개, 점수 차 최대 {worst:.2e}")
        print(f"DB 검색 시간 (이 PC→Neon 왕복 포함): 중앙값 {statistics.median(times) * 1000:.0f}ms, "
              f"최대 {max(times) * 1000:.0f}ms")
        for m in mismatches[:5]:
            print("  불일치:", m)

    ok = count == len(chunks) and same_chunks == len(chunks) and not mismatches
    print("결과:", "일치" if ok else "불일치")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
