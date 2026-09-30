import { ChevronLeft, ChevronRight, CircleAlert, RotateCw, SearchX } from 'lucide-react'
import type { Action, AnswerResponse, ChatResponse, ClarifyOption, InsufficientResponse } from '../api/types'
import type { Screen } from './useChat'
import { ActionLink, CitationChip, Mascot } from './ui'
import styles from './ScreenView.module.css'

const PORT_MIS: Action = { id: 'portmis', label: 'Port-MIS', url: 'https://portmis.go.kr/', kind: 'secondary', external: true }
const YGPA_HOME: Action = { id: 'home', label: 'YGPA 홈페이지', url: 'https://www.ygpa.or.kr/', kind: 'secondary', external: true }

interface ScreenViewProps {
  screen: Screen
  backLabel: string
  activeCitationId: number | null
  onBack: () => void
  onSelect: (option: ClarifyOption) => void
  onRetry: () => void
  onOpenCitation: (id: number, trigger: HTMLElement) => void
  onRewrite: () => void
}

export function ScreenView(props: ScreenViewProps) {
  const { screen, backLabel, onBack } = props
  return (
    <article className={styles.screen} aria-busy={screen.status === 'loading'}>
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

      <ScreenBody {...props} />
    </article>
  )
}

function ScreenBody({ screen, onSelect, onRetry, onOpenCitation, activeCitationId, onRewrite }: ScreenViewProps) {
  if (screen.status === 'loading') return <Loading />
  if (screen.status === 'error' || !screen.response) return <TechnicalError message={screen.error} onRetry={onRetry} />

  const response = screen.response
  switch (response.type) {
    case 'clarify':
      return (
        <>
          <BotHeading response={response} />
          <ul className={styles.options}>
            {response.options.map((option) => (
              <li key={option.id} className={styles.optionCard}>
                <h4 className={styles.optionTitle}>{option.title}</h4>
                <p className={styles.optionDesc}>{option.description}</p>
                <button type="button" className={styles.optionCta} onClick={() => onSelect(option)}>
                  {option.cta_label}
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )
    case 'answer':
      return response.summary ? (
        <DetailedAnswer response={response} activeCitationId={activeCitationId} onOpenCitation={onOpenCitation} />
      ) : (
        <SimpleAnswer response={response} onOpenCitation={onOpenCitation} />
      )
    case 'insufficient':
      return <Insufficient response={response} onRewrite={onRewrite} />
  }
}

function BotHeading({ response }: { response: ChatResponse }) {
  return (
    <div className={styles.bot}>
      <Mascot size={44} />
      <h3 className={styles.answerTitle}>{response.title}</h3>
      {response.lead && <p className={styles.lead}>{response.lead}</p>}
    </div>
  )
}

/** WF-02 처리 중 — 기술 용어 대신 사용자가 이해할 수 있는 작업 상태 */
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

/** WF-03 조건 확인 이후의 상세 답변 (Figma 05) */
function DetailedAnswer({
  response,
  activeCitationId,
  onOpenCitation,
}: {
  response: AnswerResponse
  activeCitationId: number | null
  onOpenCitation: (id: number, trigger: HTMLElement) => void
}) {
  const summary = response.summary!
  const summaryActive = summary.citation_ids.some((id) => id === activeCitationId)
  return (
    <>
      <section className={`${styles.summaryCard} ${summaryActive ? styles.summaryActive : ''}`}>
        <div className={styles.summaryHead}>
          <h3 className={styles.summaryTitle}>{summary.title}</h3>
          {summary.citation_ids.map((id) => (
            <CitationChip key={id} id={id} active={id === activeCitationId} onOpen={onOpenCitation} />
          ))}
          {summary.label && <span className={styles.summaryLabel}>{summary.label}</span>}
        </div>
        <p className={styles.summaryText}>{summary.text}</p>
      </section>

      {response.sections.map((section, i) =>
        section.kind === 'steps' ? (
          <section key={i} className={styles.section}>
            <h4 className={styles.sectionTitle}>{section.title}</h4>
            <ol className={styles.steps}>
              {section.items.map((item, n) => (
                <li key={n} className={styles.step}>
                  <span className={styles.stepNum} aria-hidden="true">
                    {String(n + 1).padStart(2, '0')}
                  </span>
                  <span>
                    {item.text}
                    {item.citation_ids?.map((id) => (
                      <CitationChip key={id} id={id} active={id === activeCitationId} onOpen={onOpenCitation} />
                    ))}
                  </span>
                </li>
              ))}
            </ol>
            {section.note && <p className={styles.note}>{section.note}</p>}
          </section>
        ) : (
          <section key={i} className={styles.section}>
            {section.title && <h4 className={styles.sectionTitle}>{section.title}</h4>}
            <p className={styles.lead}>
              {section.text}
              {section.citation_ids?.map((id) => (
                <CitationChip key={id} id={id} active={id === activeCitationId} onOpen={onOpenCitation} />
              ))}
            </p>
          </section>
        ),
      )}
    </>
  )
}

/** 짧은 답변 + 바로 행동 (Figma 03_Compact_Simple) */
function SimpleAnswer({
  response,
  onOpenCitation,
}: {
  response: AnswerResponse
  onOpenCitation: (id: number, trigger: HTMLElement) => void
}) {
  const [primary, ...rest] = response.actions
  const firstCitation = response.citations[0]
  return (
    <>
      <BotHeading response={response} />
      {primary && (
        <div className={styles.inlineAction}>
          <ActionLink action={primary} variant="primary" block />
          {primary.note && <p className={styles.actionNote}>{primary.note}</p>}
        </div>
      )}
      {rest.length > 0 && (
        <div className={styles.actionRow}>
          {rest.map((action) => (
            <ActionLink key={action.id} action={action} variant="secondary" />
          ))}
        </div>
      )}
      {firstCitation && (
        <button
          type="button"
          className={styles.refLink}
          onClick={(e) => onOpenCitation(firstCitation.id, e.currentTarget)}
        >
          참고자료
        </button>
      )}
    </>
  )
}

/** WF-06 근거 부족 — 기술 오류가 아니라 "확인 가능한 근거가 없다"는 정상 응답 */
function Insufficient({ response, onRewrite }: { response: InsufficientResponse; onRewrite: () => void }) {
  return (
    <div className={styles.bot}>
      <Mascot size={44} />
      <section className={styles.notice} aria-labelledby={`${response.id}-title`}>
        <p className={styles.noticeLabel}>
          <SearchX size={16} aria-hidden="true" />
          확인 가능한 근거 부족
        </p>
        <h3 id={`${response.id}-title`} className={styles.answerTitle}>
          {response.title}
        </h3>
        {response.lead && <p className={styles.lead}>{response.lead}</p>}
        {response.searched_scope && <p className={styles.scope}>확인한 범위: {response.searched_scope}</p>}
      </section>
      <div className={styles.actionRow}>
        {response.actions.map((action) => (
          <ActionLink key={action.id} action={action} variant="secondary" />
        ))}
        <button type="button" className={styles.textButton} onClick={onRewrite}>
          질문 구체화하기
        </button>
      </div>
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
        <ActionLink action={PORT_MIS} variant="secondary" />
        <ActionLink action={YGPA_HOME} variant="secondary" />
      </div>
    </div>
  )
}

interface ActionBarProps {
  response: AnswerResponse
  onOpenReferences: (trigger: HTMLElement) => void
}

/** 상세 답변 하단 고정 "다음 단계" 바 (Figma 05) */
export function ActionBar({ response, onOpenReferences }: ActionBarProps) {
  return (
    <div className={styles.actionBar}>
      <span className={styles.actionBarLabel}>다음 단계</span>
      <div className={styles.actionBarButtons}>
        {response.actions.map((action) => (
          <ActionLink key={action.id} action={action} />
        ))}
        {response.citations.length > 0 && (
          <button type="button" className={styles.secondaryButton} onClick={(e) => onOpenReferences(e.currentTarget)}>
            참고자료
          </button>
        )}
      </div>
    </div>
  )
}
