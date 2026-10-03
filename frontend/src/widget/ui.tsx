import { ArrowUpRight, Download, Phone } from 'lucide-react'
import type { MouseEvent } from 'react'
import type { Action } from '../api/types'
import styles from './ui.module.css'

const MASCOT_SRC = `${import.meta.env.BASE_URL}assets/guidongi-face.svg`

/** 귀동이 얼굴. 매뉴얼상 비율·색상 변경 금지 → 크기만 조절한다. */
export function Mascot({ size = 44 }: { size?: number }) {
  return <img className={styles.mascot} src={MASCOT_SRC} width={size} height={size} alt="" aria-hidden="true" />
}

interface CitationChipProps {
  id: number
  active?: boolean
  /** 근거 목록(sources)이 아직 도착하지 않은 스트리밍 중 */
  pending?: boolean
  onOpen: (id: number, trigger: HTMLElement) => void
}

export function CitationChip({ id, active = false, pending = false, onOpen }: CitationChipProps) {
  return (
    <button
      type="button"
      className={styles.chip}
      aria-pressed={active}
      aria-label={pending ? `근거 자료 ${id} 불러오는 중` : `근거 자료 ${id} 보기`}
      disabled={pending}
      onClick={(e: MouseEvent<HTMLButtonElement>) => onOpen(id, e.currentTarget)}
    >
      [{id}]
    </button>
  )
}

interface ActionLinkProps {
  action: Action
  variant?: 'primary' | 'secondary'
  block?: boolean
}

/** 외부 링크·서식 다운로드는 새 탭으로 열고, 스크린리더에 새 탭임을 알린다. */
export function ActionLink({ action, variant = 'secondary', block = false }: ActionLinkProps) {
  const className = [styles.button, variant === 'primary' ? styles.primary : styles.secondary, block ? styles.block : ''].join(' ')
  const Icon = action.type === 'download' ? Download : ArrowUpRight
  return (
    <a className={className} href={action.url ?? undefined} target="_blank" rel="noopener noreferrer">
      {action.label}
      <Icon size={18} aria-hidden="true" />
      <span className="sr-only">(새 탭)</span>
    </a>
  )
}

/** 담당 부서 연락처 카드. 전화번호는 복사할 수 있게 글자로도 보여준다 */
export function ContactCard({ action }: { action: Action }) {
  return (
    <div className={styles.contact}>
      <span className={styles.contactIcon} aria-hidden="true">
        <Phone size={16} />
      </span>
      <div className={styles.contactBody}>
        <p className={styles.contactLabel}>{action.label}</p>
        {action.phone && (
          <a className={styles.contactPhone} href={`tel:${action.phone.replace(/[^\d+]/g, '')}`}>
            {action.phone}
          </a>
        )}
        {action.note && <p className={styles.contactNote}>{action.note}</p>}
      </div>
    </div>
  )
}
