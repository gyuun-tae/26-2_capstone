import type { ChatRequest, ChatResponse, Citation } from '../api/types'

/**
 * Figma 프로토타입(03~06) 시나리오를 재현하는 목업 응답.
 * 원문 발췌는 Figma 06 화면에 쓰인 내용만 사용한다. 수집하지 않은 절차는
 * 지어내지 않고 '근거 부족' 응답으로 돌려 WF-06 상태를 시연한다.
 */

const RETRIEVED_AT = '2026-09-23'

const PORT_MIS_URL = 'https://portmis.go.kr/'
const YGPA_HOME_URL = 'https://www.ygpa.or.kr/'
// 캡스톤 계획서 참고자료 13번: 민원서비스 — Port-MIS 항만시설 이용절차 안내
const YGPA_PORTMIS_GUIDE_URL =
  'https://www.ygpa.or.kr/hmpg/ygpa/mwse/pmis/pmpr/pm01/contPageDetail.do?conts_no=D7600AC6607F41F1B506538F6CD0870E'

const facilityProcedure: Citation = {
  id: 1,
  source_type: 'web',
  title: '항만시설 이용절차',
  path: 'Port-MIS / 항만시설 이용안내',
  publisher: '여수광양항만공사',
  section: '외항선 입출항 수속',
  page: null,
  last_modified: null,
  retrieved_at: RETRIEVED_AT,
  excerpt: {
    heading: '원문 발췌 · 등록 확인',
    quotes: ['신고전 사용자등록신청 (ID,Password 등록)', '선박제원등록여부'],
    note: '도식 요약: 선박 제원이 미등록이면 제원신고서를 제출합니다. 입항보고 전에는 입출항 이력조회로 항차도 확인합니다.',
  },
  supports: '입항보고 전 사용자 등록과 선박 제원 등록 여부를 확인하세요.',
  url: YGPA_PORTMIS_GUIDE_URL,
  language: 'ko',
}

const tourGuide: Citation = {
  id: 1,
  source_type: 'web',
  title: '항만시설 견학 신청',
  path: '민원서비스 / 견학 신청',
  publisher: '여수광양항만공사',
  section: '견학 신청 안내',
  page: null,
  last_modified: null,
  retrieved_at: RETRIEVED_AT,
  excerpt: {
    heading: '원문 발췌',
    quotes: [],
    note: '목업 데이터: 원문 발췌는 크롤링 데이터 연동 후 표시됩니다.',
  },
  supports: '항만시설 견학은 YGPA 홈페이지에서 신청할 수 있어요.',
  url: YGPA_HOME_URL,
  language: 'ko',
}

const now = () => new Date().toISOString()
const newId = (prefix: string) => `${prefix}_${Math.random().toString(36).slice(2, 10)}`

function arrivalOverview(): ChatResponse {
  return {
    id: 'resp_arrival_overview',
    type: 'clarify',
    title: '입항 절차를 간단히 정리해드릴게요',
    short_title: '입항 개요',
    lead: '공통적인 입항 절차에 대해 안내해 드릴게요. 사용자·선박 등록 여부를 먼저 확인하고, 선박 구분에 맞는 입항보고를 진행합니다.',
    options: [
      {
        id: 'foreign',
        label: '외항선',
        title: '외항선 입항',
        description: '외항선 입항보고와 화물 유무에 따른 신고·항만시설 사용 절차를 확인해요.',
        cta_label: '외항선 절차 자세히',
      },
      {
        id: 'domestic',
        label: '내항선',
        title: '내항선 입항',
        description: '내항선 입항보고와 화물 유무에 따른 신고·항만시설 사용 절차를 확인해요.',
        cta_label: '내항선 절차 자세히',
      },
    ],
    citations: [],
    actions: [],
    source_language: 'ko',
    generated_at: now(),
  }
}

function foreignArrival(): ChatResponse {
  return {
    id: newId('resp'),
    type: 'answer',
    title: '외항선 입항 절차',
    short_title: '외항선 입항 절차',
    layout_hint: 'expanded',
    summary: {
      title: '외항선 입항 절차',
      text: '입항보고 전 사용자 등록과 선박 제원 등록 여부를 확인하세요.',
      citation_ids: [1],
      label: '원문 요약',
    },
    sections: [
      {
        kind: 'steps',
        title: '진행 순서',
        items: [
          { text: '사용자 등록 여부 확인' },
          { text: '선박 제원 등록 여부 확인' },
          { text: '항차 확인 후 외항선 입항보고' },
          { text: '화물 유무에 따른 통합화물신고' },
          { text: '항만시설 사용 신청·신고' },
        ],
        note: '선박·화물 조건에 따라 필요한 신고가 달라질 수 있어요.',
      },
    ],
    citations: [facilityProcedure],
    actions: [
      { id: 'portmis', label: 'Port-MIS 열기', url: PORT_MIS_URL, kind: 'primary', external: true },
    ],
    source_language: 'ko',
    generated_at: now(),
  }
}

function tourApplication(): ChatResponse {
  return {
    id: newId('resp'),
    type: 'answer',
    title: '항만시설 견학 신청 안내',
    short_title: '견학 신청 안내',
    lead: '항만시설 견학은 YGPA 홈페이지에서 신청할 수 있어요.\n신청 페이지에서 희망 일정과 방문 정보를 확인해 주세요.',
    sections: [],
    citations: [tourGuide],
    actions: [
      {
        id: 'tour',
        label: '견학 신청하기',
        url: YGPA_HOME_URL,
        kind: 'primary',
        external: true,
        note: '신청 시 YGPA 홈페이지 로그인이 필요합니다.',
      },
    ],
    source_language: 'ko',
    generated_at: now(),
  }
}

function insufficient(topic?: string): ChatResponse {
  return {
    id: newId('resp'),
    type: 'insufficient',
    title: '확인할 근거가 부족해요',
    lead: `현재 확인한 공식 자료만으로는 ${topic ? `${topic}에 대한` : '이 질문에 대한'} 답을 확정하기 어려워요. 중요한 업무 판단은 원문 또는 담당부서를 통해 확인해 주세요.`,
    searched_scope: 'YGPA 홈페이지 민원서비스·항만운영 안내 (목업 데이터 범위)',
    citations: [],
    actions: [
      { id: 'home', label: 'YGPA 홈페이지', url: YGPA_HOME_URL, kind: 'secondary', external: true },
    ],
    source_language: 'ko',
    generated_at: now(),
  }
}

/** 요청 → 목업 응답. null이면 핸들러가 500(기술 오류)을 돌려준다. */
export function resolveScenario(req: ChatRequest): ChatResponse | null {
  if (req.clarification?.response_id === 'resp_arrival_overview') {
    return req.clarification.option_id === 'foreign'
      ? foreignArrival()
      : insufficient('내항선 입항 절차')
  }

  const q = req.message.replace(/\s+/g, '')
  if (q.includes('오류테스트')) return null
  if (/외항선/.test(q)) return foreignArrival()
  if (/입항|출항|입출항/.test(q)) return arrivalOverview()
  if (/견학/.test(q)) return tourApplication()
  if (/사용료/.test(q)) return insufficient('항만시설 사용료')
  if (/배후단지|입주/.test(q)) return insufficient('배후단지 입주')
  return insufficient()
}
