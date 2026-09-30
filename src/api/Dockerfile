FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app

# root가 아닌 사용자로 실행, data/(SQLite·Chroma)만 쓰기 허용
RUN mkdir data && chown 1000 data
USER 1000

ENV PATH="/app/.venv/bin:$PATH"
# Render는 PORT 환경변수로 포트를 알려준다 (로컬 기본 8000)
CMD fastapi run app/main.py --host 0.0.0.0 --port ${PORT:-8000}
