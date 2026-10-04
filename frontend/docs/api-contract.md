# 채팅 API — 프론트엔드가 따르는 형식

기준은 백엔드 `feat/api-server`의 [`src/api/app/schemas.py`](../../src/api/app/schemas.py)와 `main.py`다(0f48ee4). 프론트엔드 타입은 [`src/api/types.ts`](../src/api/types.ts)에 1:1로 옮겼다. 백엔드 형식이 바뀌면 이 두 파일을 함께 고친다.

## 경로

| 용도 | 백엔드 | 프론트엔드 호출 |
|---|---|---|
| 질문 | `POST /chat` (SSE) | `POST {VITE_API_BASE_URL}/chat` — 개발 서버는 `/api/chat`을 `localhost:8000/chat`으로 프록시 |
| 피드백 | `PUT /messages/{message_id}/feedback` | 👍·👎 버튼 |

## 요청

```json
{ "messages": [
  { "role": "user", "content": "입항 절차 알려주세요" },
  { "role": "assistant", "content": "외항선인지 내항선인지에 따라 절차가 달라요. 어느 쪽인가요?" },
  { "role": "user", "content": "외항선" }
] }
```

- 화면에 쌓여 있는 질문·답변을 순서대로 보낸다. "‹ 이전 안내"로 돌아간 화면은 빠지고, "전체 업무 보기"로 가면 대화가 비워진다.
- 최근 20개까지 보낸다. 마지막은 항상 이번 질문(`user`)이다.

## 응답 — SSE

`token`(여러 번) → `sources` → `done`. 도중에 실패하면 `done` 대신 `error`로 끝난다.

```text
event: token
data: {"text": "외항선은 입항보고 전에 사용자 등록과 선박 제원 등록 여부를 먼저 확인해야 합니다[1].\n\n"}

event: sources
data: [{"doc_id": "…", "chunk_id": "…", "title": "…", "source_url": "…", "locator": "…",
        "published_at": null, "updated_at": null, "date_status": "not_displayed",
        "fetched_at": "2026-09-23T10:00:00+09:00", "snippet": "…"}]

event: done
data: {"message_id": 42, "answer_type": "answer", "actions": [], "options": []}
```

### 화면 대응

| 백엔드 값 | 화면 |
|---|---|
| 첫 `token` 전 | "관련 YGPA 안내자료와 규정을 확인하고 있어요" |
| `token` | 답변을 도착하는 대로 표시 (입력 커서) |
| 답변에 번호 목록(`1.` `2.`)이 2개 이상 | 첫 문단 → "한눈에 보기" 카드, 번호 목록 → "진행 순서". 확장 화면으로 전환 |
| 답변 속 `[n]` | `sources[n-1]`을 여는 인용 버튼. 근거 패널에 `[n]`이 붙은 문장을 모아 보여준다 |
| `answer_type: "clarify"` | 답변 문구 + `options`가 있으면 선택지 버튼 |
| `answer_type: "unknown"` | "확인할 근거가 부족해요" 안내 + `actions` |
| `error` 이벤트, HTTP 오류, 75초 동안 이벤트 없음 | "답변을 불러오지 못했습니다" + 다시 시도 (질문 보관) |

### 근거(`Source`) 표시

| 필드 | 근거 패널 |
|---|---|
| `title`, `source_url` | 제목, 사이트 주소, "원문 보기" |
| `locator` | 관련 항목 |
| `date_status` + `published_at`/`updated_at` | 원문 날짜. `not_displayed`면 "원문 미표기" — 수집일로 채우지 않는다 |
| `date_status: "official_api_current"` + `effective_at` | 법령·고시. "2026.02.27 시행 (2025.10.24 공포)" — 시행일이 지금 적용 기준 |
| `snippet` | 원문 발췌 |
| `fetched_at` | 자료 확인일 |

## v0.2 제안 필드 (선택)

백엔드가 아직 보내지 않아도 화면은 동작한다. 보내면 아래처럼 쓴다.

- `done.actions[]`: `{ type: "link" | "download" | "contact", label, url?, phone?, note?, source_ref? }`
  - `link`·`download` → 버튼 (절차형 답변은 하단 "다음 단계" 바), `contact` → 담당 부서 카드
  - url·전화번호는 LLM이 만들지 않고 검증된 메타데이터나 허용 목록에서만 채운다
- `done.options[]`: `{ label }` — `clarify`일 때 선택지 버튼. 누르면 `label`을 다음 `user` 메시지로 보낸다
- 답변 서식: 요약 한두 문장 → `1.` 번호 목록(절차) → 필요하면 `-` 목록. `**굵게**`, 문장 끝 `[n]`까지만 쓴다

## 개발용 목업

`src/mocks/`의 MSW가 같은 SSE 형식으로 응답한다(기본 켜짐). 입력별 시나리오는 [README](../README.md#목업으로-볼-수-있는-시나리오)를 참고한다.
