"""AI 팀 RAG 파이프라인과의 접점. 지금은 가짜(mock) 답변을 돌려준다.

AI 팀과 합의할 인터페이스:
    answer(messages) -> Answer
    - sources: 검색된 근거 목록 (없으면 빈 목록)
    - tokens: 답변 조각을 차례로 내놓는 async iterator
    - answer_type: tokens를 다 읽은 뒤 확정된 값을 읽는다 (생성 결과에 따라 정해질 수 있어서)
    생성 중 실패하면 tokens에서 예외를 던진다.

FE 화면 확인용: 질문에 아래 문구를 넣으면 해당 상태를 흉내 낸다.
    "테스트:조건" → clarify, "테스트:확인불가" → unknown(근거 없음), "테스트:오류" → error 이벤트
"""
import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

from app.schemas import AnswerType, Message, Source

MOCK_ANSWERS = {
    "answer": "민원은 여수광양항만공사 누리집의 민원신청 메뉴에서 신청할 수 있습니다. (※ 테스트용 가짜 답변입니다)",
    "clarify": "어떤 시설을 이용하시려는지에 따라 절차가 다릅니다. 이용하실 항만시설을 알려주세요. (※ 테스트용 가짜 답변입니다)",
    "unknown": "공식 자료에서 확인할 수 없는 내용입니다. 여수광양항만공사에 직접 문의해 주세요. (※ 테스트용 가짜 답변입니다)",
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
    )
]


@dataclass
class Answer:
    sources: list[Source]
    tokens: AsyncIterator[str]
    answer_type: AnswerType = "answer"


def answer(messages: list[Message]) -> Answer:
    q = messages[-1].content
    kind: AnswerType = "clarify" if "테스트:조건" in q else "unknown" if "테스트:확인불가" in q else "answer"
    result = Answer(sources=[] if kind == "unknown" else MOCK_SOURCES, tokens=None)

    async def tokens():
        for i, word in enumerate(MOCK_ANSWERS[kind].split(" ")):
            if i == 3 and "테스트:오류" in q:
                raise RuntimeError("mock 생성 실패")
            await asyncio.sleep(0.05)  # 실제 LLM처럼 조금씩 흘려보내기
            yield word + " "
        result.answer_type = kind  # 실제 RAG에서는 생성이 끝난 뒤 정해질 수 있다

    result.tokens = tokens()
    return result
