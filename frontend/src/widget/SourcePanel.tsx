import { ArrowUpRight, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { sentencesCiting } from '../api/parseAnswer'
import type { Source } from '../api/types'
import { dateLabel, formatDate } from './dateLabel'
import { useStrings } from './i18n'
import styles from './SourcePanel.module.css'

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
  const t = useStrings()
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
          {t.sourceHeading(index)}
        </h3>
        <button type="button" className={styles.close} onClick={onClose} aria-label={t.sourceClose}>
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      {sources.length > 1 && (
        <nav className={styles.tabs} aria-label={t.sourceTabs}>
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
        <p className={styles.kicker}>{t.sourceKicker(index)}</p>
        <h4 className={styles.title}>{source.title}</h4>
        <p className={styles.path}>{hostOf(source.source_url)}</p>

        <dl className={styles.metaTable}>
          <div className={styles.metaRow}>
            <dt>{t.sourceItem}</dt>
            <dd>{source.locator || t.sourceNoLocator}</dd>
          </div>
          <div className={styles.metaRow}>
            <dt>{t.sourceDate}</dt>
            <dd>{dateLabel(source, t)}</dd>
          </div>
          <div className={styles.metaRow}>
            <dt>{t.sourceDocId}</dt>
            <dd className={styles.mono}>{source.doc_id}</dd>
          </div>
        </dl>

        <section className={styles.excerpt} aria-labelledby="ygpa-excerpt-title">
          <h5 id="ygpa-excerpt-title" className={styles.excerptHeading}>
            {t.sourceExcerpt}
          </h5>
          <p className={styles.excerptText}>{source.snippet}</p>
        </section>

        {supports.length > 0 && (
          <>
            <h5 className={styles.supportsTitle}>{t.sourceSupports}</h5>
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
          {t.sourceOpen}
          <ArrowUpRight size={18} aria-hidden="true" />
          <span className="sr-only">{t.newTab}</span>
        </a>
        <p className={styles.footnote}>
          {source.fetched_at ? t.sourceChecked(formatDate(source.fetched_at)) : ''}{t.sourceNewTab}
        </p>
      </footer>
    </aside>
  )
}
