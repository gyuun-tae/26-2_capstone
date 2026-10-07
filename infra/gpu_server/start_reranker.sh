#!/usr/bin/env bash
# GPU 서버에서 재정렬 모델(BAAI/bge-reranker-v2-m3)을 vLLM으로 켠다. tmux 세션 "reranker", 로그 ~/llm-serve/reranker.log
# 검색 후보(질문당 10개)를 질문-청크 쌍으로 다시 채점한다 (src/api/app/rerank.py). BGE-M3와 같은 GPU 0번을 나눠 쓴다.
# 2026-10-07 실험(docs/handoff/28_rerank.md): 질문당 후보 30개 0.07초, GPU 메모리 1.4GB
set -euo pipefail
cd ~/llm-serve
[ -f .api_key ] || { echo ".api_key가 없습니다. start_qwen.sh를 먼저 실행하세요."; exit 1; }
REVISION=953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e

tmux kill-session -t reranker 2>/dev/null || true
tmux new -d -s reranker "cd ~/llm-serve && source .venv/bin/activate && \
  CUDA_VISIBLE_DEVICES=0 \
  vllm serve BAAI/bge-reranker-v2-m3 --revision $REVISION --runner pooling --served-model-name bge-reranker \
  --host 127.0.0.1 --port 8102 --max-model-len 8192 --gpu-memory-utilization 0.10 \
  --api-key \$(cat .api_key) 2>&1 | tee reranker.log"

sleep 10
until curl -s localhost:8102/health >/dev/null || ! pgrep -f "vllm serve BAAI/bge-reranker-v2-m3" >/dev/null; do sleep 5; done
if curl -s localhost:8102/health >/dev/null; then echo READY; else echo "시작 실패:"; grep -E "Error|core.py" reranker.log | tail -8; exit 1; fi
