import { ArrowDownLeft, ArrowUpRight, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import type { ClarifyOption } from '../api/types'
import { Composer } from './Composer'
import { HelpDialog } from './HelpDialog'
import { ResizeHandles, type PanelSize } from './ResizeHandles'
import { ActionBar, ScreenView } from './ScreenView'
import { SourcePanel } from './SourcePanel'
import { Mascot } from './ui'
import { useChat } from './useChat'
import { WelcomeView } from './WelcomeView'
import styles from './ChatWidget.module.css'

type Mode = 'compact' | 'expanded'

// 크기 조절 하한. 상한은 화면 크기(여백 제외)
const RESIZE_LIMITS: Record<Mode, { minWidth: number; minHeight: number }> = {
  compact: { minWidth: 360, minHeight: 480 },
  expanded: { minWidth: 600, minHeight: 480 },
}
const WIDGET_GAP = 24

/**
 * 홈페이지 우측 하단 런처 → 440px 컴팩트 패널 → 확장 업무 화면(+근거 패널).
 * 간단한 문의는 컴팩트에서 끝내고, 근거 확인·절차형 답변은 확장 화면으로 보낸다.
 */
export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<Mode>('compact')
  const [citationId, setCitationId] = useState<number | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  // 사용자가 조절한 크기. null이면 기본 크기(tokens.css). 모드별로 따로 기억한다
  const [sizes, setSizes] = useState<Record<Mode, PanelSize | null>>({ compact: null, expanded: null })

  const panelRef = useRef<HTMLElement>(null)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const citationTriggerRef = useRef<HTMLElement | null>(null)
  const wasOpenRef = useRef(false)

  const chat = useChat({
    onResponse: (response) => {
      if (response.type === 'answer' && response.layout_hint === 'expanded') setMode('expanded')
      setAnnouncement(`답변을 불러왔습니다. ${response.title}`)
    },
  })
  const { current, previous } = chat
  const response = current?.status === 'success' ? current.response : undefined
  const citations = response?.citations ?? []
  const activeCitation = mode === 'expanded' ? (citations.find((c) => c.id === citationId) ?? null) : null

  // 패널을 열면 입력창으로, 닫으면 런처로 포커스를 돌려준다
  useEffect(() => {
    if (open) composerRef.current?.focus()
    else if (wasOpenRef.current) launcherRef.current?.focus()
    wasOpenRef.current = open
  }, [open])

  // 화면이 바뀌면 맨 위부터 읽도록 스크롤을 초기화한다
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 })
  }, [current?.key])

  const closeCitation = useCallback(() => {
    setCitationId(null)
    const trigger = citationTriggerRef.current
    citationTriggerRef.current = null
    // 근거 패널을 닫으면 초점을 원래 [n] 버튼으로 복귀
    requestAnimationFrame(() => (trigger?.isConnected ? trigger.focus() : composerRef.current?.focus()))
  }, [])

  const openCitation = useCallback((id: number, trigger: HTMLElement) => {
    citationTriggerRef.current = trigger
    setMode('expanded')
    setCitationId(id)
  }, [])

  const navigate = useCallback(<A extends unknown[]>(fn: (...args: A) => void) => {
    return (...args: A) => {
      setCitationId(null)
      citationTriggerRef.current = null
      fn(...args)
    }
  }, [])

  const ask = navigate(chat.ask)
  const select = navigate((option: ClarifyOption) => chat.select(option))
  const back = navigate(chat.back)

  const collapse = () => {
    setCitationId(null)
    setMode('compact')
  }

  const close = () => {
    setOpen(false)
    setMode('compact')
    setCitationId(null)
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key !== 'Escape' || helpOpen) return
    e.stopPropagation()
    if (activeCitation) closeCitation()
    else if (mode === 'expanded') collapse()
    else close()
  }

  const busy = current?.status === 'loading'
  const backLabel = previous?.response?.short_title ?? previous?.response?.title ?? '전체 업무 보기'
  const showActionBar = response?.type === 'answer' && !!response.summary
  const size = sizes[mode]
  const panelStyle = size ? ({ '--panel-w': `${size.w}px`, '--panel-h': `${size.h}px` } as CSSProperties) : undefined

  if (!open) {
    return (
      <button
        ref={launcherRef}
        type="button"
        className={styles.launcher}
        onClick={() => setOpen(true)}
        aria-label="YGPA AI 업무도우미 열기"
        title="AI 업무도우미"
      >
        <Mascot size={46} />
      </button>
    )
  }

  return (
    <section
      ref={panelRef}
      className={`${styles.panel} ${mode === 'expanded' ? styles.expanded : ''}`}
      style={panelStyle}
      role="dialog"
      aria-modal="false"
      aria-labelledby="ygpa-chat-title"
      onKeyDown={handleKeyDown}
    >
      <ResizeHandles
        panelRef={panelRef}
        centered={mode === 'expanded'}
        gap={WIDGET_GAP}
        {...RESIZE_LIMITS[mode]}
        onCommit={(next) => setSizes((prev) => ({ ...prev, [mode]: next }))}
        onReset={() => setSizes((prev) => ({ ...prev, [mode]: null }))}
      />
      <header className={styles.header}>
        <h2 id="ygpa-chat-title" className={styles.title}>
          <span className={styles.brand}>YGPA</span> AI 업무도우미
        </h2>
        <div className={styles.headerActions}>
          {mode === 'compact' ? (
            <button
              type="button"
              className={`${styles.iconButton} ${styles.desktopOnly}`}
              onClick={() => setMode('expanded')}
              aria-label="크게 보기"
            >
              <ArrowUpRight size={20} aria-hidden="true" />
            </button>
          ) : (
            <>
              <button type="button" className={`${styles.textLink} ${styles.desktopOnly}`} onClick={() => setHelpOpen(true)}>
                이용안내
              </button>
              <button type="button" className={`${styles.collapseButton} ${styles.desktopOnly}`} onClick={collapse}>
                작게 보기
                <ArrowDownLeft size={18} aria-hidden="true" />
              </button>
            </>
          )}
          {/* 확장 화면은 Figma상 닫기 없이 "작게 보기"만 둔다. 모바일은 항상 전체 화면이라 닫기를 노출 */}
          <button
            type="button"
            className={`${styles.iconButton} ${mode === 'expanded' ? styles.mobileOnly : ''}`}
            onClick={close}
            aria-label="업무도우미 닫기"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className={styles.body}>
        <div className={styles.main}>
          <div className={styles.scroll} ref={scrollRef}>
            <div className={`${styles.content} ${activeCitation ? styles.contentFull : ''}`}>
              {current ? (
                <ScreenView
                  key={current.key}
                  screen={current}
                  backLabel={backLabel}
                  activeCitationId={activeCitation?.id ?? null}
                  onBack={back}
                  onSelect={select}
                  onRetry={chat.retry}
                  onOpenCitation={openCitation}
                  onRewrite={() => composerRef.current?.focus()}
                />
              ) : (
                <WelcomeView onAsk={ask} />
              )}
            </div>
          </div>

          {showActionBar && response.type === 'answer' && (
            <ActionBar
              response={response}
              onOpenReferences={(trigger) => openCitation(response.citations[0].id, trigger)}
            />
          )}

          <footer className={styles.footer}>
            <Composer busy={busy} onSubmit={ask} inputRef={composerRef} />
            <div className={styles.footerRow}>
              <p className={styles.privacy}>개인정보는 입력하지 마세요.</p>
              <button type="button" className={styles.textLink} onClick={() => setHelpOpen(true)}>
                이용안내
              </button>
            </div>
          </footer>
        </div>

        {activeCitation && (
          <SourcePanel
            citation={activeCitation}
            citations={citations}
            onSelect={setCitationId}
            onClose={closeCitation}
          />
        )}
      </div>

      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      <HelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </section>
  )
}
