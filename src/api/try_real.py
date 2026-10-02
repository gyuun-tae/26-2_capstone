"""실제 RAG(GPU 서버 + Neon)로 질문해 보고 시간을 잰다. 대화 로그는 남기지 않는다.

실행: uv run python try_real.py "질문" ["질문2" ...]
설정: 저장소 루트 .env (Git 제외) — DATABASE_URL, GPU_URL, GPU_API_KEY, INDEX_VERSION. 값은 화면에 출력하지 않는다.
"""
import asyncio
import os
from pathlib import Path
import sys
import time

for line in (Path(__file__).resolve().parents[2] / ".env").read_text(encoding="utf-8-sig").splitlines():
    key, _, value = line.partition("=")
    if key.strip() and not key.startswith("#"):
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
missing = [k for k in ("DATABASE_URL", "GPU_URL", "GPU_API_KEY", "INDEX_VERSION") if not os.getenv(k)]
if missing:
    sys.exit(f".env에 없는 값: {missing}")

from app import rag_real  # noqa: E402  (.env를 읽은 뒤 DB 연결)
from app.schemas import Message  # noqa: E402


async def ask(question: str):
    start = time.perf_counter()
    result = rag_real.answer([Message(role="user", content=question)])
    first, pieces = None, []
    async for piece in result.tokens:
        first = first or time.perf_counter() - start
        pieces.append(piece)
        print(piece, end="", flush=True)
    total = time.perf_counter() - start
    print(f"\n\n── 유형 {result.answer_type} | 첫 글자 {first:.2f}초 · 전체 {total:.2f}초")
    for i, s in enumerate(result.sources, 1):
        print(f"  [{i}] {s.doc_id} {s.title} · {s.locator}")
    for a in result.actions:
        print(f"  버튼: {a.type} {a.label} {a.url or ''}")
    for o in result.options:
        print(f"  선택지: {o.label}")
    print()


async def main():
    for q in sys.argv[1:]:
        print(f"■ {q}\n")
        await ask(q)


if __name__ == "__main__":
    asyncio.run(main())
