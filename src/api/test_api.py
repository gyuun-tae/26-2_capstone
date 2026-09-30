"""API 동작 확인: uv run python test_api.py"""
import json
import os
import tempfile

tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
os.environ["CHROMA_PATH"] = f"{tmp}/chroma"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)


def chat(question):
    """SSE 응답을 [(이벤트 이름, 데이터)] 목록으로"""
    body = c.post("/chat", json={"messages": [{"role": "user", "content": question}]}).text
    return [
        (block.split("\n")[0].removeprefix("event: "), json.loads(block.split("\n")[1].removeprefix("data: ")))
        for block in body.strip().split("\n\n")
    ]


# 1. 채팅: token → sources → done 순서, 근거는 팀 청크 규격 필드
events = chat("민원 신청은 어떻게 하나요?")
names = [e for e, _ in events]
assert names[0] == "token" and names[-2:] == ["sources", "done"], names
sources, done = events[-2][1], events[-1][1]
assert {"doc_id", "chunk_id", "title", "source_url", "locator", "published_at", "fetched_at"} <= sources[0].keys()
assert done["answer_type"] == "answer"
message_id = done["message_id"]

# 응답 유형·오류 흉내 (FE 화면 확인용)
assert chat("테스트:조건")[-1][1]["answer_type"] == "clarify"
unknown = chat("테스트:확인불가")
assert unknown[-1][1]["answer_type"] == "unknown" and unknown[-2][1] == []
err = chat("테스트:오류")
assert err[-1][0] == "error" and "done" not in [e for e, _ in err], err

# 2. 피드백
assert c.put(f"/messages/{message_id}/feedback", json={"rating": "up"}).status_code == 204
assert c.put("/messages/99999/feedback", json={"rating": "up"}).status_code == 404
assert c.put(f"/messages/{message_id}/feedback", json={"rating": "meh"}).status_code == 422

# 3. 잘못된 입력은 거절
assert c.post("/chat", json={"messages": []}).status_code == 422
assert c.post("/chat", json={"messages": [{"role": "assistant", "content": "hi"}]}).status_code == 422
assert c.post("/chat", json={"messages": [{"role": "user", "content": "가" * 1001}]}).status_code == 422

print("OK")
