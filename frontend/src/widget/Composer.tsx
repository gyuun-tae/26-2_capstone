import { ArrowUp } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent, type Ref } from 'react'
import styles from './Composer.module.css'

interface ComposerProps {
  busy: boolean
  onSubmit: (text: string) => void
  inputRef?: Ref<HTMLTextAreaElement>
}

export function Composer({ busy, onSubmit, inputRef }: ComposerProps) {
  const [value, setValue] = useState('')
  const canSend = value.trim().length > 0 && !busy

  const submit = () => {
    if (!canSend) return
    onSubmit(value)
    setValue('')
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    submit()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중 Enter는 글자 확정용이므로 전송하지 않는다
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form className={styles.composer} onSubmit={handleSubmit}>
      <label htmlFor="ygpa-composer" className="sr-only">
        질문 입력
      </label>
      <textarea
        id="ygpa-composer"
        ref={inputRef}
        className={styles.input}
        rows={1}
        placeholder="무엇을 도와드릴까요?"
        value={value}
        maxLength={500}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="submit" className={styles.send} disabled={!canSend} aria-label="질문 보내기">
        <ArrowUp size={20} aria-hidden="true" />
      </button>
    </form>
  )
}
