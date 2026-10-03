import { describe, expect, it } from 'vitest'
import { createSseParser } from './sse'

describe('createSseParser', () => {
  it('조각나서 도착한 이벤트를 완성된 뒤에만 돌려준다', () => {
    const parser = createSseParser()
    expect(parser.push('event: token\ndata: {"text":"안')).toEqual([])
    expect(parser.push('녕"}\n\nevent: done\ndata: {"message_id":1}\n\n')).toEqual([
      { event: 'token', data: '{"text":"안녕"}' },
      { event: 'done', data: '{"message_id":1}' },
    ])
  })

  it('CRLF 줄바꿈과 주석(ping)을 처리한다', () => {
    const parser = createSseParser()
    expect(parser.push(': ping\r\n\r\nevent: sources\r\ndata: []\r\n\r\n')).toEqual([{ event: 'sources', data: '[]' }])
  })

  it('여러 줄 data를 줄바꿈으로 잇고, 끝에 남은 블록은 flush로 받는다', () => {
    const parser = createSseParser()
    expect(parser.push('event: error\ndata: {"code":"x",\ndata: "message":"y"}')).toEqual([])
    expect(parser.flush()).toEqual([{ event: 'error', data: '{"code":"x",\n"message":"y"}' }])
  })

  it('event 필드가 없으면 message로 본다', () => {
    const parser = createSseParser()
    expect(parser.push('data: 1\n\n')).toEqual([{ event: 'message', data: '1' }])
  })
})
