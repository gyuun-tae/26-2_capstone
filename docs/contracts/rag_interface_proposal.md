# RAG 연결 인터페이스 제안 (4단계)

> **제안 · 미합의**. 검색·답변 생성 담당과 합의한 뒤 확정한다. 실제 검색·생성 코드는 아직 없으며 API는 mock으로 동작한다.

| 항목 | 내용 |
|---|---|
| 보내는 사람 | API·답변 제어 · 김동욱 |
| 받는 사람 | 문서 처리·검색 담당, 답변 생성 담당 (참고: 프론트엔드) |
| 기준 코드 | `feat/rag-interface-proposal` · `src/api/app/sources.py`, `app/rag.py`, `app/schemas.py` |
| 근거 문서 | [지식베이스 등록 계획](../handoff/dataset_and_knowledge_base.md), [API·FE·RAG 연결 검토](../handoff/api_frontend_rag_review_20260930.md), [채팅 API v0.2](README.md#채팅-api-v02--fe-제안-반영-2026-09-30) |
| 작성일 | 2026-09-30 |

---

## 한눈에 보기

질문 하나가 처리되는 순서다. 각 칸의 담당이 자기 함수만 만들면 서로 연결된다.

```text
FE ──POST /chat──▶ [API] rag.answer(messages)
                     │
                     ├─① search(질문) ─────────────▶ [검색] hits: 청크 그대로 + 점수
                     │     hits가 없거나 점수 기준 미달 → unknown (LLM 호출 안 함)
                     │
                     ├─② generate(messages, hits) ─▶ [생성] 답변 조각 스트림 + 응답 유형·선택지
                     │
                     └─③ 청크 → 화면용 근거 변환 (sources.py), 서식 다운로드·고정 링크 조립
                                     │
FE ◀── SSE: token … → sources → done(actions, options) / error
```

| 담당 | 만들 것 | 위치 (제안) |
|---|---|---|
| 문서 처리·검색 | `search()` — 승인된 청크 검색 | `src/rag/search.py` |
| 답변 생성 | `generate()` — 근거로 답변 생성 | `src/rag/generate.py` |
| API·답변 제어 | 조립(`rag.answer`), 화면용 변환, 로그·SSE | `src/api/app/rag.py`, `sources.py` |

**원칙: 청크는 검색부터 API까지 가공하지 않고 그대로 전달한다.** 화면용 문구는 API의 `sources.py` 한 곳에서만 만든다. 그래야 출처·버전·해시가 중간에 바뀌지 않는다.

---

## 1. 검색 함수 (검색 담당)

```python
def search(query: str, k: int = 5) -> list[Hit]: ...

class Hit(TypedDict):
    chunk: dict   # chunks.jsonl의 한 줄을 그대로 (source_locator 중첩 객체 포함)
    score: float  # 높을수록 관련. 기준은 검색 담당이 정함
```

- 결과는 점수 높은 순. 관련 청크가 없으면 빈 목록. 실패하면 예외를 던진다 (API가 `error`로 처리).
- **청크를 그대로 돌려준다.** Chroma metadata는 중첩 객체를 받지 않으므로(검토 문서의 합성 테스트에서 `ValueError`), Chroma를 쓴다면 청크 전체를 JSON 문자열이나 별도 테이블에 보관했다가 복원해야 한다. [4.5절의 추천(pgvector)](#45-벡터-저장소-추천-neon-postgresql--pgvector)대로 하면 청크 전체를 `jsonb` 열에 그대로 두면 되어 이 문제가 없다.
- 검색 대상은 등록 계획대로 **승인 목록에 있는 청크만**. 과거 부칙(`historical_addendum`)은 기본 제외, FAQ 출처는 차단.
- 정할 것: `k` 기본값, "근거 없음(unknown)"으로 볼 점수 기준.

## 2. 생성 함수 (답변 생성 담당)

```python
def generate(messages: list[Message], hits: list[Hit]) -> Generation: ...

@dataclass
class Generation:
    tokens: AsyncIterator[str]          # 답변 조각
    # 아래는 tokens를 다 읽은 뒤 확정
    answer_type: str = "answer"         # "answer" | "clarify" | "unknown"
    options: list[str] = []             # clarify일 때 선택지 문구
    action_keys: list[str] = []         # 고정 링크 이름 (예: "port_mis"). URL이 아니라 이름만
```

프롬프트에서 지킬 규칙 (v0.2 FE 제안 A·C·D와 같다):
1. **근거 번호 = `hits` 순서.** 첫 근거가 `[1]`. 근거를 쓴 문장 끝에 `[1]` 또는 `[1][2]`. 없는 번호는 쓰지 않는다.
2. **서식**: 요약 한두 문장 → 빈 줄 → `1.` 번호 목록(절차). `**굵게**`, `-` 목록까지만. HTML·표·마크다운 링크 금지.
3. **URL·전화번호를 쓰지 않는다.** 링크가 필요하면 `action_keys`에 정해진 이름만 넣는다. 실제 주소는 API가 `app/actions.py`에서 채운다.
4. 근거가 부족하거나 보류된 사용료 별표에 의존하면 `unknown`. 금액·기간을 모델의 일반 지식으로 보충하지 않는다.
5. 답이 조건에 따라 갈리면(예: 외항선/내항선) `clarify` + 선택지. 어떤 질문에서 되물을지 기준은 생성 담당이 정한다.

## 3. API가 하는 일 (`rag.answer` 조립)

| 단계 | 내용 |
|---|---|
| unknown 조기 판단 | `search()` 결과가 비었거나 점수 기준 미달이면 LLM을 부르지 않고 `unknown` + 연락처 안내 |
| sources | **`hits` 전체를 같은 순서로** `chunk_to_source()` 변환 → 인용 번호와 자동으로 일치 |
| 서식 다운로드 | 서식 청크(`whole_form`)가 근거에 있으면 `form_download()`로 버튼 생성. URL = 청크의 `source_url` |
| 고정 링크 | `action_keys`를 `app/actions.py`에서 찾아 추가. 없는 이름은 무시 |
| 연락처 | 부서 연락처 표가 생기면 추가 (업무·자료 담당 산출물 대기) |
| 로그 | 질문·답변·근거·응답 유형 저장. 실패는 질문 + 오류 종류만 |

**sources를 "인용된 것만"이 아니라 "전달한 근거 전체"로 보내는 이유**: 답변 조각(`[1]`, `[3]`)은 이미 화면에 나간 뒤라, 나중에 인용된 것만 골라 번호를 다시 매기면 본문 번호와 어긋난다. FE는 본문에 나온 번호의 근거만 강조하고 나머지는 흐리게 보여줄 수 있다.

## 4. 화면용 근거 변환 규칙 (`sources.py`)

실제 청크 178개 전부를 변환해 `Source` 검증을 통과했다 (2026-09-30, 로컬). 서식 청크 10개에서 다운로드 버튼이 생성됐다.

### `locator` (근거 위치 문구)

| 청크 형식 | 규칙 | 실제 예 |
|---|---|---|
| HTML 설명 (`processed_text`) | 절 제목을 ` · `로 연결 | `신청자격 · 신청절차` (YGPA-001) |
| HTML 표 (`html_table`) | 절 제목 + ` 표` | `시설개요 기본정보 표` (YGPA-005) |
| 첨부 조문 (`article`) | 본문 첫머리의 조 제목 | `제1조(목적)` (YGPA-030, HWP) |
| PDF 조문 | 조 제목 + 파일 쪽수 | `제1조(목적) · 1쪽` (YGPA-031) |
| 부칙 (`historical_addendum`) | 부칙 제목, PDF면 쪽수 | `부칙 (2011.10.24. 규정 제24호) · 10쪽` |
| 별지 표 (`table`) | 본문의 별지 번호 | `별지1` (YGPA-030) |
| 서식 (`whole_form`) | 고정 문구 | `서식 전체` |

- 쪽수는 **PDF 파일의 쪽 번호**다 (`pdf_page.page_number`). 인쇄된 쪽 번호와 다를 수 있다.
- HTML은 가상의 쪽 번호를 만들지 않는다 (청크 규격과 같음).
- 원래 위치 객체 `source_locator`는 청크에 그대로 남는다. 화면 문구는 표시용일 뿐이다.

### `snippet` (근거 발췌문)

- 처리 과정에서 붙인 설명 줄(`행·열 번호는…`, `표 좌표는…`, `표 YGPA-… (n행 × m열)`, `표 밖 안내:`)은 뺀다.
- 표 셀은 `구분: 축구장`처럼 **머리글: 값**만 남긴다.
- 공백을 정리하고 150자에서 자른다.

예: `시설개요 기본정보 구분: 축구장 규격(m): 90×50 인조잔디 규모: 1개 위치: 황길동 1419 물터공원 비고: 인조잔디 구장 1면`

### 날짜

`published_at`·`updated_at`이 빈 문자열이면 `null`로 보낸다. 수집일(`fetched_at`)로 채우지 않는다.

---

## 4.5 벡터 저장소 추천: Neon PostgreSQL + pgvector

**추천: 새 서비스를 추가하지 않고, 대화 로그를 저장 중인 Neon PostgreSQL에 `pgvector` 확장을 켜서 벡터 DB로 쓴다.** (5절 3번에 대한 API 쪽 의견. 최종 결정은 검색 담당과 함께)

"벡터 DB"는 역할 이름이다. 질문과 뜻이 가까운 청크를 찾고(의미 검색), 벡터와 함께 본문·출처·버전을 보관하고, 승인·부칙 같은 조건으로 거르고, 색인 버전을 교체하는 일을 한다. PostgreSQL에 `pgvector`를 켜면 같은 DB가 이 역할을 맡는다.

```text
Render (서버 코드)
   └──▶ Neon PostgreSQL
          ├── chat_logs      (지금: 대화 로그)
          └── chunks          (추가: 청크 전체 + 벡터 = 벡터 DB 역할)
```

| | Neon + pgvector (추천) | Chroma (현재 설치) | 전용 벡터 DB 서비스 |
|---|---|---|---|
| 새 서비스 | 없음 | 없음 | 가입·키 관리 추가 |
| Render 무료 재배포 | **유지** (서버 밖 저장) | **색인 파일이 지워짐** → 매번 재생성하거나 이미지에 포함 | 유지 |
| 청크 전체 보관 | `jsonb` 열에 그대로 (중첩 `source_locator` 포함) | 중첩 metadata 불가 → 평탄화·별도 보관 필요 | 서비스마다 다름 |
| 키워드 검색 결합 | 같은 DB의 PostgreSQL 전문 검색·SQL 조건과 결합 가능 (계획서의 pgvector 근거와 같음). 한국어 처리 결과는 별도 검증 | 별도 구현 | 서비스마다 다름 |
| 우리 규모 | 청크 178개 × 벡터 1개 ≈ 수 MB. 무료 용량 안 | 충분 | 과함 |
| 관리할 곳 | Neon 하나 (로그와 같은 곳) | 서버 + Neon | 서버 + Neon + 새 서비스 |

**표 구성 예시 (초안)**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    chunk_id       text PRIMARY KEY,
    index_version  text NOT NULL,      -- 색인 버전 (모델·입력 형식·승인 목록이 바뀌면 새 버전)
    doc_id         text NOT NULL,
    chunk_kind     text,               -- article / historical_addendum / whole_form ... (필터용)
    approved       boolean NOT NULL,   -- 승인 목록 반영
    chunk          jsonb NOT NULL,     -- chunks.jsonl 한 줄 그대로 → search()가 그대로 반환
    embedding      vector(1024)        -- 차원은 임베딩 모델에 맞춤
);
```

**검색 예시** (`<=>`는 코사인 거리. 작을수록 가깝다)

```sql
SELECT chunk, 1 - (embedding <=> :query_vector) AS score
FROM chunks
WHERE index_version = :active_version
  AND approved
  AND coalesce(chunk_kind, '') <> 'historical_addendum'
ORDER BY embedding <=> :query_vector
LIMIT :k;
```

- 이 경우 `search()`는 위 결과의 `chunk`·`score`를 그대로 돌려주면 1절 형식과 맞는다.
- 색인 교체: 새 `index_version`으로 등록·검증한 뒤 활성 버전 값만 바꾼다. 이전 버전 행은 복구용으로 남긴다 (등록 계획의 "검증 후 활성 버전 교체").
- 서로 다른 임베딩 모델의 벡터는 `index_version`으로 분리해 섞지 않는다.
- 합의되면 API 쪽에서 쓰지 않게 되는 Chroma(`app/vectorstore.py`, `/health`의 Chroma 확인)는 제거하고, `/health`는 DB 연결 확인으로 바꾼다.

---

## 5. 정해야 할 것

| # | 질문 | 담당 |
|---|---|---|
| 1 | `search()` 반환 형식(청크 그대로 + 점수)에 동의하는가? | 검색 |
| 2 | `k` 기본값, unknown 점수 기준, 과거 부칙 제외 방식 | 검색 |
| 3 | 벡터 저장소: **API 추천은 Neon PostgreSQL + pgvector** ([4.5절](#45-벡터-저장소-추천-neon-postgresql--pgvector)). 임베딩 모델(한국어 품질·차원·입력 길이·비용) | 검색 · API |
| 4 | `generate()` 형식, 인용·서식 규칙, `clarify` 기준 | 생성 |
| 5 | 링크는 `action_keys`(이름만)로 받는 방식 | 생성 · API |
| 6 | sources = 전달한 근거 전체 (인용 안 된 것은 FE가 흐리게) | 생성 · FE |
| 7 | `locator`·`snippet` 문구 규칙 | 검색 · FE |
| 8 | 승인 전(`index_approved=false`) 청크로 **개발용** 색인을 만들어 시험해도 되는가 (현재 승인 0개) | 팀 |
| 9 | 부서 연락처 표 (공식 조직도 기준) | 업무·자료 |

## 합의 후 순서

1. 검색·생성 담당이 함수 뼈대(가짜 결과를 돌려주는 버전)를 먼저 올린다.
2. API가 `rag.answer`를 mock에서 조립 코드로 바꾸고, 합성 청크로 FE → API → DB 계약 테스트를 만든다.
3. 승인 목록 → 임베딩 등록 → 실제 검색 → 실제 생성 순으로 교체한다. 각 단계마다 개발용 질문으로 확인한다 (FAQ는 최종평가 전까지 제외).

## 검증 기록

- `src/api/test_sources.py`: 형식별 합성 청크로 `locator`·`snippet`·날짜·다운로드 버튼 규칙 확인 (실제 청크는 Git에 없음).
- 로컬 실제 청크 178개: `chunk_to_source()` 178/178 통과, 서식 다운로드 버튼 10개, 빈 발췌문 0개.
- 4.5절 SQL: `pgvector/pgvector:pg17` 로컬 컨테이너에서 표 생성·검색 실행. 합성 벡터 5행 중 과거 부칙·미승인·다른 색인 버전이 제외되고 가까운 순으로 2행 반환, `jsonb`의 중첩 `source_locator` 보존 확인. 실제 임베딩·Neon 적용은 하지 않음.
