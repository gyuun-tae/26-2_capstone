import { useEffect, useRef } from 'react'
import { useStrings } from './i18n'
import styles from './HelpDialog.module.css'

interface HelpDialogProps {
  open: boolean
  onClose: () => void
}

/** 이용안내 팝업 (Figma 07_Help). 네이티브 <dialog>로 포커스 트랩·Esc 닫기를 처리한다. */
export function HelpDialog({ open, onClose }: HelpDialogProps) {
  const t = useStrings()
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
          {t.helpTitle}
        </h2>
        <p className={styles.text}>
          {t.helpLines[0]}
          <br />
          {t.helpLines[1]}
        </p>
        <p className={styles.muted}>{t.helpLinks}</p>
        <p className={styles.privacy}>{t.helpPrivacy}</p>
        <p className={styles.muted}>{t.helpDemo}</p>
        <button type="button" className={styles.confirm} onClick={onClose} autoFocus>
          {t.helpOk}
        </button>
      </div>
    </dialog>
  )
}
