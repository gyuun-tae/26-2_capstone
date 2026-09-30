import { ArrowUpRight, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { Citation, SourceType } from '../api/types'
import styles from './SourcePanel.module.css'

const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  web: '공식 웹자료',
  pdf: '공식 문서(PDF)',
  regulation: '법령·규정',
  notice: '공지·공고',
}

function formatDate(iso: string) {
  return iso.replaceAll('-', '.')
}

interface SourcePanelProps {
  citation: Citation
  citations: Citation[]
  onSelect: (id: number) => void
  onClose: () => void
}

/** WF-05 근거 확인 패널 (Figma 06_Expanded_References) */
export function SourcePanel({ citation, citations, onSelect, onClose }: SourcePanelProps) {
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [citation.id])

  const locationLabel = citation.page != null ? `${citation.section ?? ''} · p.${citation.page}` : citation.section

  return (
    <aside className={styles.panel} aria-labelledby="ygpa-source-title">
      <header className={styles.header}>
        <h3 id="ygpa-source-title" className={styles.heading} tabIndex={-1} ref={headingRef}>
          답변에 참고한 자료 [{citation.id}]
        </h3>
        <button type="button" className={styles.close} onClick={onClose} aria-label="참고자료 닫기">
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      {citations.length > 1 && (
        <nav className={styles.tabs} aria-label="참고자료 목록">
          {citations.map((c) => (
            <button
              key={c.id}
              type="button"
              className={styles.tab}
              aria-current={c.id === citation.id ? 'true' : undefined}
              onClick={() => onSelect(c.id)}
            >
              [{c.id}]
            </button>
          ))}
        </nav>
      )}

      <div className={styles.body}>
        <p className={styles.kicker}>
          {SOURCE_TYPE_LABEL[citation.source_type]} · [{citation.id}]
        </p>
        <h4 className={styles.title}>{citation.title}</h4>
        {citation.path && <p className={styles.path}>{citation.path}</p>}

        <dl className={styles.metaTable}>
          <div className={styles.metaRow}>
            <dt>출처</dt>
            <dd>{citation.publisher}</dd>
          </div>
          {locationLabel && (
            <div className={styles.metaRow}>
              <dt>관련 항목</dt>
              <dd>{locationLabel}</dd>
            </div>
          )}
          <div className={styles.metaRow}>
            <dt>원문 수정일</dt>
            <dd>{citation.last_modified ? formatDate(citation.last_modified) : '원문 미표기'}</dd>
          </div>
        </dl>

        <section className={styles.excerpt} aria-labelledby="ygpa-excerpt-title">
          <h5 id="ygpa-excerpt-title" className={styles.excerptHeading}>
            {citation.excerpt.heading ?? '원문 발췌'}
          </h5>
          {citation.excerpt.quotes.map((quote) => (
            <blockquote key={quote} className={styles.quote}>
              “{quote}”
            </blockquote>
          ))}
          {citation.excerpt.note && <p className={styles.excerptNote}>{citation.excerpt.note}</p>}
        </section>

        <h5 className={styles.supportsTitle}>이 근거가 뒷받침하는 답변</h5>
        <p className={styles.supports}>
          [{citation.id}] {citation.supports}
        </p>
      </div>

      <footer className={styles.footer}>
        <a className={styles.openButton} href={citation.url} target="_blank" rel="noopener noreferrer">
          원문 보기
          <ArrowUpRight size={18} aria-hidden="true" />
          <span className="sr-only">(새 탭)</span>
        </a>
        <p className={styles.footnote}>
          {citation.source_type === 'web' ? '웹자료' : '문서'} 확인일 {formatDate(citation.retrieved_at)} · 새 탭 열기
        </p>
      </footer>
    </aside>
  )
}
