import { ArrowUpRight, ChevronRight } from 'lucide-react'
import { EXAMPLE_QUESTIONS, TASKS } from './tasks'
import { Mascot } from './ui'
import styles from './WelcomeView.module.css'

interface WelcomeViewProps {
  onAsk: (question: string) => void
}

/** WF-01 시작 화면 (Figma 02_Homepage_Welcome_Open) */
export function WelcomeView({ onAsk }: WelcomeViewProps) {
  return (
    <div className={styles.welcome}>
      <div className={styles.hero}>
        <Mascot size={52} />
        <div>
          <h3 className={styles.heading}>어떤 업무가 필요하신가요?</h3>
          <p className={styles.sub}>
            업무 카드를 선택하거나
            <br />
            직접 질문해보세요.
          </p>
        </div>
      </div>

      <section aria-labelledby="ygpa-tasks-title">
        <h4 id="ygpa-tasks-title" className={`${styles.sectionTitle} ${styles.accent}`}>
          업무 바로 찾기
        </h4>
        <ul className={styles.grid}>
          {TASKS.map((task) => {
            const Icon = task.icon
            const content = (
              <>
                <span className={styles.taskIcon}>
                  <Icon size={18} strokeWidth={2} aria-hidden="true" />
                </span>
                <span className={styles.taskLabel}>{task.label}</span>
                {task.kind === 'link' && (
                  <>
                    <ArrowUpRight size={18} aria-hidden="true" />
                    <span className="sr-only">(새 탭)</span>
                  </>
                )}
              </>
            )
            return (
              <li key={task.id}>
                {task.kind === 'link' ? (
                  <a className={styles.task} href={task.url} target="_blank" rel="noopener noreferrer">
                    {content}
                  </a>
                ) : (
                  <button type="button" className={styles.task} onClick={() => onAsk(task.question)}>
                    {content}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      </section>

      <section aria-labelledby="ygpa-examples-title">
        <h4 id="ygpa-examples-title" className={styles.sectionTitle}>
          이렇게 질문해보세요
        </h4>
        <ul className={styles.examples}>
          {EXAMPLE_QUESTIONS.map((q) => (
            <li key={q}>
              <button type="button" className={styles.example} onClick={() => onAsk(q)}>
                <span>{q}</span>
                <ChevronRight size={18} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
