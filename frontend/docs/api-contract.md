# YGPA AI 업무도우미 — API 계약 v0.1 (초안)

프론트엔드(React)와 백엔드(FastAPI)가 주고받는 형식. 타입 원본은 [`src/api/types.ts`](../src/api/types.ts)이고, 백엔드 Pydantic 모델은 필드명을 그대로 맞춘다. 이 문서나 타입을 바꾸면 두 곳을 함께 고친다.

## 설계 원칙

- **답변 → 근거 → 다음 행동**: 모든 응답은 `citations`(근거)와 `actions`(다음 행동)를 함께 돌려준다.
- **근거 부족 ≠ 기술 오류**: 근거를 못 찾은 경우는 HTTP 200 + `type: "insufficient"`로 응답한다. 서버 장애만 4xx/5xx로 보낸다. 화면도 서로 다르다.
- **가짜 값 금지**: PDF 페이지·수정일을 정확히 알 수 없으면 `null`로 보낸다. 프론트엔드는 `null`을 "원문 미표기"로 보여준다.
- **되묻기는 답을 바꾸는 조건일 때만**: 예를 들어 외항선인지 내항선인지에 따라 절차가 다를 때만 `type: "clarify"`를 쓴다.

## `POST /api/chat`

### 요청

```json
{
  "message": "입항 절차를 알려주세요.",
  "session_id": "8f1c…",
  "locale": "ko"
}
```

조건 확인에서 선택지를 고르면 같은 질문에 `clarification`을 붙여 다시 보낸다.

```json
{
  "message": "입항 절차를 알려주세요.",
  "session_id": "8f1c…",
  "locale": "ko",
  "clarification": { "response_id": "resp_arrival_overview", "option_id": "foreign" }
}
```

### 응답 — `type` 세 가지

| type | 화면 (Figma) | 필수 필드 |
|---|---|---|
| `clarify` | 04 Compact_Overview — 외항선/내항선 선택 카드 | `options[]` |
| `answer` | 03 Simple(짧은 답 + 버튼) / 05 Expanded(요약 + 절차) | `sections[]`, 선택: `summary`, `layout_hint` |
| `insufficient` | WF-06 근거 부족 안내 | 선택: `searched_scope` |

공통 필드: `id`, `title`, `short_title?`, `lead?`, `citations[]`, `actions[]`, `source_language`, `generated_at`

- `summary`가 있으면 요약 카드와 절차형 상세 화면(05)으로, 없으면 짧은 답변과 행동 버튼(03)으로 그린다.
- `layout_hint: "expanded"`이면 프론트엔드가 확장 화면으로 자동 전환한다.
- `short_title`은 뒤로가기 링크 문구로 쓴다. 예: `‹ 입항 개요`

#### 예시: 상세 답변 (Figma 05·06)

```json
{
  "id": "resp_91ab",
  "type": "answer",
  "title": "외항선 입항 절차",
  "short_title": "외항선 입항 절차",
  "layout_hint": "expanded",
  "summary": {
    "title": "외항선 입항 절차",
    "text": "입항보고 전 사용자 등록과 선박 제원 등록 여부를 확인하세요.",
    "citation_ids": [1],
    "label": "원문 요약"
  },
  "sections": [
    {
      "kind": "steps",
      "title": "진행 순서",
      "items": [{ "text": "사용자 등록 여부 확인" }, { "text": "선박 제원 등록 여부 확인" }],
      "note": "선박·화물 조건에 따라 필요한 신고가 달라질 수 있어요."
    }
  ],
  "citations": [
    {
      "id": 1,
      "source_type": "web",
      "title": "항만시설 이용절차",
      "path": "Port-MIS / 항만시설 이용안내",
      "publisher": "여수광양항만공사",
      "section": "외항선 입출항 수속",
      "page": null,
      "last_modified": null,
      "retrieved_at": "2026-09-23",
      "excerpt": {
        "heading": "원문 발췌 · 등록 확인",
        "quotes": ["신고전 사용자등록신청 (ID,Password 등록)", "선박제원등록여부"],
        "note": "도식 요약: 선박 제원이 미등록이면 제원신고서를 제출합니다."
      },
      "supports": "입항보고 전 사용자 등록과 선박 제원 등록 여부를 확인하세요.",
      "url": "https://www.ygpa.or.kr/…",
      "language": "ko"
    }
  ],
  "actions": [
    { "id": "portmis", "label": "Port-MIS 열기", "url": "https://portmis.go.kr/", "kind": "primary", "external": true }
  ],
  "source_language": "ko",
  "generated_at": "2026-09-29T04:00:00Z"
}
```

### Citation 필드 ↔ 근거 패널(Figma 06) 매핑

| 화면 요소 | 필드 | RAG 메타데이터 출처 |
|---|---|---|
| "공식 웹자료 · [1]" | `source_type`, `id` | 문서 유형 |
| 제목 / 경로 | `title`, `path` | `document_title`, 사이트 breadcrumb |
| 출처 | `publisher` | 발행 기관 |
| 관련 항목 | `section` (+ `page`) | 조·항, 섹션 anchor, PDF 페이지 |
| 원문 수정일 | `last_modified` | 원문에 표시된 개정·시행일 |
| 원문 발췌 | `excerpt.quotes`, `excerpt.note` | 검색된 청크 원문 |
| 이 근거가 뒷받침하는 답변 | `supports` | 인용 매핑 결과 |
| 원문 보기 / 확인일 | `url`, `retrieved_at` | `source_url`, 크롤링 일자 |

청킹할 때 위 메타데이터를 함께 저장해 두어야 근거 패널을 채울 수 있다.

### 오류

| 상황 | 응답 | 프론트엔드 화면 |
|---|---|---|
| 근거를 찾지 못함 | 200 + `type: "insufficient"` | 근거 부족 안내 + 관련 링크 + "질문 구체화하기" |
| 서버 오류, 타임아웃 | 5xx | "답변을 불러오지 못했습니다" + 다시 시도 + 공식 메뉴 링크 |
| 네트워크 끊김 | fetch 실패 | 위와 같음 |

## `POST /api/feedback` (2단계에서 UI 연결)

```json
{ "response_id": "resp_91ab", "helpful": false, "reason": "weak_evidence", "comment": "선택" }
```

`reason`: `misunderstood` | `weak_evidence` | `outdated` | `missing_action` | `other`

## 이후 논의할 것

- 스트리밍: SSE로 토큰을 흘려보낼지, 완성된 JSON을 한 번에 보낼지 (응답 목표 5초 이내)
- 영어 질의: `locale: "en"`으로 물었는데 원문이 한국어면 `source_language: "ko"`로 표시
- 실시간 운영정보(선석 등)와 정적 규정을 `source_type`으로 구분할지
