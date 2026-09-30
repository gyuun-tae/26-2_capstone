"""SQLite 연결. DATABASE_URL만 바꾸면 PostgreSQL로 전환된다."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 의존성: 요청마다 세션을 열고 닫는다."""
    with SessionLocal() as db:
        yield db
