import { useCallback, useEffect, useReducer, useRef } from 'react'
import { sendFeedback, streamChat } from '../api/client'
import type { ChatMessage, ClarifyOption, DoneEvent, Source } from '../api/types'

/**
 * Figma 흐름은 채팅 로그가 아니라 "한 화면에 질문 하나"를 쌓는 구조다.
 * 웰컴(빈 스택) → 입항 질문(clarify) → 외항선 선택(answer) 처럼 화면을 push하고,
 * "‹ 이전 안내" / "‹ 전체 업무 보기" 링크로 pop 한다.
 * 백엔드에는 지금 쌓여 있는 화면들의 대화를 messages[]로 보낸다(뒤로 간 화면은 빠진다).
 */
export interface Screen {
  key: string
  /** 말풍선에 보이는 질문. 선택지를 고른 화면은 원래 질문을 그대로 보여준다 */
  question: string
  /** 조건 확인에서 고른 선택지. "선택한 안내 · 외항선" 메타에 쓴다 */
  selectionLabel?: string
  /** 실제로 보낸 user 메시지 (선택지 화면이면 선택지 문구) */
  userMessage: string
  /** 이번 요청에 보낸 대화 전체 */
  messages: ChatMessage[]
  /** loading: 첫 글자 전, streaming: 답변 도착 중, success: done 수신 */
  status: 'loading' | 'streaming' | 'success' | 'error'
  text: string
  sources: Source[]
  done?: DoneEvent
  error?: string
  feedback?: 'up' | 'down'
}

type State = { stack: Screen[] }

type Action =
  | { type: 'push'; screen: Screen }
  | { type: 'token'; key: string; text: string }
  | { type: 'sources'; key: string; sources: Source[] }
  | { type: 'done'; key: string; done: DoneEvent }
  | { type: 'fail'; key: string; error: string }
  | { type: 'retry'; key: string }
  | { type: 'feedback'; key: string; rating?: 'up' | 'down' }
  | { type: 'back' }
  | { type: 'reset' }

function patch(state: State, key: string, next: (s: Screen) => Partial<Screen>): State {
  return { stack: state.stack.map((s) => (s.key === key ? { ...s, ...next(s) } : s)) }
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'push':
      return { stack: [...state.stack, action.screen] }
    case 'token':
      return patch(state, action.key, (s) => ({ status: 'streaming', text: s.text + action.text }))
    case 'sources':
      return patch(state, action.key, () => ({ sources: action.sources }))
    case 'done':
      return patch(state, action.key, () => ({ status: 'success', done: action.done }))
    case 'fail':
      return patch(state, action.key, () => ({ status: 'error', error: action.error }))
    case 'retry':
      return patch(state, action.key, () => ({ status: 'loading', text: '', sources: [], done: undefined, error: undefined }))
    case 'feedback':
      return patch(state, action.key, () => ({ feedback: action.rating }))
    case 'back':
      return { stack: state.stack.slice(0, -1) }
    case 'reset':
      return { stack: [] }
  }
}

// 백엔드 제한: 최근 20개, 한 메시지 4000자
const MAX_MESSAGES = 20
const MAX_CONTENT = 4000

/** 스택에 남아 있는, 답변까지 받은 화면들의 대화 */
function historyOf(stack: Screen[]): ChatMessage[] {
  return stack.flatMap((s): ChatMessage[] =>
    s.status === 'success' && s.text.trim()
      ? [
          { role: 'user', content: s.userMessage },
          { role: 'assistant', content: s.text.trim().slice(0, MAX_CONTENT) },
        ]
      : [],
  )
}

function withQuestion(stack: Screen[], content: string): ChatMessage[] {
  return [...historyOf(stack), { role: 'user' as const, content }].slice(-MAX_MESSAGES)
}

let keySeq = 0
const nextKey = () => `screen_${++keySeq}`

export interface ChatResult {
  done: DoneEvent
  text: string
}

interface UseChatOptions {
  onResponse?: (result: ChatResult) => void
}

export function useChat({ onResponse }: UseChatOptions = {}) {
  const [state, dispatch] = useReducer(reducer, { stack: [] })
  const stateRef = useRef(state)
  const controllerRef = useRef<AbortController | null>(null)
  const onResponseRef = useRef(onResponse)

  useEffect(() => {
    stateRef.current = state
    onResponseRef.current = onResponse
  })

  const abortInFlight = () => {
    controllerRef.current?.abort()
    controllerRef.current = null
  }

  const run = useCallback((screen: Screen) => {
    abortInFlight()
    const controller = new AbortController()
    controllerRef.current = controller
    let text = ''
    streamChat(
      { messages: screen.messages },
      {
        signal: controller.signal,
        onToken: (chunk) => {
          text += chunk
          dispatch({ type: 'token', key: screen.key, text: chunk })
        },
        onSources: (sources) => dispatch({ type: 'sources', key: screen.key, sources }),
      },
    )
      .then((done) => {
        dispatch({ type: 'done', key: screen.key, done })
        onResponseRef.current?.({ done, text })
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        dispatch({ type: 'fail', key: screen.key, error: err instanceof Error ? err.message : String(err) })
      })
      .finally(() => {
        if (controllerRef.current === controller) controllerRef.current = null
      })
  }, [])

  const push = useCallback(
    (screen: Omit<Screen, 'key' | 'status' | 'text' | 'sources'>) => {
      const full: Screen = { ...screen, key: nextKey(), status: 'loading', text: '', sources: [] }
      dispatch({ type: 'push', screen: full })
      run(full)
    },
    [run],
  )

  const ask = useCallback(
    (input: string) => {
      const content = input.trim()
      if (!content) return
      push({ question: content, userMessage: content, messages: withQuestion(stateRef.current.stack, content) })
    },
    [push],
  )

  const select = useCallback(
    (option: ClarifyOption) => {
      const { stack } = stateRef.current
      const current = stack.at(-1)
      if (!current || current.done?.answer_type !== 'clarify') return
      push({
        question: current.question,
        selectionLabel: option.label,
        userMessage: option.label,
        messages: withQuestion(stack, option.label),
      })
    },
    [push],
  )

  const retry = useCallback(() => {
    const current = stateRef.current.stack.at(-1)
    if (!current || current.status !== 'error') return
    dispatch({ type: 'retry', key: current.key })
    run({ ...current, text: '', sources: [] })
  }, [run])

  const rate = useCallback((rating: 'up' | 'down') => {
    const current = stateRef.current.stack.at(-1)
    if (!current?.done || current.feedback) return
    dispatch({ type: 'feedback', key: current.key, rating })
    sendFeedback(current.done.message_id, { rating }).catch(() => {
      // 전송에 실패하면 다시 누를 수 있게 되돌린다
      dispatch({ type: 'feedback', key: current.key, rating: undefined })
    })
  }, [])

  const back = useCallback(() => {
    abortInFlight()
    dispatch({ type: 'back' })
  }, [])

  const reset = useCallback(() => {
    abortInFlight()
    dispatch({ type: 'reset' })
  }, [])

  useEffect(() => abortInFlight, [])

  const current = state.stack.at(-1) ?? null
  const previous = state.stack.at(-2) ?? null

  return { stack: state.stack, current, previous, ask, select, retry, rate, back, reset }
}

export type ChatController = ReturnType<typeof useChat>
