#!/usr/bin/env bash
# GPU 서버에서 BGE-M3 임베딩을 vLLM으로 켠다. tmux 세션 "bge", 로그 ~/llm-serve/bge.log
# 로컬 색인(scripts/16_build_index.py)과 같은 모델 revision으로 고정해야 질의·문서 벡터가 일치한다.
set -euo pipefail
cd ~/llm-serve
[ -f .api_key ] || { openssl rand -hex 24 > .api_key; chmod 600 .api_key; }
REVISION=5617a9f61b028005a4858fdac845db406aefb181

tmux kill-session -t bge 2>/dev/null || true
tmux new -d -s bge "cd ~/llm-serve && source .venv/bin/activate && \
  CUDA_VISIBLE_DEVICES=0 \
  vllm serve BAAI/bge-m3 --revision $REVISION --runner pooling --served-model-name bge-m3 \
  --host 127.0.0.1 --port 8101 --max-model-len 8192 --gpu-memory-utilization 0.20 \
  --api-key \$(cat .api_key) 2>&1 | tee bge.log"

sleep 10
until curl -s localhost:8101/health >/dev/null || ! pgrep -f "vllm serve BAAI/bge-m3" >/dev/null; do sleep 5; done
if curl -s localhost:8101/health >/dev/null; then echo READY; else echo "시작 실패:"; grep -E "Error|core.py" bge.log | tail -8; exit 1; fi
