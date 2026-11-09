#!/usr/bin/env bash
# GPU 서버에서 이미지 글 옮기기용 VLM(Qwen3-VL-8B-Instruct)을 vLLM으로 켠다. tmux 세션 "vlm", 서빙 이름 vlm, 로그 ~/llm-serve/vlm.log
# 색인을 만들 때만 잠깐 켠다 (scripts/31_vlm_drafts.py). 답변 서비스에는 쓰지 않는다.
# GPU 1번을 쓰므로 답변 모델(Qwen3-32B, 세션 qwen)을 먼저 꺼야 한다 → 그동안 챗봇 답변이 멈춘다. 팀원이 안 쓰는 시간에 돌린다.
#   tmux kill-session -t qwen && bash start_vlm.sh
#   다 쓰면: tmux kill-session -t vlm && bash start_qwen.sh
# 처음 한 번: hf download Qwen/Qwen3-VL-8B-Instruct  (약 17GB)
# 관문(gateway.py)은 model "vlm"을 8104로 보낸다. 관문을 고친 뒤라면 start_gateway.sh도 다시 실행한다.
set -euo pipefail
cd ~/llm-serve
[ -f .api_key ] || { echo ".api_key가 없습니다. start_qwen.sh를 먼저 한 번 실행하세요."; exit 1; }
MODEL=${VLM_MODEL:-Qwen/Qwen3-VL-8B-Instruct}

if tmux has-session -t qwen 2>/dev/null; then
  echo "답변 모델(세션 qwen)이 GPU 1번을 쓰고 있습니다. 먼저 끄세요: tmux kill-session -t qwen"; exit 1
fi
tmux kill-session -t vlm 2>/dev/null || true
sleep 3
# VLLM_USE_FLASHINFER_SAMPLER=0: start_qwen.sh와 같은 이유 (FlashInfer가 RTX 5090을 잘못 판정)
# --limit-mm-per-prompt: 요청 하나에 이미지 1장만 받는다
tmux new -d -s vlm "cd ~/llm-serve && source .venv/bin/activate && \
  VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_VISIBLE_DEVICES=1 \
  vllm serve $MODEL --served-model-name vlm \
  --host 127.0.0.1 --port 8104 --max-model-len 16384 --gpu-memory-utilization 0.85 \
  --limit-mm-per-prompt '{\"image\": 1}' \
  --api-key \$(cat .api_key) 2>&1 | tee vlm.log"

sleep 10
until curl -s localhost:8104/health >/dev/null || ! pgrep -f "vllm serve $MODEL" >/dev/null; do sleep 5; done
if curl -s localhost:8104/health >/dev/null; then echo "READY ($MODEL)"; else echo "시작 실패:"; grep -E "Error|core.py" vlm.log | tail -8; exit 1; fi
