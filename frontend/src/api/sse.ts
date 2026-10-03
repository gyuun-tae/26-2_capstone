/**
 * text/event-stream 파서. 브라우저 EventSource는 POST를 못 보내므로
 * fetch 응답 본문을 직접 읽어 이벤트 단위로 자른다.
 */
export interface RawSseEvent {
  event: string
  data: string
}

/** 조각난 청크를 받아 완성된 이벤트만 돌려주는 상태 있는 파서 */
export function createSseParser() {
  let buffer = ''

  const parseBlock = (block: string): RawSseEvent | null => {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (!line || line.startsWith(':')) continue // 빈 줄·주석(ping)
      const colon = line.indexOf(':')
      const field = colon === -1 ? line : line.slice(0, colon)
      let value = colon === -1 ? '' : line.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') event = value
      else if (field === 'data') data.push(value)
    }
    return data.length > 0 ? { event, data: data.join('\n') } : null
  }

  return {
    /** 새로 받은 텍스트를 넣으면 이번에 완성된 이벤트들을 돌려준다 */
    push(chunk: string): RawSseEvent[] {
      buffer += chunk.replace(/\r\n?/g, '\n')
      const events: RawSseEvent[] = []
      let end = buffer.indexOf('\n\n')
      while (end !== -1) {
        const parsed = parseBlock(buffer.slice(0, end))
        if (parsed) events.push(parsed)
        buffer = buffer.slice(end + 2)
        end = buffer.indexOf('\n\n')
      }
      return events
    },
    /** 스트림이 끝났을 때 남은 마지막 블록 */
    flush(): RawSseEvent[] {
      const rest = buffer.trim() ? parseBlock(buffer) : null
      buffer = ''
      return rest ? [rest] : []
    },
  }
}
