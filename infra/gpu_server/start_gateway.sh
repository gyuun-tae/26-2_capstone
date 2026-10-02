#!/usr/bin/env bash
# 관문(gateway.py)을 켠다. tmux 세션 "gateway", 127.0.0.1:8200, 로그 ~/llm-serve/gateway.log
# 터널은 이 포트만 밖으로 내보낸다 (vLLM 8100·8101은 직접 내보내지 않음)
set -euo pipefail
cd ~/llm-serve
[ -f .api_key ] || { echo ".api_key가 없습니다. start_qwen.sh를 먼저 실행하세요."; exit 1; }
source .venv/bin/activate
python -c "import fastapi, httpx, uvicorn" || { echo "fastapi·httpx·uvicorn이 없습니다 (vLLM과 함께 설치됨)"; exit 1; }

tmux kill-session -t gateway 2>/dev/null || true
tmux new -d -s gateway "cd ~/llm-serve && source .venv/bin/activate && \
  uvicorn gateway:app --host 127.0.0.1 --port 8200 --no-access-log 2>&1 | tee gateway.log"

for _ in $(seq 20); do curl -s localhost:8200/health >/dev/null && break; sleep 1; done
curl -s localhost:8200/health >/dev/null && { echo "READY"; curl -s localhost:8200/health; echo; } \
  || { echo "시작 실패:"; tail -8 gateway.log; exit 1; }
