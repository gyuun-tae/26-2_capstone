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
    """SSE로 token(답변 조각) → sources(근거 문서) → done(로그 id) 순서로 보낸다."""
    sources, tokens = rag.answer(req.messages)

    parts = []
    async for text in tokens:
        parts.append(text)
        yield ServerSentEvent(event="token", data={"text": text})

    yield ServerSentEvent(event="sources", data=[s.model_dump() for s in sources])

    # ponytail: 스트림 도중 창을 닫으면 로그가 남지 않음. 미완성 답변까지 필요해지면 그때 처리
    with SessionLocal() as db:
        log = ChatLog(
            question=req.messages[-1].content,
            answer="".join(parts).strip(),
            sources=[s.model_dump() for s in sources],
        )
        db.add(log)
        db.commit()
        yield ServerSentEvent(event="done", data={"message_id": log.id})


@app.put("/messages/{message_id}/feedback", status_code=204)
def feedback(message_id: int, body: Feedback, db: Session = Depends(get_db)):
    log = db.get(ChatLog, message_id)
    if log is None:
        raise HTTPException(404, "메시지를 찾을 수 없습니다")
    log.feedback = body.rating
    db.commit()
    return Response(status_code=204)
