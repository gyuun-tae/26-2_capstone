#!/usr/bin/env bash
# GPU 서버에서 Qwen3-32B(AWQ 4bit)를 vLLM으로 켠다. tmux 세션 "qwen", 로그 ~/llm-serve/vllm.log
# 설치·주의사항: infra/gpu_server/README.md
set -euo pipefail
cd ~/llm-serve
[ -f .api_key ] || { openssl rand -hex 24 > .api_key; chmod 600 .api_key; }

tmux kill-session -t qwen 2>/dev/null || true
# VLLM_USE_FLASHINFER_SAMPLER=0: FlashInfer가 RTX 5090(sm120)을 "sm75 미만"으로 잘못 판정해 시작이 실패하므로 끈다
tmux new -d -s qwen "cd ~/llm-serve && source .venv/bin/activate && \
  VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_VISIBLE_DEVICES=1 \
  vllm serve Qwen/Qwen3-32B-AWQ --served-model-name qwen3-32b \
  --host 127.0.0.1 --port 8100 --max-model-len 16384 --gpu-memory-utilization 0.90 \
  --api-key \$(cat .api_key) 2>&1 | tee vllm.log"

sleep 10
until curl -s localhost:8100/health >/dev/null || ! pgrep -f "vllm serve" >/dev/null; do sleep 5; done
if curl -s localhost:8100/health >/dev/null; then echo READY; else echo "시작 실패:"; grep "core.py" vllm.log | tail -6; exit 1; fi
