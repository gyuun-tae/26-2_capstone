# GPU 서버 — LLM(Qwen3-32B) 서빙

실행 방식 B: Render(API·조립) + Neon(로그·벡터) + **GPU 서버(임베딩·답변 생성)**. 이 문서는 GPU 서버에서 답변 생성 모델을 켜는 방법이다.

| 항목 | 값 |
|---|---|
| 접속 | JupyterHub `http://168.131.154.224:8888` (http라 비밀번호가 암호화되지 않음 — 다른 곳에서 쓰는 비밀번호 사용 금지) |
| 하드웨어 | RTX 5090 × 2 (각 32GB, Blackwell sm120), RAM 123GB, 디스크 800GB |
| 소프트웨어 | Python 3.12, uv, vLLM 0.30.0, PyTorch 2.13.0+cu130 (`~/llm-serve/.venv`) |
| 모델 | `Qwen/Qwen3-32B-AWQ` (4bit), 서빙 이름 `qwen3-32b` |
| GPU 배정 | 1번 = Qwen3-32B, 0번 = 임베딩(BGE-M3) 예정 |
| 주소 | `127.0.0.1:8100` (서버 안에서만 접속). 외부 연결은 터널로 별도 구성 예정 |
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
bash start_qwen.sh                 # 저장소의 infra/gpu_server/start_qwen.sh를 ~/llm-serve에 복사해 실행. READY가 나오면 준비 완료
tmux attach -t qwen                # 실행 화면 보기 (나올 때 Ctrl+B 다음 D)
tmux kill-session -t qwen          # 끄기
tail -30 ~/llm-serve/vllm.log      # 로그
```

시험 요청 (Qwen3의 "생각 과정" 출력은 끈다):

```bash
curl -s localhost:8100/v1/chat/completions -H "Authorization: Bearer $(cat ~/llm-serve/.api_key)" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-32b","messages":[{"role":"user","content":"안녕하세요"}],"max_tokens":100,"chat_template_kwargs":{"enable_thinking":false}}'
```

## 알려진 문제

- **FlashInfer가 RTX 5090을 지원하지 않는 GPU로 잘못 판정**: 시작 중 `RuntimeError: FlashInfer requires GPUs with sm75 or higher`로 실패한다. 다음 글자를 고르는 단계(sampling)에서만 FlashInfer를 끄는 `VLLM_USE_FLASHINFER_SAMPLER=0`으로 해결 (`start_qwen.sh`에 포함). 답변 품질은 같다.
- 공유 서버다. 켜기 전에 `nvidia-smi`로 다른 사람이 GPU를 쓰는지 확인한다. 데스크톱이 재부팅되면 다시 켜야 한다.

## 2026-10-02 확인 결과

| 항목 | 결과 |
|---|---|
| 모델 로딩 | 18.24 GiB, KV cache 6.01 GiB (최대 길이 16,384 토큰) |
| GPU 1번 사용량 | 27.9 / 32.6 GB |
| 짧은 한국어 질문 | 자연스러운 2문장 답변, 62토큰 0.85초 (근거를 넣은 긴 입력은 조립 단계에서 다시 측정) |
