"""API 동작 확인: uv run python test_api.py"""
import os
import tempfile

tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
os.environ["CHROMA_PATH"] = f"{tmp}/chroma"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
q = {"messages": [{"role": "user", "content": "FTZ 입주 서류는?"}]}

# 1. 채팅: token → sources → done 순서
body = c.post("/chat", json=q).text
events = [line.removeprefix("event: ") for line in body.splitlines() if line.startswith("event: ")]
assert events[0] == "token" and events[-2:] == ["sources", "done"], events
message_id = int(body.rsplit('"message_id":', 1)[1].split("}")[0])

# 2. 피드백
assert c.put(f"/messages/{message_id}/feedback", json={"rating": "up"}).status_code == 204
assert c.put("/messages/99999/feedback", json={"rating": "up"}).status_code == 404
assert c.put(f"/messages/{message_id}/feedback", json={"rating": "meh"}).status_code == 422

# 3. 잘못된 입력은 거절
assert c.post("/chat", json={"messages": []}).status_code == 422
assert c.post("/chat", json={"messages": [{"role": "assistant", "content": "hi"}]}).status_code == 422
assert c.post("/chat", json={"messages": [{"role": "user", "content": "가" * 1001}]}).status_code == 422

print("OK")
