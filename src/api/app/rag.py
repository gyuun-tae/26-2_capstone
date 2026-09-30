"""AI 팀 RAG 파이프라인과의 접점. 지금은 가짜(mock) 답변을 돌려준다.

AI 팀과 합의할 인터페이스:
    answer(messages) -> Answer
    - sources: 검색된 근거 목록 (없으면 빈 목록). 순서가 곧 인용 번호 [1], [2] ...
    - tokens: 답변 조각을 차례로 내놓는 async iterator
      답변 서식(v0.2): 요약 한두 문장 → 빈 줄 → "1." 번호 목록. 근거를 쓴 문장 끝에 [n]
    - answer_type, actions, options: tokens를 다 읽은 뒤 확정된 값을 읽는다 (생성 결과에 따라 정해질 수 있어서)
      actions의 url·phone은 LLM이 만들지 않는다. 근거 메타데이터나 app/actions.py에서만 채운다
    생성 중 실패하면 tokens에서 예외를 던진다.

FE 화면 확인용: 질문에 아래 문구를 넣으면 해당 상태를 흉내 낸다.
    "테스트:조건" → clarify(+options), "테스트:확인불가" → unknown(근거 없음, +contact), "테스트:오류" → error 이벤트
"""
import asyncio
import re
from dataclasses import dataclass, field
from typing import AsyncIterator

from app.actions import PORT_MIS
from app.schemas import Action, AnswerType, Message, Option, Source

NOTE = "(※ 테스트용 가짜 답변입니다)"
MOCK_ANSWERS = {
    "answer": (
        f"민원은 여수광양항만공사 누리집의 민원신청 메뉴에서 신청할 수 있습니다[1]. {NOTE}\n\n"
        "1. 누리집 민원신청 메뉴에서 신청서 작성[1]\n"
        "2. 항만시설 출입업체 등록은 신청서(HWP)를 내려받아 작성[2]\n"
        "3. 처리 결과 확인[1]\n"
    ),
    "clarify": f"이용하시려는 항만시설에 따라 절차가 다릅니다. 어느 쪽인가요? {NOTE}",
    "unknown": f"확인한 공식 자료만으로는 답을 확정하기 어렵습니다. 담당 부서를 통해 확인해 주세요. {NOTE}",
}
MOCK_SOURCES = [
    Source(
        doc_id="YGPA-001",
        chunk_id="YGPA-001-mock-0001",
        title="민원신청안내",
        source_url="https://www.ygpa.or.kr/hmpg/ygpa/mwse/onmw/mwgu/contPageDetail.do?conts_no=69ABE2DCEF294D449FCE2A530341F15D",
        locator="본문 1~15행",
        published_at=None,
        updated_at=None,
        date_status="not_displayed",
        fetched_at="2026-09-27T10:00:00+09:00",
        snippet="민원 신청 자격 및 4단계 신청 절차...",
    ),
    Source(
        doc_id="YGPA-023",
        chunk_id="YGPA-023-mock-0001",
        title="항만시설출입업체등록신청서",
        source_url="https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000007123",
        locator="신청서 1쪽",
        published_at=None,
        updated_at=None,
        date_status="unverified_attachment",
        fetched_at="2026-09-27T10:00:00+09:00",
        snippet="항만시설 출입업체 등록 신청서 서식...",
    ),
]
MOCK_ACTIONS = {
    "answer": [
        # 서식 링크는 근거(sources[1])의 원문 URL에서 가져온다
        Action(type="download", label="항만시설출입업체등록신청서(HWP)", url=MOCK_SOURCES[1].source_url, source_ref=2),
        PORT_MIS,
    ],
    "clarify": [],
    "unknown": [Action(type="contact", label="여수광양항만공사 (테스트용)", phone="061-000-0000", note="테스트용 가짜 번호")],
}
MOCK_OPTIONS = {"clarify": [Option(label="여객 터미널"), Option(label="화물 부두"), Option(label="잘 모르겠어요")]}


@dataclass
class Answer:
    sources: list[Source]
    tokens: AsyncIterator[str]
    answer_type: AnswerType = "answer"
    actions: list[Action] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)


def answer(messages: list[Message]) -> Answer:
    q = messages[-1].content
    kind: AnswerType = "clarify" if "테스트:조건" in q else "unknown" if "테스트:확인불가" in q else "answer"
    result = Answer(sources=MOCK_SOURCES if kind == "answer" else [], tokens=None)

    async def tokens():
        # 단어 + 뒤따르는 공백·줄바꿈 단위로 흘려보내 서식을 유지한다
        for i, piece in enumerate(re.findall(r"\S+\s*", MOCK_ANSWERS[kind])):
            if i == 3 and "테스트:오류" in q:
                raise RuntimeError("mock 생성 실패")
            await asyncio.sleep(0.05)  # 실제 LLM처럼 조금씩 흘려보내기
            yield piece
        # 실제 RAG에서는 생성이 끝난 뒤 정해질 수 있다
        result.answer_type = kind
        result.actions = MOCK_ACTIONS[kind]
        result.options = MOCK_OPTIONS.get(kind, [])

    result.tokens = tokens()
    return result
