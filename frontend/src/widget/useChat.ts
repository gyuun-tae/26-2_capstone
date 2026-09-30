import { useCallback, useEffect, useReducer, useRef } from 'react'
import { postChat } from '../api/client'
import type { ChatRequest, ChatResponse, ClarifyOption } from '../api/types'

/**
 * Figma 흐름은 채팅 로그가 아니라 "한 화면에 질문 하나"를 쌓는 구조다.
 * 웰컴(빈 스택) → 입항 개요(clarify) → 외항선 상세(answer) 처럼 화면을 push하고,
 * "‹ 입항 개요" / "‹ 전체 업무 보기" 링크로 pop 한다.
 */
export interface Screen {
  key: string
  request: ChatRequest
  /** 말풍선에 보이는 사용자 질문 */
  question: string
  /** 조건 확인에서 고른 선택지. "선택한 안내 · 외항선" 메타에 쓴다 */
  selectionLabel?: string
  status: 'loading' | 'success' | 'error'
  response?: ChatResponse
  error?: string
}

type State = { stack: Screen[] }

type Action =
  | { type: 'push'; screen: Screen }
  | { type: 'resolve'; key: string; response: ChatResponse }
  | { type: 'fail'; key: string; error: string }
  | { type: 'retry'; key: string }
  | { type: 'back' }
  | { type: 'reset' }

function patch(state: State, key: string, next: Partial<Screen>): State {
  return { stack: state.stack.map((s) => (s.key === key ? { ...s, ...next } : s)) }
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'push':
      return { stack: [...state.stack, action.screen] }
    case 'resolve':
      return patch(state, action.key, { status: 'success', response: action.response, error: undefined })
    case 'fail':
      return patch(state, action.key, { status: 'error', error: action.error })
    case 'retry':
      return patch(state, action.key, { status: 'loading', error: undefined })
    case 'back':
      return { stack: state.stack.slice(0, -1) }
    case 'reset':
      return { stack: [] }
  }
}

let keySeq = 0
const nextKey = () => `screen_${++keySeq}`

interface UseChatOptions {
  onResponse?: (response: ChatResponse) => void
}

export function useChat({ onResponse }: UseChatOptions = {}) {
  const [state, dispatch] = useReducer(reducer, { stack: [] })
  const stateRef = useRef(state)
  const controllerRef = useRef<AbortController | null>(null)
  const sessionIdRef = useRef(crypto.randomUUID())
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
    postChat(screen.request, controller.signal)
      .then((response) => {
        dispatch({ type: 'resolve', key: screen.key, response })
        onResponseRef.current?.(response)
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        dispatch({ type: 'fail', key: screen.key, error: err instanceof Error ? err.message : String(err) })
      })
      .finally(() => {
        if (controllerRef.current === controller) controllerRef.current = null
      })
  }, [])

  const ask = useCallback(
    (text: string) => {
      const message = text.trim()
      if (!message) return
      const screen: Screen = {
        key: nextKey(),
        request: { message, session_id: sessionIdRef.current, locale: 'ko' },
        question: message,
        status: 'loading',
      }
      dispatch({ type: 'push', screen })
      run(screen)
    },
    [run],
  )

  const select = useCallback(
    (option: ClarifyOption) => {
      const current = stateRef.current.stack.at(-1)
      if (!current?.response || current.response.type !== 'clarify') return
      const screen: Screen = {
        key: nextKey(),
        request: {
          message: current.question,
          session_id: sessionIdRef.current,
          locale: 'ko',
          clarification: { response_id: current.response.id, option_id: option.id },
        },
        question: current.question,
        selectionLabel: option.label,
        status: 'loading',
      }
      dispatch({ type: 'push', screen })
      run(screen)
    },
    [run],
  )

  const retry = useCallback(() => {
    const current = stateRef.current.stack.at(-1)
    if (!current || current.status !== 'error') return
    dispatch({ type: 'retry', key: current.key })
    run(current)
  }, [run])

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

  return { stack: state.stack, current, previous, ask, select, retry, back, reset }
}

export type ChatController = ReturnType<typeof useChat>
