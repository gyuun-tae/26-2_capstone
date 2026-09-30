import { delay, http, HttpResponse } from 'msw'
import type { ChatRequest, FeedbackRequest } from '../api/types'
import { resolveScenario } from './scenarios'

export const handlers = [
  http.post('*/api/chat', async ({ request }) => {
    const body = (await request.json()) as ChatRequest
    // "관련 자료를 확인하고 있어요" 상태를 볼 수 있도록 실제 RAG 지연을 흉내 낸다
    await delay(900)
    const response = resolveScenario(body)
    if (!response) {
      return HttpResponse.json({ detail: 'mock: internal error' }, { status: 500 })
    }
    return HttpResponse.json(response)
  }),

  http.post('*/api/feedback', async ({ request }) => {
    const body = (await request.json()) as FeedbackRequest
    console.info('[mock] feedback', body)
    return HttpResponse.json({ ok: true })
  }),
]
