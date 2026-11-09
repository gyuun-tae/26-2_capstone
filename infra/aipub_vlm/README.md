# AIPub H100 워크스페이스에서 VLM 돌리기 (V3 이미지 글 옮기기)

색인을 만들 때만 쓰는 VLM(Qwen3-VL-8B-Instruct)을 학교 AIPub 워크스페이스(윤태가 만든 것)에서 켠다. 2026-11-09.
기존 GPU 서버(RTX 5090)의 답변 모델을 끄지 않아도 되므로 챗봇이 멈추지 않는다.

| 항목 | 값 |
|---|---|
| 워크스페이스 | `workload.aipub.jnu.ac.kr` SSH 포트 57896, root. 학교 와이파이에서는 SSH가 시간 초과 → **웹 터미널로 작업** |
| GPU | H100 80GB의 절반(`PART_50`, 42.6GB) |
| 저장 위치 | `~/vlm` (작업 디스크 `/`, 약 250GB 여유). **`/lsail-jnu`는 연구실 공유 NAS(97% 사용)라 쓰지 않는다** |
| 연결 | vLLM(127.0.0.1:8104, API 키) ← Cloudflare 임시 터널 ← 내 PC `scripts/31_vlm_drafts.py` |

터널은 워크스페이스에서 바깥으로 나가는 연결이라 SSH 방화벽과 상관없다. 이미지는 PC에 있는 그대로 보낸다.
관문(gateway.py) 없이 vLLM을 바로 내보내므로 **작업할 때만 켜고 끝나면 바로 끈다** (4단계).

## 1. 설치 (처음 한 번, 10~20분)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env
mkdir -p ~/vlm && cd ~/vlm && uv venv --python 3.12 .venv && source .venv/bin/activate
nohup bash -c "uv pip install vllm && hf download Qwen/Qwen3-VL-8B-Instruct && echo DONE" > install.log 2>&1 &
tail -f install.log    # 마지막에 DONE이 나오면 끝 (Ctrl+C로 보기만 멈춤, 설치는 계속됨)
```

## 2. VLM 켜기

```bash
cd ~/vlm && source .venv/bin/activate
[ -f .api_key ] || { python3 -c "import secrets; print(secrets.token_hex(24))" > .api_key; chmod 600 .api_key; }
nohup vllm serve Qwen/Qwen3-VL-8B-Instruct --served-model-name vlm \
  --host 127.0.0.1 --port 8104 --max-model-len 16384 --gpu-memory-utilization 0.85 \
  --limit-mm-per-prompt '{"image": 1}' --api-key $(cat .api_key) > vlm.log 2>&1 &
until curl -s localhost:8104/health >/dev/null; do sleep 5; done; echo READY   # 1~3분
```

안 켜지면 `tail -30 vlm.log`.

## 3. 터널 켜기

```bash
cd ~/vlm
[ -x cloudflared ] || { curl -fsSL -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x cloudflared; }
nohup ./cloudflared tunnel --url http://127.0.0.1:8104 > tunnel.log 2>&1 &
sleep 10; grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log | head -1
```

나온 주소와 `cat ~/vlm/.api_key` 값을 **내 PC 저장소 루트 `.env`에 직접** 넣는다 (키는 채팅·저장소에 올리지 않는다).

```
VLM_URL=https://xxxx.trycloudflare.com
VLM_API_KEY=<.api_key 내용>
```

그다음 PC에서: `uv run --no-project --with pillow --with httpx python scripts/31_vlm_drafts.py --sample`

## 4. 끄기 (작업 끝나면 바로)

```bash
pkill -f cloudflared; pkill -f "vllm serve"
```

다시 쓸 때는 2·3단계만. 터널 주소는 켤 때마다 바뀌므로 `.env`의 `VLM_URL`도 고친다.
