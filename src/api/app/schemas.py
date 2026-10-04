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
    date_status: str  # not_displayed / page_updated / conflicting / unverified_attachment / official_api_current(법령·고시)
    effective_at: str | None = None  # 법령·고시의 시행일 (국가법령정보 API). 그 밖의 문서는 None
    fetched_at: str | None  # 수집 시각
    snippet: str


# answer: 답변 / clarify: 조건 확인 필요 / unknown: 근거 없음(확인 불가). 오류는 SSE error 이벤트로 보낸다
AnswerType = Literal["answer", "clarify", "unknown"]


class Action(BaseModel):
    """다음 행동 버튼·카드 (v0.2).
    url·phone은 LLM이 만들지 않는다. 근거 메타데이터나 app/actions.py의 고정 목록에서만 채운다."""
    type: Literal["link", "download", "contact"]
    label: str  # "Port-MIS 열기", "선박입항신고서(HWP)", "항만운영팀"
    url: str | None = None  # link, download
    phone: str | None = None  # contact
    note: str | None = None  # "로그인 필요", "평일 09~18시"
    source_ref: int | None = Field(default=None, ge=1)  # 근거가 된 sources 번호(1부터). 고정 링크면 None

    @model_validator(mode="after")
    def has_target(self):
        if self.type in ("link", "download") and not (self.url or "").startswith("https://"):
            raise ValueError(f"{self.type}에는 https:// 주소가 필요합니다")
        if self.type == "contact" and not self.phone:
            raise ValueError("contact에는 phone이 필요합니다")
        return self


class Option(BaseModel):
    """clarify 선택지 (v0.2). FE는 누른 label을 다음 user 메시지로 보낸다."""
    label: str = Field(min_length=1, max_length=50)


class Done(BaseModel):
    """SSE done 이벤트의 data"""
    message_id: int
    answer_type: AnswerType
    actions: list[Action] = []
    options: list[Option] = []  # answer_type이 clarify일 때만 채운다


class Feedback(BaseModel):
    rating: Literal["up", "down"]
