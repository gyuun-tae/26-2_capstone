import type { PointerEvent as ReactPointerEvent, RefObject } from 'react'
import styles from './ResizeHandles.module.css'

export interface PanelSize {
  w: number
  h: number
}

interface Edges {
  left?: boolean
  right?: boolean
  top?: boolean
}

interface ResizeHandlesProps {
  panelRef: RefObject<HTMLElement | null>
  /** 가운데 정렬된 확장 패널이면 좌우를 대칭으로 늘린다 */
  centered: boolean
  minWidth: number
  minHeight: number
  /** 화면 가장자리와 패널 사이에 남길 여백 (--widget-gap) */
  gap: number
  onCommit: (size: PanelSize) => void
  onReset: () => void
}

const HINT = '드래그해서 크기 조절 · 더블클릭하면 기본 크기'

// 최솟값이 화면보다 크면 화면에 맞춘다
const clamp = (value: number, min: number, max: number) => Math.max(Math.min(value, max), Math.min(min, max))

/**
 * 패널 가장자리 크기 조절 손잡이.
 * 드래그 중에는 React 상태를 거치지 않고 --panel-w/--panel-h를 직접 바꿔 끊김을 없애고,
 * 손을 뗄 때 한 번만 상태로 반영한다. 포인터 전용 보조 기능이라 스크린리더에서는 숨긴다
 * (키보드 사용자는 "크게 보기" 버튼으로 확장 화면을 쓸 수 있다).
 */
export function ResizeHandles({ panelRef, centered, minWidth, minHeight, gap, onCommit, onReset }: ResizeHandlesProps) {
  const startResize = (edges: Edges) => (e: ReactPointerEvent<HTMLDivElement>) => {
    const panel = panelRef.current
    if (!panel || e.button !== 0) return
    e.preventDefault() // 드래그 중 텍스트 선택 방지

    const handle = e.currentTarget
    const pointerId = e.pointerId
    try {
      handle.setPointerCapture(pointerId)
    } catch {
      // 합성 이벤트 등으로 캡처할 수 없는 경우에도 window 리스너로 동작한다
    }

    const rect = panel.getBoundingClientRect()
    const viewport = window.visualViewport
    const maxW = (viewport?.width ?? window.innerWidth) - 2 * gap
    const maxH = (viewport?.height ?? window.innerHeight) - 2 * gap
    const factor = centered ? 2 : 1
    const startX = e.clientX
    const startY = e.clientY
    let next: PanelSize | null = null

    panel.dataset.resizing = ''

    const onMove = (ev: PointerEvent) => {
      const dx = ev.clientX - startX
      const dy = ev.clientY - startY
      let w = rect.width
      let h = rect.height
      if (edges.left) w -= dx * factor
      if (edges.right) w += dx * factor
      if (edges.top) h -= dy
      next = { w: Math.round(clamp(w, minWidth, maxW)), h: Math.round(clamp(h, minHeight, maxH)) }
      panel.style.setProperty('--panel-w', `${next.w}px`)
      panel.style.setProperty('--panel-h', `${next.h}px`)
    }

    const onEnd = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onEnd)
      window.removeEventListener('pointercancel', onEnd)
      delete panel.dataset.resizing
      // 클릭만 하고 움직이지 않았으면 기본 크기 추종을 유지한다
      if (next) onCommit(next)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onEnd)
    window.addEventListener('pointercancel', onEnd)
  }

  const handle = (className: string, edges: Edges) => (
    <div
      className={`${styles.handle} ${className}`}
      aria-hidden="true"
      title={HINT}
      onPointerDown={startResize(edges)}
      onDoubleClick={onReset}
    />
  )

  return (
    <>
      {handle(styles.top, { top: true })}
      {handle(styles.left, { left: true })}
      {handle(styles.topLeft, { top: true, left: true })}
      {centered && handle(styles.right, { right: true })}
      {centered && handle(styles.topRight, { top: true, right: true })}
    </>
  )
}
