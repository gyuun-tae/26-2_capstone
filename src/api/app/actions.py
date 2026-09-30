"""근거와 상관없이 쓸 수 있는 고정 링크 목록 (v0.2 actions).
LLM이 만든 URL·전화번호는 쓰지 않는다. 여기 넣기 전에 주소가 실제로 열리는지 확인할 것."""
from app.schemas import Action

# 2026-09-30 확인: portmis.go.kr은 410(서비스 종료), new.portmis.go.kr이 현재 Port-MIS
PORT_MIS = Action(type="link", label="Port-MIS 열기", url="https://new.portmis.go.kr/", note="로그인 필요")
