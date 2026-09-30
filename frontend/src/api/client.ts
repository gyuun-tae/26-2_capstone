import { createSseParser } from './sse'
import type { ChatRequest, DoneEvent, ErrorEvent, FeedbackRequest, Source } from './types'

// .env에서 빈 문자열이면 기본값 사용. 개발 서버는 /api를 백엔드(localhost:8000)로 프록시한다
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

// 이벤트가 이 시간 동안 하나도 오지 않으면 실패로 본다 (무료 서버가 잠에서 깨는 시간 포함)
const IDLE_TIMEOUT_MS = 75_000

/** 네트워크 실패·HTTP 오류·SSE error 이벤트 등 기술 오류. 근거 부족(answer_type: 'unknown')과 구분한다. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

interface StreamHandlers {
  signal?: AbortSignal
  onToken: (text: string) => void
  onSources: (sources: Source[]) => void
}

/**
 * POST /chat 을 SSE로 받는다. token·sources는 콜백으로 흘려보내고,
 * done을 받으면 그 내용을 돌려준다. error 이벤트나 done 없이 끝난 스트림은 ApiError.
 */
export async function streamChat(req: ChatRequest, { signal, onToken, onSources }: StreamHandlers): Promise<DoneEvent> {
  const idle = new AbortController()
  const abortIdle = () => idle.abort()
  signal?.addEventListener('abort', abortIdle)
  let timer = setTimeout(abortIdle, IDLE_TIMEOUT_MS)
  const resetTimer = () => {
    clearTimeout(timer)
    timer = setTimeout(abortIdle, IDLE_TIMEOUT_MS)
  }

  try {
    let res: Response
    try {
      res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(req),
        signal: idle.signal,
      })
    } catch (err) {
      throw toApiError(err, signal)
    }
    if (!res.ok || !res.body) {
      throw new ApiError(res.status, 'http_error', `요청이 실패했습니다. (HTTP ${res.status})`)
    }

    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
    const parser = createSseParser()
    for (;;) {
      let chunk: ReadableStreamReadResult<string>
      try {
        chunk = await reader.read()
      } catch (err) {
        throw toApiError(err, signal)
      }
      const events = chunk.done ? parser.flush() : parser.push(chunk.value)
      resetTimer()
      for (const ev of events) {
        let data: unknown
        try {
          data = JSON.parse(ev.data)
        } catch {
          throw new ApiError(200, 'bad_event', '응답 형식을 해석하지 못했습니다.')
        }
        if (ev.event === 'token') onToken((data as { text: string }).text)
        else if (ev.event === 'sources') onSources(data as Source[])
        else if (ev.event === 'done') return data as DoneEvent
        else if (ev.event === 'error') {
          const { code, message } = data as ErrorEvent
          throw new ApiError(200, code, message)
        }
      }
      if (chunk.done) throw new ApiError(200, 'stream_ended', '응답이 중간에 끊겼습니다.')
    }
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abortIdle)
  }
}

function toApiError(err: unknown, signal?: AbortSignal): unknown {
  if (err instanceof DOMException && err.name === 'AbortError') {
    // 사용자가 취소한 경우는 그대로 AbortError로 올려 조용히 무시하게 한다
    if (signal?.aborted) return err
    return new ApiError(0, 'timeout', '응답이 너무 오래 걸려 요청을 멈췄습니다.')
  }
  return new ApiError(0, 'network', '서버에 연결하지 못했습니다.')
}

export async function sendFeedback(messageId: number, body: FeedbackRequest) {
  const res = await fetch(`${API_BASE}/messages/${messageId}/feedback`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new ApiError(res.status, 'http_error', `의견을 보내지 못했습니다. (HTTP ${res.status})`)
}
