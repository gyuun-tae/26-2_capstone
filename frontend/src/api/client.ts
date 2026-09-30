import type { ChatRequest, ChatResponse, FeedbackRequest } from './types'

// .env에서 빈 문자열이면 기본값 사용
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

/** 네트워크 실패·5xx 등 기술 오류. 근거 부족(type: 'insufficient')과 구분한다. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, '서버에 연결하지 못했습니다.')
  }
  if (!res.ok) {
    throw new ApiError(res.status, `요청이 실패했습니다. (HTTP ${res.status})`)
  }
  return res.json() as Promise<T>
}

export function postChat(req: ChatRequest, signal?: AbortSignal) {
  return postJson<ChatResponse>('/chat', req, signal)
}

export function postFeedback(req: FeedbackRequest) {
  return postJson<{ ok: true }>('/feedback', req)
}
