import type { Action, ChatRequest, ClarifyOption, DoneEvent, Source } from '../api/types'

/**
 * 백엔드 없이 화면을 확인하기 위한 목업 응답 (팀 SSE 형식 + v0.2 제안 필드).
 * 원문 발췌는 Figma 06 화면에 쓰인 내용만 사용한다. 수집하지 않은 절차는
 * 지어내지 않고 answer_type: 'unknown'으로 돌려 근거 부족 상태를 시연한다.
 * 문서 ID는 실제 카탈로그(YGPA-001…)와 헷갈리지 않게 MOCK 접두어를 쓴다.
 */

export interface MockReply {
  text: string
  sources: Source[]
  done: Omit<DoneEvent, 'message_id'>
  /** 이 번째 token을 보낸 뒤 error 이벤트로 끝낸다 (오류 화면 시연) */
  failAfterTokens?: number
}

const PORT_MIS_URL = 'https://portmis.go.kr/'
const YGPA_HOME_URL = 'https://www.ygpa.or.kr/'
// 캡스톤 계획서 참고자료 13번: 민원서비스 — Port-MIS 항만시설 이용절차 안내
const YGPA_PORTMIS_GUIDE_URL =
  'https://www.ygpa.or.kr/hmpg/ygpa/mwse/pmis/pmpr/pm01/contPageDetail.do?conts_no=D7600AC6607F41F1B506538F6CD0870E'

const facilityProcedure: Source = {
  doc_id: 'MOCK-PORTMIS',
  chunk_id: 'MOCK-PORTMIS-c01',
  title: '항만시설 이용절차',
  source_url: YGPA_PORTMIS_GUIDE_URL,
  locator: 'Port-MIS 항만시설 이용안내 · 외항선 입출항 수속',
  published_at: null,
  updated_at: null,
  date_status: 'not_displayed',
  fetched_at: '2026-09-23T10:00:00+09:00',
  snippet:
    '“신고전 사용자등록신청 (ID,Password 등록)”\n“선박제원등록여부”\n\n도식 요약: 선박 제원이 미등록이면 제원신고서를 제출합니다. 입항보고 전에는 입출항 이력조회로 항차도 확인합니다.',
}

const tourGuide: Source = {
  doc_id: 'MOCK-TOUR',
  chunk_id: 'MOCK-TOUR-c01',
  title: '항만시설 견학 신청',
  source_url: YGPA_HOME_URL,
  locator: '민원서비스 · 견학 신청',
  published_at: null,
  updated_at: null,
  date_status: 'not_displayed',
  fetched_at: '2026-09-23T10:00:00+09:00',
  snippet: '목업 데이터: 원문 발췌는 백엔드 연동 후 표시됩니다.',
}

const portMisLink: Action = { type: 'link', label: 'Port-MIS 열기', url: PORT_MIS_URL, source_ref: null }
const homeLink: Action = { type: 'link', label: 'YGPA 홈페이지', url: YGPA_HOME_URL, source_ref: null }
const vesselOptions: ClarifyOption[] = [{ label: '외항선' }, { label: '내항선' }, { label: '잘 모르겠어요' }]

const foreignArrival: MockReply = {
  text:
    '외항선은 입항보고 전에 사용자 등록과 선박 제원 등록 여부를 먼저 확인해야 합니다[1].\n\n' +
    '1. 사용자 등록 여부 확인[1]\n2. 선박 제원 등록 여부 확인[1]\n3. 항차 확인 후 외항선 입항보고\n' +
    '4. 화물 유무에 따른 통합화물신고\n5. 항만시설 사용 신청·신고\n\n' +
    '선박·화물 조건에 따라 필요한 신고가 달라질 수 있어요.',
  sources: [facilityProcedure],
  done: { answer_type: 'answer', actions: [portMisLink], options: [] },
}

const arrivalClarify: MockReply = {
  text: '외항선인지 내항선인지에 따라 입항 절차가 달라요. 어느 쪽인가요?',
  sources: [],
  done: { answer_type: 'clarify', actions: [], options: vesselOptions },
}

const arrivalUnsure: MockReply = {
  text: '두 경우 모두 사용자·선박 등록 여부를 먼저 확인하고, 선박 구분에 맞는 입항보고를 진행합니다. 선박 구분을 확인하신 뒤 다시 골라 주세요.',
  sources: [],
  done: { answer_type: 'clarify', actions: [], options: vesselOptions.slice(0, 2) },
}

const tourApplication: MockReply = {
  text: '항만시설 견학은 YGPA 홈페이지에서 신청할 수 있어요[1].\n신청 페이지에서 희망 일정과 방문 정보를 확인해 주세요.',
  sources: [tourGuide],
  done: {
    answer_type: 'answer',
    actions: [
      { type: 'link', label: '견학 신청하기', url: YGPA_HOME_URL, note: '신청 시 YGPA 홈페이지 로그인이 필요합니다.', source_ref: 1 },
    ],
    options: [],
  },
}

function unknown(topic?: string): MockReply {
  return {
    text: `현재 확인한 공식 자료만으로는 ${topic ? `${topic}에 대한` : '이 질문에 대한'} 답을 확정하기 어려워요. 중요한 업무 판단은 원문이나 담당부서를 통해 확인해 주세요.`,
    sources: [],
    done: { answer_type: 'unknown', actions: [homeLink], options: [] },
  }
}

/** 마지막 user 메시지로 목업 응답을 고른다 */
export function resolveScenario(req: ChatRequest): MockReply {
  const last = req.messages.at(-1)?.content ?? ''
  const q = last.replace(/\s+/g, '')

  if (q.includes('오류테스트')) return { ...unknown(), failAfterTokens: 3 }
  if (q === '외항선' || q.includes('외항선')) return foreignArrival
  if (q === '내항선' || q.includes('내항선')) return unknown('내항선 입항 절차')
  if (q === '잘모르겠어요') return arrivalUnsure
  if (/입항|출항|입출항/.test(q)) return arrivalClarify
  if (/견학/.test(q)) return tourApplication
  if (/사용료/.test(q)) return unknown('항만시설 사용료')
  if (/배후단지|입주/.test(q)) return unknown('배후단지 입주')
  return unknown()
}

/** 실제 LLM처럼 텍스트를 잘게 나눠 흘려보낸다 */
export function chunkText(text: string, size = 6): string[] {
  const chunks: string[] = []
  for (let i = 0; i < text.length; i += size) chunks.push(text.slice(i, i + size))
  return chunks
}
