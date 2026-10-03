import { Info } from 'lucide-react'
import styles from './CapturePage.module.css'

const BASE = import.meta.env.BASE_URL

/**
 * 공개 데모용 호스트 페이지. YGPA 홈페이지를 복제하지 않고 캡처 이미지만 배경으로 깔아
 * "실제 홈페이지에 붙은 모습"을 보여준다 (Figma 01~07과 같은 방식).
 * 브라우저 틀과 안내 문구로 목업임을 드러내, 실제 사이트로 오인되지 않게 한다.
 */
export function CapturePage() {
  return (
    <div className={styles.page}>
      <div className={styles.chrome}>
        <span className={styles.dots} aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <p className={styles.notice}>
          <Info size={14} aria-hidden="true" />
          시연용 화면 캡처 · 실제 YGPA 홈페이지가 아닙니다
        </p>
      </div>
      <picture className={styles.shot}>
        <source media="(max-width: 640px)" srcSet={`${BASE}assets/ygpa-home-capture-mobile.webp`} />
        <img
          src={`${BASE}assets/ygpa-home-capture.webp`}
          alt="여수광양항만공사 홈페이지 메인 화면 캡처 (시연용 배경)"
          width={2400}
          height={1350}
        />
      </picture>
    </div>
  )
}
