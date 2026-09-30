/**
 * 프론트엔드 ↔ 백엔드 채팅 API 형식.
 * 기준: feat/api-server의 src/api/app/schemas.py (0f48ee4). 필드명을 1:1로 맞춘다.
 * `actions`·`options`는 v0.2 제안 필드라 선택 사항이다 — 백엔드가 보내지 않아도 동작해야 한다.
 */

// ── 요청 ────────────────────────────────────────────────

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/** POST /chat — 창이 열린 뒤의 대화. 마지막은 이번 질문(user). 최대 20개 */
export interface ChatRequest {
  messages: ChatMessage[]
}

/** PUT /messages/{message_id}/feedback */
export interface FeedbackRequest {
  rating: 'up' | 'down'
}

// ── SSE 이벤트: token → sources → done | error ─────────

/** 답변 근거 1개 (팀 청크 규격과 같은 필드명). 배열 순서가 곧 인용 번호 [1], [2]… */
export interface Source {
  doc_id: string
  chunk_id: string
  title: string
  source_url: string
  /** 화면에 보여줄 근거 위치 문구. 예: "3쪽 표 2" */
  locator: string
  /** 원문에 날짜가 없으면 null. 수집일로 채우지 않는다 */
  published_at: string | null
  updated_at: string | null
  date_status: 'not_displayed' | 'page_updated' | 'conflicting' | 'unverified_attachment' | (string & {})
  /** 수집 시각 */
  fetched_at: string | null
  snippet: string
}

export type AnswerType = 'answer' | 'clarify' | 'unknown'

/** v0.2 제안: 다음 행동 버튼·카드. url·phone은 검증된 메타데이터/허용 목록에서만 온다 */
export interface Action {
  type: 'link' | 'download' | 'contact'
  label: string
  url?: string | null
  phone?: string | null
  note?: string | null
  /** 근거가 된 sources 번호(1부터). 고정 링크면 null */
  source_ref?: number | null
}

/** v0.2 제안: clarify 선택지. 누르면 label을 다음 user 메시지로 보낸다 */
export interface ClarifyOption {
  label: string
}

export interface DoneEvent {
  message_id: number
  answer_type: AnswerType
  actions?: Action[]
  options?: ClarifyOption[]
}

export interface ErrorEvent {
  code: string
  message: string
}

export type ChatStreamEvent =
  | { event: 'token'; data: { text: string } }
  | { event: 'sources'; data: Source[] }
  | { event: 'done'; data: DoneEvent }
  | { event: 'error'; data: ErrorEvent }
