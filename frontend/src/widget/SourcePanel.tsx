import { ArrowUpRight, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { sentencesCiting } from '../api/parseAnswer'
import type { Source } from '../api/types'
import styles from './SourcePanel.module.css'

const formatDate = (iso: string) => iso.slice(0, 10).replaceAll('-', '.')

/** 원문 날짜 표시. 날짜가 없으면 수집일로 채우지 않고 "원문 미표기"로 둔다 (팀 규격) */
function dateLabel(source: Source): string {
  const published = source.published_at && formatDate(source.published_at)
  const updated = source.updated_at && formatDate(source.updated_at)
  switch (source.date_status) {
    case 'not_displayed':
      return '원문 미표기'
    case 'page_updated':
      return updated ? `${updated} (페이지 수정일)` : '원문 미표기'
    case 'conflicting':
      return `확인 필요 · 원문 날짜가 서로 다름${published ? ` (${published})` : ''}`
    case 'unverified_attachment':
      return published ? `${published} (첨부 날짜 미확인)` : '첨부 날짜 미확인'
    default:
      return updated ?? published ?? '원문 미표기'
  }
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

interface SourcePanelProps {
  /** 1부터 시작하는 인용 번호 */
  index: number
  sources: Source[]
  /** 답변 전체 텍스트. [n]이 붙은 문장을 "뒷받침하는 답변"으로 보여준다 */
  answerText: string
  onSelect: (index: number) => void
  onClose: () => void
}

/** WF-05 근거 확인 패널 (Figma 06_Expanded_References) */
export function SourcePanel({ index, sources, answerText, onSelect, onClose }: SourcePanelProps) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const source = sources[index - 1]
  const supports = sentencesCiting(answerText, index)

  useEffect(() => {
    headingRef.current?.focus()
  }, [index])

  if (!source) return null

  return (
    <aside className={styles.panel} aria-labelledby="ygpa-source-title">
      <header className={styles.header}>
        <h3 id="ygpa-source-title" className={styles.heading} tabIndex={-1} ref={headingRef}>
          답변에 참고한 자료 [{index}]
        </h3>
        <button type="button" className={styles.close} onClick={onClose} aria-label="참고자료 닫기">
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      {sources.length > 1 && (
        <nav className={styles.tabs} aria-label="참고자료 목록">
          {sources.map((s, i) => (
            <button
              key={s.chunk_id}
              type="button"
              className={styles.tab}
              aria-current={i + 1 === index ? 'true' : undefined}
              onClick={() => onSelect(i + 1)}
            >
              [{i + 1}]
            </button>
          ))}
        </nav>
      )}

      <div className={styles.body}>
        <p className={styles.kicker}>공식 자료 · [{index}]</p>
        <h4 className={styles.title}>{source.title}</h4>
        <p className={styles.path}>{hostOf(source.source_url)}</p>

        <dl className={styles.metaTable}>
          <div className={styles.metaRow}>
            <dt>관련 항목</dt>
            <dd>{source.locator || '원문 위치 미표기'}</dd>
          </div>
          <div className={styles.metaRow}>
            <dt>원문 날짜</dt>
            <dd>{dateLabel(source)}</dd>
          </div>
          <div className={styles.metaRow}>
            <dt>문서 ID</dt>
            <dd className={styles.mono}>{source.doc_id}</dd>
          </div>
        </dl>

        <section className={styles.excerpt} aria-labelledby="ygpa-excerpt-title">
          <h5 id="ygpa-excerpt-title" className={styles.excerptHeading}>
            원문 발췌
          </h5>
          <p className={styles.excerptText}>{source.snippet}</p>
        </section>

        {supports.length > 0 && (
          <>
            <h5 className={styles.supportsTitle}>이 근거가 뒷받침하는 답변</h5>
            <ul className={styles.supports}>
              {supports.map((sentence) => (
                <li key={sentence}>{sentence}</li>
              ))}
            </ul>
          </>
        )}
      </div>

      <footer className={styles.footer}>
        <a className={styles.openButton} href={source.source_url} target="_blank" rel="noopener noreferrer">
          원문 보기
          <ArrowUpRight size={18} aria-hidden="true" />
          <span className="sr-only">(새 탭)</span>
        </a>
        <p className={styles.footnote}>
          {source.fetched_at ? `자료 확인일 ${formatDate(source.fetched_at)} · ` : ''}새 탭 열기
        </p>
      </footer>
    </aside>
  )
}
