"""FE와 주고받는 요청/응답 형식 (= API 명세). 바꾸면 FE에 꼭 알릴 것."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    # 창이 열린 뒤의 대화 전체. 마지막이 이번 질문. 최근 10턴(20개)까지만 받는다.
    messages: list[Message] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def last_is_question(self):
        last = self.messages[-1]
        if last.role != "user":
            raise ValueError("마지막 메시지는 user의 질문이어야 합니다")
        if len(last.content) > 1000:
            raise ValueError("질문은 1000자 이하여야 합니다")
        return self


class Source(BaseModel):
    """답변 근거 1개. 필드 이름은 팀 청크 규격(docs/handoff/chunking_001.md)과 같다."""
    doc_id: str
    chunk_id: str
    title: str
    source_url: str
    locator: str  # 화면에 보여줄 근거 위치 문구 (예: "3쪽 표 2")
    published_at: str | None  # 원문에 날짜가 없으면 None. 수집일로 채우지 않는다
    updated_at: str | None
    date_status: str  # not_displayed / page_updated / conflicting / unverified_attachment
    fetched_at: str | None  # 수집 시각
    snippet: str


# answer: 답변 / clarify: 조건 확인 필요 / unknown: 근거 없음(확인 불가). 오류는 SSE error 이벤트로 보낸다
AnswerType = Literal["answer", "clarify", "unknown"]


class Feedback(BaseModel):
    rating: Literal["up", "down"]
