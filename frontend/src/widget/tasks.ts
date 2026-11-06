import type { LucideIcon } from 'lucide-react'
import { Building2, FileText, MapPin, MessageSquare, Monitor, Network, ReceiptText, Ship } from 'lucide-react'
import type { UiLang } from './i18n'

/** 웰컴 화면의 "업무 바로 찾기" 카드 (Figma 02). 기관 메뉴가 아니라 과업 기준으로 묶는다. 화면 언어별 글 (영·일·중은 검토 전 초안) */
type Text = Record<UiLang, string>
export type Task =
  | { id: string; label: Text; icon: LucideIcon; kind: 'ask'; question: Text }
  | { id: string; label: Text; icon: LucideIcon; kind: 'link'; url: string }

// Port-MIS 주소: 옛 portmis.go.kr은 410(종료) — 백엔드 app/actions.py와 같은 새 주소
export const PORT_MIS_URL = 'https://new.portmis.go.kr/'

export const TASKS: Task[] = [
  {
    id: 'arrival', icon: Ship, kind: 'ask',
    label: { ko: '선박 입·출항', en: 'Vessel arrival/departure', ja: '船舶の入出港', zh: '船舶进出港' },
    question: {
      ko: '선박 입·출항 절차를 알려주세요.',
      en: 'What is the procedure for vessel arrival and departure?',
      ja: '船舶の入出港の手続きを教えてください。',
      zh: '请告诉我船舶进出港的手续。',
    },
  },
  { id: 'portmis', icon: Monitor, kind: 'link', label: { ko: 'Port-MIS', en: 'Port-MIS', ja: 'Port-MIS', zh: 'Port-MIS' }, url: PORT_MIS_URL },
  {
    id: 'fee', icon: ReceiptText, kind: 'ask',
    label: { ko: '항만시설 사용료', en: 'Port facility fees', ja: '港湾施設使用料', zh: '港口设施使用费' },
    question: {
      ko: '항만시설 사용료는 어떻게 확인하나요?',
      en: 'How can I check port facility usage fees?',
      ja: '港湾施設使用料はどのように確認できますか？',
      zh: '港口设施使用费怎么查询？',
    },
  },
  {
    id: 'hinterland', icon: Building2, kind: 'ask',
    label: { ko: '배후단지 입주', en: 'Hinterland complex', ja: '背後団地への入居', zh: '腹地园区入驻' },
    question: {
      ko: '배후단지 입주 절차를 알려주세요.',
      en: 'How do I move into the port hinterland complex?',
      ja: '背後団地への入居手続きを教えてください。',
      zh: '请告诉我入驻腹地园区的手续。',
    },
  },
  {
    id: 'forms', icon: FileText, kind: 'ask',
    label: { ko: '서식 찾기', en: 'Find forms', ja: '書式を探す', zh: '查找表格' },
    question: {
      ko: '필요한 신청 서식을 찾고 싶어요.',
      en: 'I want to find the application form I need.',
      ja: '必要な申請書式を探したいです。',
      zh: '我想找需要的申请表格。',
    },
  },
  {
    id: 'department', icon: Network, kind: 'ask',
    label: { ko: '담당부서 찾기', en: 'Find a department', ja: '担当部署を探す', zh: '查找负责部门' },
    question: {
      ko: '담당부서를 찾고 싶어요.',
      en: 'Which department should I contact?',
      ja: 'どの部署に問い合わせればよいですか？',
      zh: '我应该联系哪个部门？',
    },
  },
  {
    id: 'tour', icon: MapPin, kind: 'ask',
    label: { ko: '항만시설 견학', en: 'Port tours', ja: '港湾施設の見学', zh: '港口设施参观' },
    question: {
      ko: '견학 신청은 어디서 하나요?',
      en: 'Where can I apply for a port tour?',
      ja: '見学の申請はどこでできますか？',
      zh: '在哪里申请参观？',
    },
  },
  {
    id: 'civil', icon: MessageSquare, kind: 'ask',
    label: { ko: '민원·신고', en: 'Complaints/reports', ja: '苦情・申告', zh: '投诉·举报' },
    question: {
      ko: '민원이나 신고는 어떻게 하나요?',
      en: 'How do I file a complaint or report?',
      ja: '苦情や申告はどのようにすればよいですか？',
      zh: '如何提出投诉或举报？',
    },
  },
]

export const EXAMPLE_QUESTIONS: Record<UiLang, string[]> = {
  ko: ['입항 절차를 알려주세요.', '견학 신청은 어디서 하나요?'],
  en: ['How do I get a port access pass?', 'Where is the Yeosu Gwangyang Port Authority head office?'],
  ja: ['港湾出入証はどうやって発行できますか？', '麗水光陽港湾公社の本社はどこですか？'],
  zh: ['港口出入证怎么办理？', '丽水光阳港湾公社的总部在哪里？'],
}
