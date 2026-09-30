import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.orm import Session

Path("data").mkdir(exist_ok=True)  # SQLite 파일과 Chroma 폴더 위치

from app import rag  # noqa: E402
from app.db import Base, SessionLocal, add_missing_columns, engine, get_db  # noqa: E402
from app.models import ChatLog  # noqa: E402
from app.schemas import ChatRequest, Done, Feedback  # noqa: E402
from app.vectorstore import client  # noqa: E402

Base.metadata.create_all(engine)
add_missing_columns()  # 기존 테이블(예: Neon)에 새로 생긴 열을 붙인다
logger = logging.getLogger(__name__)

app = FastAPI(title="YGPA RAG 챗봇 API")

app.add_middleware(
    CORSMiddleware,
    # 기본값: FE 로컬 개발 주소 + FE 데모(GitHub Pages)
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,https://dlghskgmll.github.io"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    client.heartbeat()  # Chroma가 살아있는지 확인
    return {"status": "ok"}


def save_error_log(question: str, partial_answer: str, sources: list, error: str):
    """실패한 대화도 평가용으로 남긴다. DB 자체가 원인이면 저장도 실패하므로 서버 로그만 남기고 넘어간다."""
    try:
        with SessionLocal() as db:
            db.add(ChatLog(question=question, answer=partial_answer, sources=sources, answer_type="error", error=error[:1000]))
            db.commit()
    except Exception:
        logger.exception("오류 로그 저장 실패")


@app.post("/chat", response_class=EventSourceResponse)
async def chat(req: ChatRequest):
    """SSE로 token(답변 조각) → sources(근거 문서, 순서 = 인용 번호) → done(로그 id, 응답 유형, actions, options) 순서로 보낸다.
    검색·생성·로그 저장 중 어디서든 실패하면 done 대신 error를 보내고 끝낸다.
    (FE는 done 또는 error를 받아야 로딩을 멈출 수 있다)"""
    question = req.messages[-1].content
    parts, sources = [], []
    try:
        result = rag.answer(req.messages)
        async for text in result.tokens:
            parts.append(text)
            yield ServerSentEvent(event="token", data={"text": text})

        sources = [s.model_dump() for s in result.sources]
        yield ServerSentEvent(event="sources", data=sources)

        # 저장 전에 검사해서, 형식 오류가 성공 로그와 오류 로그를 둘 다 남기지 않게 한다
        done = Done(message_id=0, answer_type=result.answer_type, actions=result.actions, options=result.options)

        # ponytail: 스트림 도중 창을 닫으면 로그가 남지 않음. 미완성 답변까지 필요해지면 그때 처리
        with SessionLocal() as db:
            log = ChatLog(
                question=question,
                answer="".join(parts).strip(),
                sources=sources,
                answer_type=result.answer_type,
            )
            db.add(log)
            db.commit()
            done.message_id = log.id
    except Exception as e:
        logger.exception("채팅 처리 실패")
        save_error_log(question, "".join(parts).strip(), sources, f"{type(e).__name__}: {e}")
        yield ServerSentEvent(
            event="error",
            data={"code": "generation_failed", "message": "답변을 만드는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요."},
        )
        return

    yield ServerSentEvent(event="done", data=done.model_dump())


@app.put("/messages/{message_id}/feedback", status_code=204)
def feedback(message_id: int, body: Feedback, db: Session = Depends(get_db)):
    log = db.get(ChatLog, message_id)
    if log is None:
        raise HTTPException(404, "메시지를 찾을 수 없습니다")
    log.feedback = body.rating
    db.commit()
    return Response(status_code=204)
