import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.orm import Session

Path("data").mkdir(exist_ok=True)  # SQLite 파일과 Chroma 폴더 위치

from app import rag  # noqa: E402
from app.db import Base, SessionLocal, engine, get_db  # noqa: E402
from app.models import ChatLog  # noqa: E402
from app.schemas import ChatRequest, Feedback  # noqa: E402
from app.vectorstore import client  # noqa: E402

Base.metadata.create_all(engine)
logger = logging.getLogger(__name__)

app = FastAPI(title="YGPA RAG 챗봇 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    client.heartbeat()  # Chroma가 살아있는지 확인
    return {"status": "ok"}


@app.post("/chat", response_class=EventSourceResponse)
async def chat(req: ChatRequest):
    """SSE로 token(답변 조각) → sources(근거 문서) → done(로그 id, 응답 유형) 순서로 보낸다.
    검색·생성·로그 저장 중 어디서든 실패하면 done 대신 error를 보내고 끝낸다.
    (FE는 done 또는 error를 받아야 로딩을 멈출 수 있다)"""
    try:
        result = rag.answer(req.messages)
        parts = []
        async for text in result.tokens:
            parts.append(text)
            yield ServerSentEvent(event="token", data={"text": text})

        sources = [s.model_dump() for s in result.sources]
        yield ServerSentEvent(event="sources", data=sources)

        # ponytail: 스트림 도중 창을 닫으면 로그가 남지 않음. 미완성 답변까지 필요해지면 그때 처리
        with SessionLocal() as db:
            log = ChatLog(question=req.messages[-1].content, answer="".join(parts).strip(), sources=sources)
            db.add(log)
            db.commit()
            message_id = log.id
    except Exception:
        logger.exception("채팅 처리 실패")
        yield ServerSentEvent(
            event="error",
            data={"code": "generation_failed", "message": "답변을 만드는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요."},
        )
        return

    yield ServerSentEvent(event="done", data={"message_id": message_id, "answer_type": result.answer_type})


@app.put("/messages/{message_id}/feedback", status_code=204)
def feedback(message_id: int, body: Feedback, db: Session = Depends(get_db)):
    log = db.get(ChatLog, message_id)
    if log is None:
        raise HTTPException(404, "메시지를 찾을 수 없습니다")
    log.feedback = body.rating
    db.commit()
    return Response(status_code=204)
