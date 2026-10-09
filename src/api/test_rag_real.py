"""실제 RAG 조립 확인 (GPU·DB 없이 가짜 응답으로): uv run python test_rag_real.py"""
import json
import os
import tempfile
from unittest.mock import patch

tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
os.environ["CHROMA_PATH"] = f"{tmp}/chroma"
os.environ["RAG_MODE"] = "real"
os.environ["RAG_RERANK"] = "off"  # 재정렬은 test_rerank.py에서

from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import gpu, prompt, rag_real, search  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ChatLog  # noqa: E402
from app.schemas import Message  # noqa: E402
from test_sources import form, html_text  # noqa: E402

c = TestClient(app)
HITS = [{"chunk": html_text | {"chunk_id": "h1", "text": html_text["text"] + "\n- Port-MIS로 신고"}, "score": 0.7},
        {"chunk": form | {"chunk_id": "f1"}, "score": 0.6}]
calls = {"embed": [], "chat": []}


def run(question, llm_pieces, hits=HITS, history=(), embed=None):
    """가짜 임베딩·검색·생성으로 /chat을 호출해 [(이벤트, 데이터)]를 돌려준다"""
    async def fake_embed(text):
        calls["embed"].append(text)
        return [0.1] * 1024

    async def fake_chat(messages, max_tokens, temperature, model=gpu.LLM_MODEL):
        if model != gpu.LLM_MODEL:  # 판정은 이 시험의 답변 조각을 받지 않는다 (판정 시험은 아래 14번)
            yield "있음"
            return
        calls["chat"].append(messages)
        for p in llm_pieces:
            if isinstance(p, Exception):
                raise p
            yield p

    msgs = [*history, {"role": "user", "content": question}]
    with patch.object(gpu, "embed", embed or fake_embed), patch.object(gpu, "chat_stream", fake_chat), \
            patch.object(search, "search", lambda v, k, q="", max_law=None: hits(q) if callable(hits) else hits):
        body = c.post("/chat", json={"messages": msgs}).text
    return [(b.split("\n")[0].removeprefix("event: "), json.loads(b.split("\n")[1].removeprefix("data: ")))
            for b in body.strip().split("\n\n")]


def text_of(events):
    return "".join(d["text"] for e, d in events if e == "token")


# 1. 답변: 정리 줄이 여러 조각에 걸쳐 와도 화면에 나가지 않고, 고른 서식 버튼 + 고른 고정 링크가 붙는다
ev = run("선박제원 신고는 어떻게 하나요?", ["회원가입 후 신청합니다[1].\n\n1. 신고서 작성[2]\n", "@@", "ME",
                                     'TA {"type": "answer", "options": [], "actions": ["port_mis", "없는이름"], "forms": [2]}'])
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

# 1-1. GPU 서버에 닿지 않으면(터널 꺼짐·관문 502) 오류 화면 대신 안내 + 대표전화, 로그에 gpu_unavailable
for failure in (httpx.ConnectError("[Errno -2] Name or service not known"), gpu.GpuError("임베딩 실패 502")):
    async def down(text, failure=failure):
        raise failure
    ev = run("선박 입항 신고는 어떻게 하나요?", ["안 불림"], embed=down)
    assert [e for e, _ in ev] == ["token", "sources", "done"], ev
    assert text_of(ev) == rag_real.GPU_DOWN_TEXT and ev[1][1] == []
    assert ev[-1][1]["answer_type"] == "answer" and [a["label"] for a in ev[-1][1]["actions"]] == ["여수광양항만공사 대표전화"]
    with SessionLocal() as db:
        log = db.scalars(select(ChatLog).order_by(ChatLog.id.desc())).first()
        assert log.error == "gpu_unavailable" and log.answer == rag_real.GPU_DOWN_TEXT

# 2. 서식 버튼은 LLM이 forms로 고르고 본문에도 인용한 서식 청크만. 인용만 됐거나 서식이 아니면 버튼 없음
done = run("민원 신청 방법", ["회원가입 후 신청합니다[1].", '@@META {"type": "answer", "forms": [2]}'])[-1][1]
assert done["actions"] == [], done  # forms에 있지만 본문에 인용 안 됨
done = run("항만공사가 뭐하는 곳이야", ["항만을 운영합니다[1]. 신고서도 있습니다[2].", '@@META {"type": "answer"}'])[-1][1]
assert done["actions"] == [], done  # 서식을 인용했지만 고르지 않음 (설명용 인용)
done = run("민원 신청 방법", ["회원가입 후 신청합니다[1].", '@@META {"type": "answer", "forms": [1, "2", true]}'])[-1][1]
assert done["actions"] == [], done  # [1]은 서식 청크가 아님, 숫자가 아닌 값은 무시

# 2-1. 근거에 Port-MIS가 없으면 LLM이 골라도 버튼을 붙이지 않는다
other = [{"chunk": form | {"chunk_id": "f1"}, "score": 0.6}]
done = run("서식 있나요?", ["서식이 있습니다[1].", '@@META {"type": "answer", "actions": ["port_mis"], "forms": [1]}'], hits=other)[-1][1]
assert [a["type"] for a in done["actions"]] == ["download"], done["actions"]
# 법령 서식(scripts/27): 버튼 이름은 법령 이름이 아니라 서식 이름
law_form = form | {"chunk_id": "lf1", "title": "선박입출항법 시행규칙", "form_title": "내항선 출입 신고서",
                   "text": "[별지 제1호서식] 내항선 출입 신고서\n온라인 신청: 항만운영정보시스템(Port-MIS)에서도 신청할 수 있습니다."}
done = run("출입 신고서 어디서 받아요?", ["내항선 출입 신고서를 씁니다[1].", '@@META {"type": "answer", "actions": ["port_mis"], "forms": [1]}'],
           hits=[{"chunk": law_form, "score": 0.6}])[-1][1]
assert [a["label"] for a in done["actions"]] == ["내항선 출입 신고서(HWP)", "Port-MIS 열기"], done["actions"]
# 그 서식을 인용하면 LLM이 port_mis를 고르지 않아도 Port-MIS 링크 (w01). 인용하지 않으면 붙이지 않는다
done = run("출입 신고서 어디서 받아요?", ["국가법령정보센터에서 받습니다[1].", '@@META {"type": "answer", "actions": [], "forms": []}'],
           hits=[{"chunk": law_form, "score": 0.6}])[-1][1]
assert [a["label"] for a in done["actions"]] == ["Port-MIS 열기"], done["actions"]
done = run("출입 신고서 어디서 받아요?", ["다른 근거입니다[2].", '@@META {"type": "answer", "actions": [], "forms": []}'],
           hits=[{"chunk": law_form, "score": 0.6}, {"chunk": form | {"chunk_id": "f2"}, "score": 0.6}])[-1][1]
assert "Port-MIS 열기" not in [a["label"] for a in done["actions"]], done["actions"]

# 2-3. 정리 줄 항목을 본문 줄로 따로 적어도("forms: [1]") 화면에 나가지 않고, 뒤의 @@META를 읽는다. 중국식 마침표는 바꾼다
ev = run("서식", ["서식이 있습니다[2]。\n", "forms: [2]\n", '@@META {"type": "answer", "forms": [2]}'])
assert text_of(ev) == "서식이 있습니다[2].", repr(text_of(ev))
assert [a["type"] for a in ev[-1][1]["actions"]] == ["download"], ev[-1][1]
assert prompt.parse_meta(' {"type": "clarify", "options": ["a", "b"]} 뒤에 글').kind == "clarify"
assert prompt.parse_meta(" [1, 2]").kind == "answer"
# 실제 Qwen 출력 (10/10 a13·w01): 번호를 문자로, 같은 항목을 두 번 → 서식 버튼이 사라지던 경우
assert prompt.parse_meta(' {"type": "answer", "actions": [], "forms": ["1"]}').forms == [1]
assert prompt.parse_meta(' {"type": "answer", "forms": [1], "forms": ["1"]}').forms == [1]
assert prompt.parse_meta(' {"type": "answer", "actions": ["port_mis"], "forms": [1], "forms": []}').forms == [1]
assert prompt.parse_meta(' {"type": "answer", "forms": [true, "x", 2]}').forms == [2]
assert prompt.parse_meta(' {"type": "unknown", "type": "answer"}').kind == "unknown"

# 2-4. 날짜를 물었는데 답에 날짜·요일·숫자가 없으면 끝에 안내 + 대표전화. 날짜가 있으면 붙이지 않는다
ev = run("입주기업 모집 가장 최근이 언제야?", ["모집 절차는 모집, 선정, 계약 순입니다[1].", '@@META {"type": "answer"}'])
assert text_of(ev).endswith(rag_real.DATE_NOTE) and ev[-1][1]["actions"][-1]["label"] == "여수광양항만공사 대표전화"
ev = run("홍보관은 언제 열어요?", ["매주 월~금요일에 엽니다[1].", '@@META {"type": "answer"}'])
assert rag_real.DATE_NOTE not in text_of(ev)
assert not rag_real.missing_date("며칠 안에 내야 해요?", "출항일로부터 7일 이내[1]")
assert not rag_real.missing_date("서류가 뭐예요?", "신청서를 냅니다[1]")
assert rag_real.missing_date("모집 언제야?", "절차입니다[1].\n\n1. 입주기업 모집\n2. 우선협상 대상자 선정")  # 목록 번호는 날짜가 아님

# 2-2. 선택지 없는 되묻기는 일반 답변으로 본다
assert run("민원 신청", ["답[1]", '@@META {"type": "clarify", "options": []}'])[-1][1]["answer_type"] == "answer"

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
# 점수가 낮아도 질문의 영문 용어가 근거에 그대로 있으면 LLM이 판단한다 (의미 검색이 약어 질문에 약함)
term = [{"chunk": html_text | {"text": "Port-MIS란 해운항만물류정보시스템을 말한다."}, "score": 0.41}]
n = len(calls["chat"])
assert run("Port-MIS가 뭐예요?", ["정보시스템입니다[1].", '@@META {"type": "answer"}'], hits=term)[-1][1]["answer_type"] == "answer"
assert len(calls["chat"]) == n + 1
assert run("BTS 멤버 알려줘", ["부르면 안 됨"], hits=term)[-1][1]["answer_type"] == "unknown"
# LLM이 근거로 답할 수 없다고 판단하면 근거·링크 대신 대표전화만 보여준다 (조기 판단도 같음)
MAIN = {"type": "contact", "label": "여수광양항만공사 대표전화", "url": None, "phone": "061-797-4300",
        "note": "담당 부서를 모를 때", "source_ref": None}
ev = run("부산항 운영사는?", ["확인이 어렵습니다.", '@@META {"type": "unknown", "actions": ["port_mis"]}'])
assert ev[-1][1]["answer_type"] == "unknown" and ev[-2][1] == [] and ev[-1][1]["actions"] == [MAIN], ev[-1][1]
assert run("오늘 날씨", ["부르면 안 됨"], hits=[{"chunk": html_text, "score": 0.40}])[-1][1]["actions"] == [MAIN]

# 답에서 인용한 문서에 담당 연락처가 있으면 연락처 버튼 (contacts.json, 같은 이름·번호는 한 번만). 되묻기는 없음
lost = [{"chunk": form | {"chunk_id": "g1", "doc_id": "YGPA-022", "title": "출입증분실경위서"}, "score": 0.7},
        {"chunk": form | {"chunk_id": "g2", "doc_id": "YGPA-025", "title": "항만상시출입증발급신청서"}, "score": 0.6}]
acts = run("출입증 분실", ["경위서를 냅니다[1][2].", '@@META {"type": "answer", "forms": [1]}'], hits=lost)[-1][1]["actions"]
assert [(a["type"], a["label"], a.get("phone")) for a in acts] == [
    ("download", "출입증분실경위서(HWP)", None),
    ("contact", "항만출입증 담당자 (광양)", "061-797-4434"), ("contact", "항만출입증 담당자 (여수)", "061-692-4336")], acts
assert run("출입증", ["어떤 출입증인가요?", '@@META {"type": "clarify", "options": ["발급", "연장"]}'],
           hits=lost)[-1][1]["actions"] == []

# 6. 생성 도중 실패 → error 이벤트 (done 없음), 오류 로그
ev = run("민원 신청 방법", ["회원가입", RuntimeError("터널 끊김")])
assert ev[-1][0] == "error" and "done" not in [e for e, _ in ev]

# 7. 짧은 답(선택지)은 앞 질문을 붙여 검색, 긴 질문은 그대로
run("체육시설", ['답[1]\n@@META {"type": "answer"}'], history=[
    {"role": "user", "content": "사용료가 얼마인가요?"}, {"role": "assistant", "content": "어느 시설인가요?"}])
assert calls["embed"][-1] == "사용료가 얼마인가요?\n체육시설", calls["embed"][-1]
assert "사용료가 얼마인가요?\n(앞 질문에 대한 사용자의 선택: 체육시설)" in calls["chat"][-1][-1]["content"]
# 앞 답이 되묻기가 아니면 '이어지는 질문'으로 붙인다 (h26)
run("담당 부서가 어디야?", ['답[1]\n@@META {"type": "answer"}'], history=[
    {"role": "user", "content": "입주기업 모집 가장 최근이 언제야?"},
    {"role": "assistant", "content": "확인한 공식 자료만으로는 답을 확정하기 어렵습니다."}])
assert "입주기업 모집 가장 최근이 언제야?\n(이어지는 질문: 담당 부서가 어디야?)" in calls["chat"][-1][-1]["content"]

# 7-1-1. 긴 질문이라도 혼자서 근거가 약하면 앞 질문을 붙여 다시 찾고, 그래야 근거가 잡히면 이어지는 질문으로 답한다
weak = [h | {"score": 0.4} for h in HITS]
follow = [{"role": "user", "content": "출입 신고서는 어디서 볼 수 있어?"}, {"role": "assistant", "content": "관리청에 제출합니다[1]."}]
ev = run("이 사이트에서 서식을 얻을 수 없는거야?", ['답[1]\n@@META {"type": "answer"}'],
         hits=lambda q: HITS if "출입 신고서" in q else weak, history=follow)
assert calls["embed"][-2:] == ["이 사이트에서 서식을 얻을 수 없는거야?", "출입 신고서는 어디서 볼 수 있어?\n이 사이트에서 서식을 얻을 수 없는거야?"]
assert "(이어지는 질문: 이 사이트에서 서식을 얻을 수 없는거야?)" in calls["chat"][-1][-1]["content"]
assert ev[-1][1]["answer_type"] == "answer"
# 붙여도 약하면 LLM 없이 확인 불가
n_chat = len(calls["chat"])
ev = run("오늘 여수 날씨 어때요 알려 주세요?", ["안 불림"], hits=weak, history=follow)
assert ev[-1][1]["answer_type"] == "unknown" and len(calls["chat"]) == n_chat

# 7-2. 근거에 '※ … 제한' 공지가 있으면 질문 옆에 짚어 준다 (없으면 붙이지 않는다)
notice = [{"chunk": html_text | {"chunk_id": "n1", "text": "※ 경보 해제 시까지 예약이 제한됩니다.\n예약 안내"}, "score": 0.7}]
run("홍보관 예약", ['답[1]\n@@META {"type": "answer"}'], hits=notice)
assert '(주의: 근거 [1]에 이용 제한 공지가 있습니다 — "※ 경보 해제 시까지 예약이 제한됩니다."' in calls["chat"][-1][-1]["content"]
run("민원 신청", ['답[1]\n@@META {"type": "answer"}'])
assert "주의:" not in calls["chat"][-1][-1]["content"]

# 7-3. 근거에 없는 연락처는 가리고, 근거에 글자 그대로 있는 것은 둔다 (조각이 나뉘어 와도)
phone = [{"chunk": html_text | {"chunk_id": "p1", "text": "문의: 061-797-4550, play@ygpm.co.kr"}, "score": 0.7}]
ev = run("문의처", ["문의는 061-797-", "4550 또는 play@ygpm.co.kr[1]. 다른 번호 010-1234-5678, ",
                   "https://fake.example.com 참고[1].", '\n@@META {"type": "answer"}'], hits=phone)
t = text_of(ev)
assert "061-797-4550" in t and "play@ygpm.co.kr[1]." in t, t
assert "010-1234-5678" not in t and "fake.example" not in t and t.count(prompt.MASK) == 2, t

# 7-4. 근거 개수를 넘는 번호는 지우고(조각이 나뉘어 와도), 맞는 번호·[별지3]·[] 같은 글자는 둔다
ev = run("Port-MIS 뜻", ["정보시스템입니다[2", "0]. 서식은 〔별지3〕과 [별지4], [] 참고[1]", "[2].", '\n@@META {"type": "answer"}'])
assert text_of(ev) == "정보시스템입니다. 서식은 〔별지3〕과 [별지4], [] 참고[1][2].\n", repr(text_of(ev))
f = prompt.CitationFilter(5)
assert f.feed("끝[") + f.flush() == "끝["

# 7-1. 본문이 확인 불가 문구인데 정리 줄이 answer면 unknown으로 고친다
ev = run("운임 얼마예요?", ["확인한 공식 자료만으로는 답을 확정하기 어렵습니다.", '@@META {"type": "answer"}'])
assert ev[-1][1]["answer_type"] == "unknown" and ev[-2][1] == []
assert rag_real.search_query([Message(role="user", content="항만시설 사용 신청은 어떻게 하나요?")]) == "항만시설 사용 신청은 어떻게 하나요?"

# 8. 표식 거르기 단위 확인: 표식과 비슷하지만 아닌 글자는 그대로 내보낸다
f = prompt.MetaFilter()
assert f.feed("이메일 @") == "이메일 " and f.feed("표시") == "@표시" and f.flush() == ""
assert prompt.violations("자세한 건 https://x.kr 또는 061-123-4567 [3]", 2) == ["url_or_phone", "bad_citation"]
assert prompt.violations("정상 답변[1][2]", 2) == []
assert prompt.violations("Port-MIS로 신고합니다[port_mis].", 2) == ["action_name"]


def filtered(pieces):
    f = prompt.RuleLineFilter()
    return "".join(f.feed(p) for p in pieces) + f.flush()


# 구분선 줄은 조각이 나뉘어 와도 지우고, "- 목록"·문장 안의 ---·굵게는 그대로 둔다
assert filtered(["요약[1].\n\n", "-", "--", "\n", "1. 항목[1]\n", "- 세부\n", "**굵게**[2]\n", "___"]) == \
    "요약[1].\n\n1. 항목[1]\n- 세부\n**굵게**[2]\n"
assert filtered(["a --- b\n", "  - - -  \n", "끝"]) == "a --- b\n끝"
ev = run("민원 신청 방법", ["회원가입 후 신청합니다[1].\n\n---\n", '@@META {"type": "answer"}'])
assert "---" not in text_of(ev) and text_of(ev).startswith("회원가입"), text_of(ev)

# 9. 설정이 없으면 오류 이벤트 (조용히 mock으로 넘어가지 않는다)
os.environ.pop("GPU_URL", None)
body = c.post("/chat", json={"messages": [{"role": "user", "content": "민원 신청"}]}).text
assert "event: error" in body

# 10. 기한이 지난 한시 조항은 근거 머리에 표시한다 (지시문 9번). 아직 남은 기한·없는 날짜는 표시하지 않는다
from datetime import date  # noqa: E402
text = "(11)2024년 12월 31일까지 광양항에 입출항하는 선박\n(12)2030년 1월 1일까지 …\n(13)2024년 2월 30일까지"
assert prompt.expired_until(text, today=date(2026, 10, 3)) == ["2024년 12월 31일까지"]
fee = dict(form, chunk_kind="table", section_titles=["【별표 2】 감면"], text=text)
assert "기한 지난 조항 있음(2024년 12월 31일까지 — 오늘 " in prompt.evidence([{"chunk": fee, "score": 0.7}])
assert "기한 지난" not in prompt.evidence([{"chunk": html_text, "score": 0.7}])

# 11. "[근거]에 … 포함되어 있지 않습니다"는 확인 불가로 본다 (u02). 보통 답은 해당 없음
assert prompt.NO_EVIDENCE.search("[근거]에 부산항 신항 컨테이너 터미널 운영사에 대한 정보는 포함되어 있지 않습니다.")
assert not prompt.NO_EVIDENCE.search("접안료 및 정박료의 최저액은 3,000원입니다[1].")
assert not prompt.NO_EVIDENCE.search("[근거]에 따르면 일정 규모 이상의 선박은 예선을 사용하도록 의무화되어 있습니다[1].")  # l04
assert prompt.NO_EVIDENCE.search("확인한 공식 자료에 부산항 신항 운영사에 대한 정보는 포함되어 있지 않습니다.")
assert not prompt.NO_EVIDENCE.search("확인한 공식 자료만으로는 답을 확정하기 어렵습니다.")

# 11-1. "[근거]" 이름표는 화면에 내보내기 전에 바꾼다 (조각 경계에 걸쳐도)
f = prompt.EvidenceWordFilter()
assert "".join([f.feed("["), f.feed("근"), f.feed("거]에 따르면 [1]"), f.flush()]) == "확인한 공식 자료에 따르면 [1]"
f = prompt.EvidenceWordFilter()
assert f.feed("목록 [") + f.feed("근") + f.flush() == "목록 [근"
ev = run("부산항 신항 운영사는?", ["[근거]에 부산항 신항 운영사 정보는 포함되어 있지 않습니다.", '@@META {"type": "answer"}'])
shown = text_of(ev)
assert "[근거]" not in shown and "확인한 공식 자료에" in shown and ev[-1][1]["answer_type"] == "unknown"

# 12. 한글이 없는 질문에만 언어 안내를 붙인다 (t24)
def last_user(question):
    return prompt.build_messages([Message(role="user", content=question)], [{"chunk": html_text, "score": 0.7}])[-1]["content"]
assert prompt.FOREIGN_NOTE in last_user("How do I get a port access pass?")
assert prompt.FOREIGN_NOTE not in last_user("출입증 발급 신청은 어디서 하나요?")

# 13. 대상이 한정된 문서(통과선박 지침·신청서)는 질문에 '통과'가 있을 때만 검색 후보
assert search.excluded_docs("입항 절차를 알려주세요.") == ["YGPA-028", "YGPA-030"]
assert search.excluded_docs("통과선박으로 인정받으려면?") == []
# 선박 '출입 신고'를 물으면 사람·차량 출입증 서식은 후보에서 뺀다 (r10). 출입증을 함께 말하면 그대로 둔다
assert set(search.PASS_FORMS) <= set(search.excluded_docs("출입 신고서의 구체적인 서식은 따로 볼 수 없는건가?"))
assert set(search.PASS_FORMS) <= set(search.excluded_docs("외항선 출입신고서 양식은 어디서 받아요?"))
assert not set(search.PASS_FORMS) & set(search.excluded_docs("출입증을 잃어버렸는데 어떻게 재발급 받나요?"))
assert not set(search.PASS_FORMS) & set(search.excluded_docs("출입증 말고 선박 출입 신고서는요?"))

# 14. 답변 전 판정(RAG_GATE): 판정 모델(gate-llm)이 없음이면 확인 불가 + 대표전화, 판정이 실패하면 판정 없이 답한다
import asyncio  # noqa: E402

from app import gate  # noqa: E402


def verdict(*pieces):
    async def f(messages, max_tokens, temperature, model=gpu.LLM_MODEL):
        assert model == gate.MODEL
        assert messages[0]["content"] == gate.SYSTEM and "[근거]\n[1]" in messages[1]["content"]
        for p in pieces:
            if isinstance(p, Exception):
                raise p
            yield p
    return f


msgs = [Message(role="user", content="해상 운임은 얼마예요?")]
for pieces, expected in ((["없", "음"], False), (["있음"], True), ([gpu.GpuError("생성 실패 502")], True)):
    with patch.object(gpu, "chat_stream", verdict(*pieces)):
        assert asyncio.run(gate.answerable(msgs, HITS)) is expected, pieces

os.environ["RAG_GATE"] = "on"
def judge(ok, delay=0.0):
    async def f(messages, hits, follow_up=False):
        await asyncio.sleep(delay)
        return ok
    return f


# 판정과 생성은 함께 시작한다. 없음이면 생성한 답은 화면에 하나도 나가지 않는다 (판정이 늦어도)
for delay in (0.0, 0.05):
    with patch.object(gate, "answerable", judge(False, delay)):
        ev = run("해상 운임은 얼마예요?", ["버려질 ", "답 [1]"])
    assert ev[-1][1]["answer_type"] == "unknown" and ev[-1][1]["actions"][0]["type"] == "contact" and ev[-2][1] == []
    assert text_of(ev) == rag_real.UNKNOWN_TEXT, text_of(ev)
# 판정에 넘기는 근거는 기본으로 답변과 같은 길이, gate.CHARS를 정하면 그만큼만 (실험용)
long_hits = [{**HITS[0], "chunk": {**HITS[0]["chunk"], "text": "가" * 2000}}]
assert gate.CHARS is None and "가" * 2000 in gate.build(msgs, long_hits)[1]["content"]
with patch.object(gate, "CHARS", 400):
    assert "가" * 400 + " …(이하 생략)" in gate.build(msgs, long_hits)[1]["content"]
# 있음이면 판정 전에 모아 둔 조각부터 순서대로 전부 나간다 (생성이 판정보다 먼저 끝나도)
with patch.object(gate, "answerable", judge(True, 0.05)):
    ev = run("부두 사용료는요?", ["첫 ", "조각 ", "끝 [1]"])
assert text_of(ev) == "첫 조각 끝 [1]" and ev[-1][1]["answer_type"] == "answer"


async def slow_pieces():
    for p in ("가", "나", "다"):
        await asyncio.sleep(0.02)
        yield p


async def collect(ok, delay):
    return [p async for p in gate.hold(slow_pieces(), lambda: judge(ok, delay)(None, None))]

assert asyncio.run(collect(True, 0.03)) == ["가", "나", "다"]  # 판정이 생성 중간에 나와도 빠짐·중복 없음
assert asyncio.run(collect(True, 0.0)) == ["가", "나", "다"]
for delay in (0.0, 0.01, 0.03):  # 0.0: 첫 조각을 받는 중에 판정이 나옴 → 받던 조각을 취소하고 스트림을 닫아야 한다
    try:
        asyncio.run(collect(False, delay))
        raise AssertionError("Blocked가 나야 함")
    except gate.Blocked:
        pass
del os.environ["RAG_GATE"]

print("OK")
