import { ArrowUpRight, ChevronRight, Info } from 'lucide-react'
import { useContext } from 'react'
import { LangContext, STRINGS } from './i18n'
import { EXAMPLE_QUESTIONS, TASKS } from './tasks'
import { Mascot } from './ui'
import styles from './WelcomeView.module.css'

interface WelcomeViewProps {
  onAsk: (question: string) => void
}

/** WF-01 시작 화면 (Figma 02_Homepage_Welcome_Open) */
export function WelcomeView({ onAsk }: WelcomeViewProps) {
  const lang = useContext(LangContext)
  const t = STRINGS[lang]
  return (
    <div className={styles.welcome}>
      <div className={styles.hero}>
        <Mascot size={52} />
        <div>
          <h3 className={styles.heading}>{t.welcomeHeading}</h3>
          <p className={styles.sub}>
            {t.welcomeSub[0]}
            <br />
            {t.welcomeSub[1]}
          </p>
        </div>
      </div>

      {/* 답하는 범위를 먼저 밝혀 자료 밖 질문(다른 항만·운임 시세)을 줄인다 */}
      <p className={styles.scope}>
        <Info size={16} aria-hidden="true" />
        <span>{t.scope}</span>
      </p>

      <section aria-labelledby="ygpa-tasks-title">
        <h4 id="ygpa-tasks-title" className={`${styles.sectionTitle} ${styles.accent}`}>
          {t.tasksTitle}
        </h4>
        <ul className={styles.grid}>
          {TASKS.map((task) => {
            const Icon = task.icon
            const content = (
              <>
                <span className={styles.taskIcon}>
                  <Icon size={18} strokeWidth={2} aria-hidden="true" />
                </span>
                <span className={styles.taskLabel}>{task.label[lang]}</span>
                {task.kind === 'link' && (
                  <>
                    <ArrowUpRight size={18} aria-hidden="true" />
                    <span className="sr-only">{t.newTab}</span>
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
                  <button type="button" className={styles.task} onClick={() => onAsk(task.question[lang])}>
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
          {t.examplesTitle}
        </h4>
        <ul className={styles.examples}>
          {EXAMPLE_QUESTIONS[lang].map((q) => (
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
