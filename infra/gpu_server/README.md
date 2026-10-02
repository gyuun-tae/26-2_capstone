# GPU 서버 — LLM(Qwen3-32B)·임베딩(BGE-M3) 서빙

실행 방식 B: Render(API·조립) + Neon(로그·벡터) + **GPU 서버(임베딩·답변 생성)**. 이 문서는 GPU 서버에서 답변 생성(Qwen3-32B)과 임베딩(BGE-M3) 모델을 켜는 방법이다.

| 항목 | 값 |
|---|---|
| 접속 | JupyterHub `http://168.131.154.224:8888` (http라 비밀번호가 암호화되지 않음 — 다른 곳에서 쓰는 비밀번호 사용 금지) |
| 하드웨어 | RTX 5090 × 2 (각 32GB, Blackwell sm120), RAM 123GB, 디스크 800GB |
| 소프트웨어 | Python 3.12, uv, vLLM 0.30.0, PyTorch 2.13.0+cu130 (`~/llm-serve/.venv`) |
| 모델 | 생성 `Qwen/Qwen3-32B-AWQ` (4bit, 이름 `qwen3-32b`) · 임베딩 `BAAI/bge-m3` @ `5617a9f6` (이름 `bge-m3`) |
| GPU 배정 | 1번 = Qwen3-32B, 0번 = BGE-M3 |
| 주소 | 생성 `127.0.0.1:8100`, 임베딩 `127.0.0.1:8101` (서버 안에서만 접속). 외부(Render)는 관문 `127.0.0.1:8200` → 터널 주소로만 접속 |
| 인증 | `~/llm-serve/.api_key` (권한 600). 내용을 저장소·채팅에 올리지 않는다 |

## 처음 설치 (관리자 권한 불필요, 홈 폴더 안)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env
mkdir -p ~/llm-serve && cd ~/llm-serve
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install vllm
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_capability(0))"   # True, (12, 0)
hf download Qwen/Qwen3-32B-AWQ
```

## 켜기·끄기·상태

```bash
cd ~/llm-serve
R=https://raw.githubusercontent.com/gyuun-tae/26-2_capstone/main/infra/gpu_server
for f in start_qwen.sh start_bge.sh start_gateway.sh start_tunnel.sh gateway.py check_embedding.py check_gateway.py; do curl -fsSO $R/$f; done   # 스크립트 받기
bash start_qwen.sh                 # 생성 (세션 qwen, 로그 vllm.log). READY가 나오면 준비 완료
bash start_bge.sh                  # 임베딩 (세션 bge, 로그 bge.log)
tmux attach -t qwen                # 실행 화면 보기 (나올 때 Ctrl+B 다음 D)
tmux kill-session -t qwen          # 끄기 (임베딩은 -t bge)
```

시험 요청 (Qwen3의 "생각 과정" 출력은 끈다):

```bash
curl -s localhost:8100/v1/chat/completions -H "Authorization: Bearer $(cat ~/llm-serve/.api_key)" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-32b","messages":[{"role":"user","content":"안녕하세요"}],"max_tokens":100,"chat_template_kwargs":{"enable_thinking":false}}'
```

## 임베딩 일치 확인

질의는 GPU 서버에서, 청크는 로컬(`scripts/16_build_index.py`)에서 벡터로 만들므로 둘이 같아야 검색이 맞다. `start_bge.sh`는 로컬 색인과 같은 모델 revision으로 고정한다. 로컬에서 만든 비교 파일(글 + 로컬 벡터)을 `~/llm-serve`에 올리고 확인한다.

```bash
python3 check_embedding.py bge_m3_check.json   # 모든 항목 코사인 0.999 이상이면 "결과: 일치"
```

## 외부 연결: 관문 + 터널

```text
Render ──https──▶ Cloudflare 임시 터널 ──▶ 관문 gateway.py (8200) ──▶ Qwen (8100) / BGE-M3 (8101)
```

| 관문이 하는 일 | 이유 |
|---|---|
| `Authorization: Bearer <.api_key>`가 맞아야 통과 | vLLM의 `--api-key`는 `/v1/...`만 검사해 `/tokenize`·`/metrics` 등이 키 없이 열린다 |
| `POST /v1/embeddings`(모델 `bge-m3`), `POST /v1/chat/completions`(모델 `qwen3-32b`), `GET /health`만 허용 | 나머지 주소·문서 페이지는 404 |
| 요청 1MB, 답변 2,048토큰 상한 | 큰 요청으로 GPU를 붙잡지 못하게 |
| 스트리밍 답변을 SSE 대신 **NDJSON**(한 줄에 JSON 하나, `application/x-ndjson`)으로 전달 | [Cloudflare 임시 터널은 SSE를 지원하지 않음](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/). 각 줄은 vLLM SSE의 `data:` 내용 그대로 |

```bash
bash start_gateway.sh              # 관문 (세션 gateway, 로그 gateway.log). Qwen·BGE-M3를 먼저 켠다
bash start_tunnel.sh               # 터널 (세션 tunnel, 로그 tunnel.log). cloudflared를 ~/bin에 받고 주소를 tunnel_url에 저장
python3 check_gateway.py           # 터널 주소로 키 검사·막힌 주소·임베딩·스트리밍 확인
```

- 임시 터널은 **다시 켤 때마다 주소가 바뀐다** → Render Environment의 `GPU_URL`을 새 주소로 고치고 재배포. 가동 보장이 없는 개발·시험용이다.
- 고정 주소가 필요해지면 도메인 + Cloudflare 정식 터널 또는 ngrok으로 바꾼다 (관문은 그대로).
- 끄기: `tmux kill-session -t tunnel; tmux kill-session -t gateway`

## 알려진 문제

- **FlashInfer가 RTX 5090을 지원하지 않는 GPU로 잘못 판정**: 시작 중 `RuntimeError: FlashInfer requires GPUs with sm75 or higher`로 실패한다. 다음 글자를 고르는 단계(sampling)에서만 FlashInfer를 끄는 `VLLM_USE_FLASHINFER_SAMPLER=0`으로 해결 (`start_qwen.sh`에 포함). 답변 품질은 같다.
- 공유 서버다. 켜기 전에 `nvidia-smi`로 다른 사람이 GPU를 쓰는지 확인한다. 데스크톱이 재부팅되면 다시 켜야 한다.

## 2026-10-02 확인 결과

| 항목 | 결과 |
|---|---|
| 모델 로딩 | 18.24 GiB, KV cache 6.01 GiB (최대 길이 16,384 토큰) |
| GPU 1번 사용량 | 27.9 / 32.6 GB |
| 짧은 한국어 질문 | 자연스러운 2문장 답변, 62토큰 0.85초 (근거를 넣은 긴 입력은 조립 단계에서 다시 측정) |
| BGE-M3 일치 | 로컬 색인 `bge-m3-dense-d67237d5942d`과 코사인 0.999998~1.000000 (최장 청크 6,463자·표·조문·서식·질문 5개), 5개 임베딩 0.07초 |
| 관문 + 임시 터널 | `check_gateway.py` 전 항목 통과: 키 없음·틀린 키 401, `/tokenize`·`/docs`·`/v1/models`·`/metrics` 404, 다른 모델 400. 터널 경유 임베딩 0.10초, 스트리밍 NDJSON 301줄이 0.12초부터 4.10초까지 나뉘어 도착 (약 73토큰/초) → **임시 터널로 스트리밍 가능** |
