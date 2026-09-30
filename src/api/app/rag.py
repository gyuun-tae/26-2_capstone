"""AI 팀 RAG 파이프라인과의 접점. 지금은 가짜(mock) 답변을 돌려준다.

AI 팀과 합의할 인터페이스:
    answer(messages) -> (sources, 답변 조각을 차례로 내놓는 async iterator)
"""
import asyncio

from app.schemas import Message, Source

MOCK_ANSWER = (
    "광양항 자유무역지역 입주를 신청하려면 사업계획서, 법인 등기부등본, "
    "수출입 실적 증명서가 필요합니다. (※ 테스트용 가짜 답변입니다)"
)
MOCK_SOURCES = [
    Source(
        title="자유무역지역 입주 안내 (예시)",
        url="https://www.ygpa.or.kr",
        snippet="입주 자격 및 제출 서류에 관한 안내...",
    )
]


def answer(messages: list[Message]):
    async def tokens():
        for word in MOCK_ANSWER.split(" "):
            await asyncio.sleep(0.05)  # 실제 LLM처럼 조금씩 흘려보내기
            yield word + " "

    return MOCK_SOURCES, tokens()
