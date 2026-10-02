# YGPA RAG 챗봇 백엔드

FastAPI + SQLite(로컬) / PostgreSQL(배포, Neon) + Chroma

## 실행

```bash
cd src/api                        # 이 폴더에서 실행
uv sync                          # 의존성 설치 (최초 1회)
uv run fastapi dev app/main.py   # 개발 서버: http://localhost:8000
```

- API 문서(Swagger): http://localhost:8000/docs
- 상태 확인: http://localhost:8000/health

## 구조

```
app/
├── main.py         # FastAPI 앱, 라우트
├── rag.py          # 답변 진입점. RAG_MODE=real이면 rag_real, 아니면 가짜(mock) 답변
├── rag_real.py     # 실제 조립: 질문 임베딩 → Neon 검색 → Qwen 생성 → 근거·버튼 정리
├── gpu.py          # GPU 서버 관문 호출 (임베딩, 답변 스트리밍 NDJSON)
├── search.py       # Neon pgvector 검색 (색인은 scripts/18_load_pgvector.py로 적재)
├── prompt.py       # Qwen 지시문·근거 구성, 정리 줄(@@META) 거르기, 규칙 위반 검사
├── actions.py      # 고정 링크 (LLM은 이름만 고름)
├── sources.py      # 청크 → 화면용 근거(Source)·서식 다운로드 변환 (4단계 제안)
├── db.py           # DB 연결 (SQLAlchemy, DATABASE_URL로 SQLite·PostgreSQL 전환)
└── vectorstore.py  # Chroma 연결 (벡터DB 접근은 여기에만)
data/               # app.db, chroma/ 가 생성됨 (git 제외)
```

## 환경변수 (선택)

| 이름 | 기본값 |
|---|---|
| `DATABASE_URL` | `sqlite:///data/app.db` (배포: Neon 접속 주소를 그대로 붙여넣기) |
| `CHROMA_PATH` | `data/chroma` |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000,https://dlghskgmll.github.io` |
| `RAG_MODE` | `mock` (가짜 답변). `real`이면 아래 값으로 실제 검색·생성 — **승인 전 청크 색인이므로 팀장 확인 후 켠다** |
| `GPU_URL` | GPU 서버 터널 주소 (`infra/gpu_server/start_tunnel.sh`가 출력. 터널을 다시 켜면 바뀜) |
| `GPU_API_KEY` | GPU 서버 `~/llm-serve/.api_key` 내용. GitHub·채팅에 올리지 않는다 |
| `INDEX_VERSION` | Neon에 넣은 색인 버전 (예: `bge-m3-dense-d67237d5942d`) |
| `UNKNOWN_THRESHOLD` | `0.48` — 검색 1위 점수가 이보다 낮으면 LLM 없이 "확인 불가" (`scripts/19_unknown_threshold.py`로 측정) |

실제 모드 시험 (로그를 남기지 않음): 저장소 루트 `.env`에 `DATABASE_URL`·`GPU_URL`·`GPU_API_KEY`·`INDEX_VERSION`을 넣고 `uv run python try_real.py "질문"`.
테스트: `uv run python test_api.py`, `test_sources.py`, `test_rag_real.py` (가짜 GPU·검색).

## 배포 (Render)

GitHub에 push하면 Render가 `Dockerfile`로 자동 빌드·배포한다. (Render 설정: Root Directory = `src/api`)

```bash
docker build -t ygpa-api . && docker run --rm -p 8000:8000 ygpa-api   # 로컬 확인: http://localhost:8000/health
```

- FE 주소 허용: Render 대시보드 → Environment에 `CORS_ORIGINS` 추가 (쉼표로 구분)
- 무료 플랜은 15분 동안 요청이 없으면 잠들고, 첫 요청 때 깨어나는 데 30초 이상 걸린다
- 대화 로그는 Neon(PostgreSQL)에 저장된다 → Render Environment의 `DATABASE_URL`. 이 값이 없으면 서버 안 SQLite에 저장되고 재배포 때 지워진다
- `DATABASE_URL`에는 비밀번호가 들어 있으므로 GitHub·채팅에 올리지 않는다
- 로그 테이블 `chat_logs`: 질문·답변·근거·피드백·`answer_type`(answer/clarify/unknown/**error**)·`error`(오류 종류). 실패한 대화는 질문과 오류 종류만 남긴다. 답변 조각·예외 메시지는 저장하지 않고 상세 원인은 Render Logs에서 본다 (DB 자체가 실패한 경우는 로그 저장도 안 됨)
- 모델에 nullable 열을 추가하면 서버 시작 때 기존 테이블에 자동으로 붙는다 (`db.add_missing_columns`)
