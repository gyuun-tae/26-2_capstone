#!/usr/bin/env bash
# GPU 서버에서 답변 전 판정용 LLM을 vLLM으로 켠다. tmux 세션 "gate", 서빙 이름 gate-llm, 로그 ~/llm-serve/gate.log
# 판정("근거가 질문의 주제를 다루는가: 있음/없음", src/api/app/gate.py)을 답변 생성(Qwen3-32B, GPU 1번)과 동시에 돌리려고
# 다른 GPU(0번, BGE-M3·재정렬과 나눠 씀)에 둔다. 같은 GPU에서 돌리면 서로 계산을 나눠 써 첫 글자가 늦어진다 (docs/handoff/31_answer_gate.md).
# 모델 바꾸기: GATE_MODEL=Qwen/Qwen3-8B-AWQ bash start_gate.sh (8B는 답이 있는 질문을 3개 잘못 막아 14B가 기본)
# GPU 0번 메모리: BGE-M3 0.20 + 재정렬 0.10 + 판정 0.55 (14B는 0.45면 KV cache가 0.94GiB뿐이라 16384토큰을 못 받음)
set -euo pipefail
cd ~/llm-serve
[ -f .api_key ] || { echo ".api_key가 없습니다. start_qwen.sh를 먼저 실행하세요."; exit 1; }
MODEL=${GATE_MODEL:-Qwen/Qwen3-14B-AWQ}

tmux kill-session -t gate 2>/dev/null || true
sleep 3  # 이전 판정 모델이 GPU 메모리를 내려놓을 때까지
# VLLM_USE_FLASHINFER_SAMPLER=0: start_qwen.sh와 같은 이유 (FlashInfer가 RTX 5090을 잘못 판정)
tmux new -d -s gate "cd ~/llm-serve && source .venv/bin/activate && \
  VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_VISIBLE_DEVICES=0 \
  vllm serve $MODEL --served-model-name gate-llm \
  --host 127.0.0.1 --port 8103 --max-model-len 16384 --gpu-memory-utilization 0.55 \
  --api-key \$(cat .api_key) 2>&1 | tee gate.log"

sleep 10
until curl -s localhost:8103/health >/dev/null || ! pgrep -f "vllm serve $MODEL" >/dev/null; do sleep 5; done
if curl -s localhost:8103/health >/dev/null; then echo "READY ($MODEL)"; else echo "시작 실패:"; grep -E "Error|core.py" gate.log | tail -8; exit 1; fi
