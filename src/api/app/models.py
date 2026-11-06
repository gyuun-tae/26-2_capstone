"""DB 테이블. 사용자 정보 없이 질문·답변·피드백만 익명으로 남긴다.
새 열은 nullable로만 추가한다 (db.add_missing_columns가 기존 테이블에 자동으로 붙인다)."""
from datetime import datetime

from sqlalchemy import JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON)
    feedback: Mapped[str | None]  # "up" / "down" / None
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # answer / clarify / unknown / error. 이 열이 생기기 전의 로그는 None
    answer_type: Mapped[str | None]
    error: Mapped[str | None] = mapped_column(Text)  # 실패한 대화의 오류 종류 (예: RuntimeError)
    # 단계별 걸린 시간(초): embed_s·search_s·rerank_s·gate_s·llm_s·first_token_s·total_s (거친 단계만). 이 열 전·mock은 None
    timings: Mapped[dict | None] = mapped_column(JSON)
