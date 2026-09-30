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
    title: str
    url: str
    snippet: str


class Feedback(BaseModel):
    rating: Literal["up", "down"]
