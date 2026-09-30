/**
 * YGPA AI 업무도우미 — 프론트엔드 ↔ FastAPI 응답 계약 (v0.1 초안)
 *
 * 백엔드(Pydantic 모델)와 이 파일의 필드명을 1:1로 맞춘다. 사람이 읽는 설명은
 * docs/api-contract.md 참고. 필드를 바꾸면 두 곳을 함께 고친다.
 */

export type Locale = 'ko' | 'en'

// ── 요청 ────────────────────────────────────────────────

export interface ChatRequest {
  /** 사용자가 입력(또는 카드로 선택)한 원문 질문 */
  message: string
  /** 익명 세션 식별자. 개인정보가 아닌 무작위 값 */
  session_id?: string
  locale?: Locale
  /** 조건 확인(clarify) 응답에서 선택지를 고른 경우 */
  clarification?: {
    /** 선택지가 들어 있던 clarify 응답의 id */
    response_id: string
    option_id: string
  }
}

export interface FeedbackRequest {
  response_id: string
  helpful: boolean
  /** 👎 일 때만: 질문을 잘못 이해함 / 근거 부족 / 정보가 오래됨 / 원하는 링크 없음 / 기타 */
  reason?: 'misunderstood' | 'weak_evidence' | 'outdated' | 'missing_action' | 'other'
  comment?: string
}

// ── 근거(Citation) ─────────────────────────────────────

export type SourceType = 'web' | 'pdf' | 'regulation' | 'notice'

export interface Citation {
  /** 답변 본문의 [n] 번호와 같은 값 (1부터) */
  id: number
  source_type: SourceType
  /** 문서/페이지 제목. 예: "항만시설 이용절차" */
  title: string
  /** 사이트 내 위치나 규정 계층. 예: "Port-MIS / 항만시설 이용안내" */
  path?: string
  /** 발행 기관. 예: "여수광양항만공사" */
  publisher: string
  /** 관련 항목·조항. 예: "외항선 입출항 수속", "제12조 제2항" */
  section?: string
  /** PDF 페이지. 정확히 매핑하지 못하면 null — 가짜 번호를 만들지 않는다 */
  page?: number | null
  /** 원문에 표시된 수정·시행일(YYYY-MM-DD). 원문에 없으면 null → "원문 미표기" */
  last_modified: string | null
  /** 크롤러가 원문을 확인한 날짜(YYYY-MM-DD) */
  retrieved_at: string
  /** 답변에 실제로 사용된 원문 구간 */
  excerpt: {
    heading?: string
    quotes: string[]
    /** 표·도식처럼 인용이 어려운 부분의 요약 */
    note?: string
  }
  /** 이 근거가 뒷받침하는 답변 문장 */
  supports: string
  url: string
  language: Locale
}

// ── 다음 행동(Action) ───────────────────────────────────

export interface Action {
  id: string
  label: string
  url: string
  kind: 'primary' | 'secondary'
  /** true면 새 탭으로 열고 ↗ 표시 */
  external: boolean
  /** 버튼 아래 보조 문구. 예: "신청 시 YGPA 홈페이지 로그인이 필요합니다." */
  note?: string
}

// ── 응답 ────────────────────────────────────────────────

interface ResponseBase {
  id: string
  /** 화면 제목. 예: "입항 절차를 간단히 정리해드릴게요" */
  title: string
  /** 뒤로가기 링크에 쓰는 짧은 이름. 예: "입항 개요" */
  short_title?: string
  /** 제목 아래 안내 문단 */
  lead?: string
  citations: Citation[]
  actions: Action[]
  /** 답변 근거 원문의 언어. 영어 질문에 한국어 원문이면 'ko' */
  source_language: Locale
  generated_at: string
}

export interface SummaryBlock {
  title: string
  text: string
  citation_ids: number[]
  /** 요약 카드 우측 라벨. 예: "원문 요약" */
  label?: string
}

export type AnswerSection =
  | {
      kind: 'steps'
      title: string
      items: { text: string; citation_ids?: number[] }[]
      note?: string
    }
  | {
      kind: 'paragraph'
      title?: string
      text: string
      citation_ids?: number[]
    }

/** 근거에 기반한 답변 (WF-04) */
export interface AnswerResponse extends ResponseBase {
  type: 'answer'
  /** 있으면 요약 카드 + 절차형 상세 답변, 없으면 짧은 답변 + 행동 버튼 */
  summary?: SummaryBlock
  sections: AnswerSection[]
  /** 백엔드가 권하는 표시 방식. 'expanded'면 확장 화면으로 전환 */
  layout_hint?: 'compact' | 'expanded'
}

export interface ClarifyOption {
  id: string
  /** 메타 줄에 쓰는 짧은 이름. 예: "외항선" */
  label: string
  title: string
  description: string
  cta_label: string
}

/** 답을 바꾸는 조건만 되묻기 (WF-03) */
export interface ClarifyResponse extends ResponseBase {
  type: 'clarify'
  options: ClarifyOption[]
}

/** 근거 부족 — 기술 오류와 구분되는 정상 응답 (WF-06) */
export interface InsufficientResponse extends ResponseBase {
  type: 'insufficient'
  /** 확인한 자료 범위. 예: "YGPA 홈페이지 민원서비스·항만운영 안내" */
  searched_scope?: string
}

export type ChatResponse = AnswerResponse | ClarifyResponse | InsufficientResponse
