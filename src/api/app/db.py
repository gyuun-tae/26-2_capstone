"""DB 연결. 로컬은 SQLite, 배포는 DATABASE_URL에 PostgreSQL(Neon) 주소를 넣는다."""
import os

from sqlalchemy import create_engine, inspect, text
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


def add_missing_columns():
    """create_all은 이미 있는 테이블에 새 열을 추가하지 않는다. 모델에는 있고 DB에는 없는 열만 추가한다.
    ponytail: nullable 열 추가만 처리. 열 이름·타입 변경이 필요해지면 Alembic으로 옮길 것"""
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}"))


def get_db():
    """FastAPI 의존성: 요청마다 세션을 열고 닫는다."""
    with SessionLocal() as db:
        yield db
