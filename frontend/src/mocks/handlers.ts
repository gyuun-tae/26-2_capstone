import { delay, http, HttpResponse } from 'msw'
import type { ChatRequest, FeedbackRequest } from '../api/types'
import { chunkText, resolveScenario } from './scenarios'

let messageSeq = 0

/** 팀 백엔드(feat/api-server)와 같은 SSE 순서: token → sources → done, 실패 시 error */
export const handlers = [
  http.post('*/api/chat', async ({ request }) => {
    const reply = resolveScenario((await request.json()) as ChatRequest)
    const messageId = ++messageSeq
    const encoder = new TextEncoder()

    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        const send = (event: string, data: unknown) =>
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`))

        await delay(700) // 검색 시간
        const tokens = chunkText(reply.text)
        for (const [i, text] of tokens.entries()) {
          if (reply.failAfterTokens !== undefined && i === reply.failAfterTokens) {
            send('error', { code: 'generation_failed', message: '답변을 만드는 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.' })
            controller.close()
            return
          }
          send('token', { text })
          await delay(30)
        }
        send('sources', reply.sources)
        send('done', { message_id: messageId, ...reply.done })
        controller.close()
      },
    })

    return new HttpResponse(stream, {
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
    })
  }),

  http.put('*/api/messages/:messageId/feedback', async ({ request, params }) => {
    const body = (await request.json()) as FeedbackRequest
    console.info('[mock] feedback', params.messageId, body)
    return new HttpResponse(null, { status: 204 })
  }),
]
