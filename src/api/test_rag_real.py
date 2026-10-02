"""실제 RAG 조립 확인 (GPU·DB 없이 가짜 응답으로): uv run python test_rag_real.py"""
import json
import os
import tempfile
from unittest.mock import patch

tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
os.environ["CHROMA_PATH"] = f"{tmp}/chroma"
os.environ["RAG_MODE"] = "real"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import gpu, prompt, rag_real, search  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ChatLog  # noqa: E402
from app.schemas import Message  # noqa: E402
from test_sources import form, html_text  # noqa: E402

c = TestClient(app)
HITS = [{"chunk": html_text | {"chunk_id": "h1"}, "score": 0.7}, {"chunk": form | {"chunk_id": "f1"}, "score": 0.6}]
calls = {"embed": [], "chat": []}


def run(question, llm_pieces, hits=HITS, history=()):
    """가짜 임베딩·검색·생성으로 /chat을 호출해 [(이벤트, 데이터)]를 돌려준다"""
    async def fake_embed(text):
        calls["embed"].append(text)
        return [0.1] * 1024

    async def fake_chat(messages, max_tokens, temperature):
        calls["chat"].append(messages)
        for p in llm_pieces:
            if isinstance(p, Exception):
                raise p
            yield p

    msgs = [*history, {"role": "user", "content": question}]
    with patch.object(gpu, "embed", fake_embed), patch.object(gpu, "chat_stream", fake_chat), \
            patch.object(search, "search", lambda v, k: hits):
        body = c.post("/chat", json={"messages": msgs}).text
    return [(b.split("\n")[0].removeprefix("event: "), json.loads(b.split("\n")[1].removeprefix("data: ")))
            for b in body.strip().split("\n\n")]


def text_of(events):
    return "".join(d["text"] for e, d in events if e == "token")


# 1. 답변: 정리 줄이 여러 조각에 걸쳐 와도 화면에 나가지 않고, 인용된 서식 버튼 + 고른 고정 링크가 붙는다
ev = run("선박제원 신고는 어떻게 하나요?", ["회원가입 후 신청합니다[1].\n\n1. 신고서 작성[2]\n", "@@", "ME",
                                     'TA {"type": "answer", "options": [], "actions": ["port_mis", "없는이름"]}'])
assert [e for e, _ in ev][-2:] == ["sources", "done"], ev
assert "@" not in text_of(ev) and text_of(ev).startswith("회원가입"), text_of(ev)
sources, done = ev[-2][1], ev[-1][1]
assert [s["chunk_id"] for s in sources] == ["h1", "f1"]
assert done["answer_type"] == "answer" and done["options"] == []
assert [(a["type"], a.get("source_ref")) for a in done["actions"]] == [("download", 2), ("link", None)], done["actions"]
msgs = calls["chat"][-1]
assert msgs[0]["role"] == "system" and "port_mis" in msgs[0]["content"]
assert "[1] 문서 · 신청자격 · 신청절차" in msgs[-1]["content"] and "[2] 선박제원신고서 · 서식 전체" in msgs[-1]["content"]
with SessionLocal() as db:
    log = db.scalars(select(ChatLog).order_by(ChatLog.id.desc())).first()
    assert "@@META" not in log.answer and log.answer_type == "answer"

# 2. 인용되지 않은 서식은 버튼을 만들지 않는다
done = run("민원 신청 방법", ["회원가입 후 신청합니다[1].", '@@META {"type": "answer"}'])[-1][1]
assert done["actions"] == [], done

# 3. 되묻기: 선택지는 clarify일 때만, 버튼 없음
done = run("사용료가 얼마인가요?", ["어느 시설인가요?\n", '@@META {"type": "clarify", "options": ["부두", "체육시설"], "actions": ["port_mis"]}'])[-1][1]
assert done["answer_type"] == "clarify" and [o["label"] for o in done["options"]] == ["부두", "체육시설"] and done["actions"] == []

# 4. 정리 줄이 없거나 깨지면 일반 답변 (본문은 그대로)
ev = run("민원 신청 방법", ["회원가입 후 ", "신청합니다[1]."])
assert ev[-1][1]["answer_type"] == "answer" and text_of(ev) == "회원가입 후 신청합니다[1]."
assert run("민원 신청 방법", ["답[1]", "@@META {깨짐"])[-1][1]["answer_type"] == "answer"

# 5. 1위 점수가 기준보다 낮으면 LLM을 부르지 않고 unknown, 근거 없음
n = len(calls["chat"])
ev = run("오늘 날씨 어때?", ["부르면 안 됨"], hits=[{"chunk": html_text, "score": 0.40}])
assert ev[-1][1]["answer_type"] == "unknown" and ev[-2][1] == [] and len(calls["chat"]) == n
assert text_of(ev) == rag_real.UNKNOWN_TEXT
assert run("x", ["부르면 안 됨"], hits=[])[-1][1]["answer_type"] == "unknown"
# LLM이 근거로 답할 수 없다고 판단해도 근거·버튼을 보여주지 않는다
ev = run("부산항 운영사는?", ["확인이 어렵습니다.", '@@META {"type": "unknown", "actions": ["port_mis"]}'])
assert ev[-1][1]["answer_type"] == "unknown" and ev[-2][1] == [] and ev[-1][1]["actions"] == []

# 6. 생성 도중 실패 → error 이벤트 (done 없음), 오류 로그
ev = run("민원 신청 방법", ["회원가입", RuntimeError("터널 끊김")])
assert ev[-1][0] == "error" and "done" not in [e for e, _ in ev]

# 7. 짧은 답(선택지)은 앞 질문을 붙여 검색, 긴 질문은 그대로
run("체육시설", ['답[1]\n@@META {"type": "answer"}'], history=[
    {"role": "user", "content": "사용료가 얼마인가요?"}, {"role": "assistant", "content": "어느 시설인가요?"}])
assert calls["embed"][-1] == "사용료가 얼마인가요?\n체육시설", calls["embed"][-1]
assert rag_real.search_query([Message(role="user", content="항만시설 사용 신청은 어떻게 하나요?")]) == "항만시설 사용 신청은 어떻게 하나요?"

# 8. 표식 거르기 단위 확인: 표식과 비슷하지만 아닌 글자는 그대로 내보낸다
f = prompt.MetaFilter()
assert f.feed("이메일 @") == "이메일 " and f.feed("표시") == "@표시" and f.flush() == ""
assert prompt.violations("자세한 건 https://x.kr 또는 061-123-4567 [3]", 2) == ["url_or_phone", "bad_citation"]
assert prompt.violations("정상 답변[1][2]", 2) == []

# 9. 설정이 없으면 오류 이벤트 (조용히 mock으로 넘어가지 않는다)
os.environ.pop("GPU_URL", None)
body = c.post("/chat", json={"messages": [{"role": "user", "content": "민원 신청"}]}).text
assert "event: error" in body

print("OK")
