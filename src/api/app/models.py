"""DB 테이블. 사용자 정보 없이 질문·답변·피드백만 익명으로 남긴다."""
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
