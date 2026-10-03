import { ChevronLeft, ChevronRight, CircleAlert, RotateCw, SearchX, ThumbsDown, ThumbsUp } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'
import { hasSteps, parseAnswer, type Block, type Inline } from '../api/parseAnswer'
import type { Action, ClarifyOption } from '../api/types'
import type { Screen } from './useChat'
import { splitActions } from './actions'
import { ActionLink, CitationChip, ContactCard, Mascot } from './ui'
import styles from './ScreenView.module.css'

const PORT_MIS: Action = { type: 'link', label: 'Port-MIS', url: 'https://portmis.go.kr/' }
const YGPA_HOME: Action = { type: 'link', label: 'YGPA 홈페이지', url: 'https://www.ygpa.or.kr/' }

interface ScreenViewProps {
  screen: Screen
  backLabel: string
  activeCitationId: number | null
  onBack: () => void
  onSelect: (option: ClarifyOption) => void
  onRetry: () => void
  onOpenCitation: (id: number, trigger: HTMLElement) => void
  onRewrite: () => void
  onRate: (rating: 'up' | 'down') => void
}

export function ScreenView(props: ScreenViewProps) {
  const { screen, backLabel, onBack } = props
  const busy = screen.status === 'loading' || screen.status === 'streaming'
  return (
    <article className={styles.screen} aria-busy={busy}>
      <div className={styles.topRow}>
        <button type="button" className={styles.backLink} onClick={onBack}>
          <ChevronLeft size={18} aria-hidden="true" />
          {backLabel}
        </button>
        {screen.selectionLabel && <span className={styles.meta}>선택한 안내 · {screen.selectionLabel}</span>}
      </div>

      <div className={styles.userRow}>
        <p className={styles.userBubble}>
          <span className="sr-only">내 질문: </span>
          {screen.question}
        </p>
      </div>

      {screen.status === 'loading' ? (
        <Loading />
      ) : screen.status === 'error' ? (
        <TechnicalError message={screen.error} onRetry={props.onRetry} />
      ) : (
        <AnswerContent {...props} />
      )}
    </article>
  )
}

// ── 인용·서식 렌더링 ─────────────────────────────────

interface CiteContext {
  count: number
  /** done을 받았으면 더 이상 근거가 오지 않는다 → 짝 없는 번호는 일반 글자 */
  settled: boolean
  activeId: number | null
  onOpen: (id: number, trigger: HTMLElement) => void
}

function Cite({ n, cite }: { n: number; cite: CiteContext }) {
  if (n <= cite.count) return <CitationChip id={n} active={cite.activeId === n} onOpen={cite.onOpen} />
  if (!cite.settled) return <CitationChip id={n} pending onOpen={cite.onOpen} />
  return <>[{n}]</>
}

// 인용 번호 바로 뒤의 문장부호. 번호와 떨어져 혼자 다음 줄로 넘어가지 않게 함께 묶는다
const TRAILING_PUNCT = /^[.,!?)」』]+/

function Inlines({ inlines, cite }: { inlines: Inline[]; cite: CiteContext }) {
  const out: ReactNode[] = []
  let i = 0
  while (i < inlines.length) {
    const node = inlines[i]
    if (node.kind === 'text') {
      out.push(<Fragment key={i}>{node.text}</Fragment>)
      i++
      continue
    }
    if (node.kind === 'bold') {
      out.push(<strong key={i}>{node.text}</strong>)
      i++
      continue
    }
    // 연속된 [1][2]와 뒤따르는 문장부호를 한 덩어리로
    const start = i
    const group: ReactNode[] = []
    while (i < inlines.length) {
      const c = inlines[i]
      if (c.kind !== 'cite') break
      group.push(<Cite key={i} n={c.n} cite={cite} />)
      i++
    }
    let rest = ''
    const next = inlines[i]
    if (next?.kind === 'text') {
      const punct = TRAILING_PUNCT.exec(next.text)?.[0]
      if (punct) {
        group.push(punct)
        rest = next.text.slice(punct.length)
        i++
      }
    }
    out.push(
      <span key={`c${start}`} className={styles.nowrap}>
        {group}
      </span>,
    )
    if (rest) out.push(<Fragment key={`r${start}`}>{rest}</Fragment>)
  }
  return out
}

function BlockView({ block, cite }: { block: Block; cite: CiteContext }) {
  if (block.kind === 'p') {
    return (
      <p className={styles.paragraph}>
        <Inlines inlines={block.inlines} cite={cite} />
      </p>
    )
  }
  const List = block.kind === 'ol' ? 'ol' : 'ul'
  return (
    <List className={block.kind === 'ol' ? styles.numbered : styles.bullets}>
      {block.items.map((item, i) => (
        <li key={i}>
          <Inlines inlines={item} cite={cite} />
        </li>
      ))}
    </List>
  )
}

const citesIn = (block: Block): number[] =>
  (block.kind === 'p' ? [block.inlines] : block.items).flat().flatMap((n) => (n.kind === 'cite' ? [n.n] : []))

// ── 답변 본문 ──────────────────────────────────────

function AnswerContent({ screen, activeCitationId, onSelect, onOpenCitation, onRewrite, onRate }: ScreenViewProps) {
  const blocks = parseAnswer(screen.text)
  const type = screen.done?.answer_type
  const streaming = screen.status === 'streaming'
  const cite: CiteContext = {
    count: screen.sources.length,
    settled: screen.status === 'success',
    activeId: activeCitationId,
    onOpen: onOpenCitation,
  }
  const { links, contacts } = splitActions(screen.done?.actions)
  const caret = streaming && <span className={styles.caret} aria-hidden="true" />

  let body
  if (type === 'unknown') {
    body = (
      <div className={styles.bot}>
        <Mascot size={44} />
        <section className={styles.notice} aria-labelledby={`${screen.key}-notice`}>
          <p className={styles.noticeLabel}>
            <SearchX size={16} aria-hidden="true" />
            확인 가능한 근거 부족
          </p>
          <h3 id={`${screen.key}-notice`} className={styles.answerTitle}>
            확인할 근거가 부족해요
          </h3>
          {blocks.map((b, i) => (
            <BlockView key={i} block={b} cite={cite} />
          ))}
        </section>
        {contacts.length > 0 && (
          <div className={styles.contacts}>
            {contacts.map((a, i) => (
              <ContactCard key={i} action={a} />
            ))}
          </div>
        )}
        <div className={styles.actionRow}>
          {links.map((a, i) => (
            <ActionLink key={i} action={a} />
          ))}
          <button type="button" className={styles.textButton} onClick={onRewrite}>
            질문 구체화하기
          </button>
        </div>
      </div>
    )
  } else if (hasSteps(blocks)) {
    // 절차형 답변 (Figma 05): 첫 문단 → 요약 카드, 첫 번호 목록 → 진행 순서
    const [first, ...rest] = blocks
    const summary = first.kind === 'p' ? first : null
    const afterSummary = summary ? rest : blocks
    const stepsIndex = afterSummary.findIndex((b) => b.kind === 'ol' && b.items.length >= 2)
    const summaryActive = !!summary && citesIn(summary).includes(activeCitationId ?? -1)
    body = (
      <>
        {summary && (
          <section className={`${styles.summaryCard} ${summaryActive ? styles.summaryActive : ''}`}>
            <p className={styles.summaryLabel}>한눈에 보기</p>
            <p className={styles.summaryText}>
              <Inlines inlines={summary.inlines} cite={cite} />
            </p>
          </section>
        )}
        {afterSummary.map((block, i) =>
          i === stepsIndex && block.kind === 'ol' ? (
            <section key={i} className={styles.section}>
              <h4 className={styles.sectionTitle}>진행 순서</h4>
              <ol className={styles.steps}>
                {block.items.map((item, n) => (
                  <li key={n} className={styles.step}>
                    <span className={styles.stepNum} aria-hidden="true">
                      {String(n + 1).padStart(2, '0')}
                    </span>
                    <span>
                      <Inlines inlines={item} cite={cite} />
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          ) : (
            <div key={i} className={styles.section}>
              <BlockView block={block} cite={cite} />
            </div>
          ),
        )}
        {caret}
        {contacts.length > 0 && (
          <div className={styles.contacts}>
            {contacts.map((a, i) => (
              <ContactCard key={i} action={a} />
            ))}
          </div>
        )}
      </>
    )
  } else {
    // 짧은 답변(Figma 03)·조건 확인(Figma 04)·스트리밍 중인 답변
    const [primary, ...secondary] = type === 'answer' ? links : []
    body = (
      <div className={styles.bot}>
        <Mascot size={44} />
        <div className={styles.text}>
          {blocks.map((b, i) => (
            <BlockView key={i} block={b} cite={cite} />
          ))}
          {caret}
        </div>

        {type === 'clarify' && (screen.done?.options?.length ?? 0) > 0 && (
          <ul className={styles.options} aria-label="선택지">
            {screen.done!.options!.map((option) => (
              <li key={option.label}>
                <button type="button" className={styles.optionButton} onClick={() => onSelect(option)}>
                  <span>{option.label}</span>
                  <ChevronRight size={18} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {primary && (
          <div className={styles.inlineAction}>
            <ActionLink action={primary} variant="primary" block />
            {primary.note && <p className={styles.actionNote}>{primary.note}</p>}
          </div>
        )}
        {secondary.length > 0 && (
          <div className={styles.actionRow}>
            {secondary.map((a, i) => (
              <ActionLink key={i} action={a} />
            ))}
          </div>
        )}
        {contacts.length > 0 && (
          <div className={styles.contacts}>
            {contacts.map((a, i) => (
              <ContactCard key={i} action={a} />
            ))}
          </div>
        )}
        {screen.status === 'success' && screen.sources.length > 0 && (
          <button type="button" className={styles.refLink} onClick={(e) => onOpenCitation(1, e.currentTarget)}>
            참고자료 {screen.sources.length}건
          </button>
        )}
      </div>
    )
  }

  return (
    <>
      {body}
      {screen.status === 'success' && type !== 'clarify' && <Feedback value={screen.feedback} onRate={onRate} />}
    </>
  )
}

/** 답변마다 받는 짧은 피드백. 무엇이 부족했는지 개선 근거로 쓴다 */
function Feedback({ value, onRate }: { value?: 'up' | 'down'; onRate: (rating: 'up' | 'down') => void }) {
  if (value) {
    return (
      <p className={styles.feedbackDone} role="status">
        의견을 보냈어요. 고맙습니다.
      </p>
    )
  }
  return (
    <div className={styles.feedback}>
      <span className={styles.feedbackLabel}>답변이 도움이 되었나요?</span>
      <button type="button" className={styles.feedbackButton} onClick={() => onRate('up')}>
        <ThumbsUp size={16} aria-hidden="true" />
        도움돼요
      </button>
      <button type="button" className={styles.feedbackButton} onClick={() => onRate('down')}>
        <ThumbsDown size={16} aria-hidden="true" />
        아쉬워요
      </button>
    </div>
  )
}

/** WF-02 처리 중 — 첫 글자가 오기 전까지. 기술 용어 대신 사용자가 이해할 수 있는 작업 상태 */
function Loading() {
  return (
    <div className={styles.loading} role="status">
      <Mascot size={44} />
      <p className={styles.loadingText}>
        관련 YGPA 안내자료와 규정을 확인하고 있어요
        <span className={styles.dots} aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </p>
    </div>
  )
}

/** WF-07 기술 오류 — 질문은 보관하고, 재시도와 공식 메뉴 fallback을 준다 */
function TechnicalError({ message, onRetry }: { message?: string; onRetry: () => void }) {
  return (
    <div className={styles.error} role="alert">
      <p className={styles.errorTitle}>
        <CircleAlert size={18} aria-hidden="true" />
        답변을 불러오지 못했습니다
      </p>
      <p className={styles.errorText}>입력하신 질문은 그대로 보관했습니다. 잠시 후 다시 시도해 주세요.</p>
      {message && <p className={styles.errorDetail}>{message}</p>}
      <button type="button" className={styles.retry} onClick={onRetry}>
        <RotateCw size={16} aria-hidden="true" />
        다시 시도
      </button>
      <p className={styles.errorText}>업무가 급한 경우 YGPA 공식 메뉴를 이용해 주세요.</p>
      <div className={styles.actionRow}>
        <ActionLink action={PORT_MIS} />
        <ActionLink action={YGPA_HOME} />
      </div>
    </div>
  )
}

interface ActionBarProps {
  links: Action[]
  hasSources: boolean
  onOpenReferences: (trigger: HTMLElement) => void
}

/** 절차형 답변 하단 고정 "다음 단계" 바 (Figma 05) */
export function ActionBar({ links, hasSources, onOpenReferences }: ActionBarProps) {
  if (links.length === 0 && !hasSources) return null
  return (
    <div className={styles.actionBar}>
      <span className={styles.actionBarLabel}>다음 단계</span>
      <div className={styles.actionBarButtons}>
        {links.map((action, i) => (
          <ActionLink key={i} action={action} variant={i === 0 ? 'primary' : 'secondary'} />
        ))}
        {hasSources && (
          <button type="button" className={styles.secondaryButton} onClick={(e) => onOpenReferences(e.currentTarget)}>
            참고자료
          </button>
        )}
      </div>
    </div>
  )
}
