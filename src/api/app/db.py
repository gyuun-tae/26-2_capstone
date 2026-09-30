"""DB 연결. 로컬은 SQLite, 배포는 DATABASE_URL에 PostgreSQL(Neon) 주소를 넣는다."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
# Neon이 주는 postgresql:// 주소를 그대로 붙여넣어도 psycopg(v3) 드라이버를 쓰게 한다
for prefix in ("postgresql://", "postgres://"):
    if DATABASE_URL.startswith(prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix(prefix)

# pool_pre_ping: Neon은 쉬는 동안 연결을 끊으므로, 쓰기 전에 살아있는지 확인하고 다시 연결한다
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 의존성: 요청마다 세션을 열고 닫는다."""
    with SessionLocal() as db:
        yield db
