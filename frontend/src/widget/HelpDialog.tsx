import { useEffect, useRef } from 'react'
import styles from './HelpDialog.module.css'

interface HelpDialogProps {
  open: boolean
  onClose: () => void
}

/** 이용안내 팝업 (Figma 07_Help). 네이티브 <dialog>로 포커스 트랩·Esc 닫기를 처리한다. */
export function HelpDialog({ open, onClose }: HelpDialogProps) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className={styles.dialog}
      aria-labelledby="ygpa-help-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className={styles.content}>
        <h2 id="ygpa-help-title" className={styles.title}>
          YGPA AI 업무도우미 이용안내
        </h2>
        <p className={styles.text}>
          업무 카드나 예시 질문으로 안내를 확인하세요.
          <br />
          참고자료에서 출처를 확인하고, 원문 보기로 공식 페이지에 이동할 수 있어요.
        </p>
        <p className={styles.muted}>↗ 표시가 있는 버튼은 외부 사이트를 새 탭으로 엽니다. 견학 신청은 YGPA 홈페이지 로그인이 필요합니다.</p>
        <p className={styles.privacy}>주민등록번호, 여권번호 등 업무에 불필요한 개인정보는 입력하지 마세요.</p>
        <p className={styles.muted}>
          현재 화면은 개발 중인 시연 버전입니다. 답변 아래 👍·👎로 의견을 남겨 주시고, 실제 업무 전에는 공식 원문을 확인해 주세요.
        </p>
        <button type="button" className={styles.confirm} onClick={onClose} autoFocus>
          확인
        </button>
      </div>
    </dialog>
  )
}
