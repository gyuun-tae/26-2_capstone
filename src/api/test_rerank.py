"""검색 후보 재정렬 확인 (GPU 없이 가짜 점수로): uv run python test_rerank.py"""
import asyncio
import os
import tempfile
from unittest.mock import patch

tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
os.environ["CHROMA_PATH"] = f"{tmp}/chroma"
os.environ["RAG_MODE"] = "real"
os.environ["RAG_RERANK"] = "on"

from app import gpu, rag_real, rerank, search  # noqa: E402
from app.schemas import Message  # noqa: E402
from test_sources import html_text  # noqa: E402


def hit(doc, score, kind="article", text=None):
    return {"chunk": html_text | {"chunk_id": f"{doc}-{score}", "doc_id": doc, "chunk_kind": kind, "text": text or doc},
            "score": score}


def ids(hits):
    return [h["chunk"]["chunk_id"] for h in hits]


def fake_rerank(scores):
    async def f(query, documents, timeout, truncate=None):
        f.calls.append(documents)
        return [scores.get(d, 0.0) for d in documents]
    f.calls = []
    return f


# 1. 벡터 순서 선택은 SQL과 같은 법령 상한: 법령 조문은 2개까지, 법령 서식은 세지 않는다
pool = [hit("LAW-1", 0.70), hit("LAW-2", 0.69), hit("LAW-3", 0.68), hit("LAW-9", 0.67, "whole_form"), hit("YGPA-1", 0.60),
        hit("YGPA-2", 0.59), hit("YGPA-3", 0.58)]
assert ids(rerank.by_vector(pool, 5)) == ["LAW-1-0.7", "LAW-2-0.69", "LAW-9-0.67", "YGPA-1-0.6", "YGPA-2-0.59"]
# 법령 서식은 서식끼리 MAX_FORM개까지 (w01: 다른 법령의 "신고서" 서식은 잡음)
forms = [hit("LAW-9", 0.70, "whole_form"), hit("LAW-8", 0.69, "whole_form"), hit("LAW-7", 0.68, "whole_form"),
         hit("YGPA-1", 0.60)]
assert ids(rerank.by_vector(forms, 2)) == ["LAW-9-0.7", "YGPA-1-0.6"]

# 2. 재정렬 점수와 벡터 점수 반반으로 순서를 다시 정한다. 앞 N개만 재정렬, 모자라면 나머지로 채운다
os.environ["RAG_RERANK_N"] = "4"
f = fake_rerank({"LAW-1": 0.1, "LAW-2": 0.9, "LAW-3": 0.95, "LAW-9": 0.8})
with patch.object(gpu, "rerank", f):
    out = asyncio.run(rerank.rerank("q", pool, 5))
assert f.calls == [["LAW-1", "LAW-2", "LAW-3", "LAW-9"]]  # 앞 4개만 GPU로
# LAW-3(0.815)·LAW-2(0.795)·LAW-9(0.735)·LAW-1(0.4 → 법령 상한으로 빠짐) → 남은 자리는 YGPA를 벡터 순서로
assert ids(out) == ["LAW-3-0.68", "LAW-2-0.69", "LAW-9-0.67", "YGPA-1-0.6", "YGPA-2-0.59"], ids(out)
assert out[0]["score"] == 0.68 and out[0]["rerank"] == 0.95  # score는 벡터 유사도 그대로 (확인 불가 기준)
del os.environ["RAG_RERANK_N"]


# 3. 재정렬이 실패하면 벡터 순서
async def broken(*a, **kw):
    raise gpu.GpuError("재정렬 실패 502")
with patch.object(gpu, "rerank", broken):
    assert ids(asyncio.run(rerank.rerank("q", pool, 5))) == ids(rerank.by_vector(pool, 5))

# 4. 조립: 후보를 넉넉히(2N, 법령 상한 없이) 받고, 확인 불가가 아니면 재정렬 순서로 근거를 만든다
calls = []


def fake_search(vector, k, question="", max_law=None):
    calls.append((k, max_law))
    return pool


async def fake_embed(text):
    return [0.1] * 1024


async def fake_chat(messages, max_tokens, temperature, model=None):
    yield '답[1]\n@@META {"type": "answer"}'


async def run(question):
    result = rag_real.answer([Message(role="user", content=question)])
    text = "".join([p async for p in result.tokens])
    return result, text

f = fake_rerank({"LAW-1": 0.1, "LAW-2": 0.9, "LAW-3": 0.95, "LAW-9": 0.8, "YGPA-1": 1.0})  # 반반: LAW-3 0.815, YGPA-1 0.8, LAW-2 0.795
with patch.object(gpu, "embed", fake_embed), patch.object(gpu, "chat_stream", fake_chat), \
        patch.object(search, "search", fake_search), patch.object(gpu, "rerank", f):
    result, _ = asyncio.run(run("선박 입항 신고는 어떻게 하나요?"))
assert calls == [(20, 20)], calls
assert [s.chunk_id for s in result.sources][:3] == ["LAW-3-0.68", "YGPA-1-0.6", "LAW-2-0.69"], [s.chunk_id for s in result.sources]

# 5. 확인 불가(벡터 1위가 기준 미만)면 재정렬을 부르지 않는다
weak_pool = [hit("YGPA-1", 0.30), hit("YGPA-2", 0.29)]
f = fake_rerank({})
with patch.object(gpu, "embed", fake_embed), patch.object(gpu, "chat_stream", fake_chat), \
        patch.object(search, "search", lambda v, k, q="", max_law=None: weak_pool), patch.object(gpu, "rerank", f):
    result, _ = asyncio.run(run("오늘 날씨 어때요?"))
assert result.answer_type == "unknown" and f.calls == []

# 6. RAG_RERANK=off면 지금까지처럼 상위 k개만 받는다
os.environ["RAG_RERANK"] = "off"
calls.clear()
with patch.object(gpu, "embed", fake_embed), patch.object(gpu, "chat_stream", fake_chat), \
        patch.object(search, "search", fake_search), patch.object(gpu, "rerank", broken):
    asyncio.run(run("선박 입항 신고는 어떻게 하나요?"))
assert calls == [(5, None)], calls

print("OK")
