import type { LucideIcon } from 'lucide-react'
import { Building2, FileText, MapPin, MessageSquare, Monitor, Network, ReceiptText, Ship } from 'lucide-react'

/** 웰컴 화면의 "업무 바로 찾기" 카드 (Figma 02). 기관 메뉴가 아니라 과업 기준으로 묶는다. */
export type Task =
  | { id: string; label: string; icon: LucideIcon; kind: 'ask'; question: string }
  | { id: string; label: string; icon: LucideIcon; kind: 'link'; url: string }

export const TASKS: Task[] = [
  { id: 'arrival', label: '선박 입·출항', icon: Ship, kind: 'ask', question: '선박 입·출항 절차를 알려주세요.' },
  { id: 'portmis', label: 'Port-MIS', icon: Monitor, kind: 'link', url: 'https://portmis.go.kr/' },
  { id: 'fee', label: '항만시설 사용료', icon: ReceiptText, kind: 'ask', question: '항만시설 사용료는 어떻게 확인하나요?' },
  { id: 'hinterland', label: '배후단지 입주', icon: Building2, kind: 'ask', question: '배후단지 입주 절차를 알려주세요.' },
  { id: 'forms', label: '서식 찾기', icon: FileText, kind: 'ask', question: '필요한 신청 서식을 찾고 싶어요.' },
  { id: 'department', label: '담당부서 찾기', icon: Network, kind: 'ask', question: '담당부서를 찾고 싶어요.' },
  { id: 'tour', label: '항만시설 견학', icon: MapPin, kind: 'ask', question: '견학 신청은 어디서 하나요?' },
  { id: 'civil', label: '민원·신고', icon: MessageSquare, kind: 'ask', question: '민원이나 신고는 어떻게 하나요?' },
]

export const EXAMPLE_QUESTIONS = ['입항 절차를 알려주세요.', '견학 신청은 어디서 하나요?']
