import { ArrowUpRight } from 'lucide-react'
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
  onOpen: (id: number, trigger: HTMLElement) => void
}

export function CitationChip({ id, active = false, onOpen }: CitationChipProps) {
  return (
    <button
      type="button"
      className={styles.chip}
      aria-pressed={active}
      aria-label={`근거 자료 ${id} 보기`}
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

/** 외부 링크(↗)는 새 탭으로 열고, 스크린리더에 새 탭임을 알린다. */
export function ActionLink({ action, variant = action.kind, block = false }: ActionLinkProps) {
  const className = [
    styles.button,
    variant === 'primary' ? styles.primary : styles.secondary,
    block ? styles.block : '',
  ].join(' ')
  return (
    <a
      className={className}
      href={action.url}
      {...(action.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
    >
      {action.label}
      {action.external && (
        <>
          <ArrowUpRight size={18} aria-hidden="true" />
          <span className="sr-only">(새 탭)</span>
        </>
      )}
    </a>
  )
}
