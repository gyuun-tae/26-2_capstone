import { describe, expect, it } from 'vitest'
import { hasSteps, parseAnswer, parseInline, sentencesCiting } from './parseAnswer'

describe('parseInline', () => {
  it('굵게와 인용 번호를 나눈다', () => {
    expect(parseInline('**입항보고** 전 확인[1][2].')).toEqual([
      { kind: 'bold', text: '입항보고' },
      { kind: 'text', text: ' 전 확인' },
      { kind: 'cite', n: 1 },
      { kind: 'cite', n: 2 },
      { kind: 'text', text: '.' },
    ])
  })

  it('스트리밍 중 덜 도착한 표시는 일반 글자로 둔다', () => {
    expect(parseInline('확인 **굵')).toEqual([{ kind: 'text', text: '확인 **굵' }])
    expect(parseInline('확인[1')).toEqual([{ kind: 'text', text: '확인[1' }])
  })
})

describe('parseAnswer', () => {
  const answer = '외항선은 사용자 등록을 먼저 확인합니다[1].\n\n1. 사용자 등록 여부 확인[1]\n2. 선박 제원 등록 여부 확인[1]\n\n- 조건에 따라 달라질 수 있어요.'

  it('요약 문단, 번호 목록, 글머리 목록으로 나눈다', () => {
    const blocks = parseAnswer(answer)
    expect(blocks.map((b) => b.kind)).toEqual(['p', 'ol', 'ul'])
    expect(blocks[1].kind === 'ol' && blocks[1].items.length).toBe(2)
    expect(hasSteps(blocks)).toBe(true)
  })

  it('번호 목록이 없으면 절차형이 아니다', () => {
    expect(hasSteps(parseAnswer('견학은 홈페이지에서 신청할 수 있어요[1].'))).toBe(false)
  })

  it('줄바꿈만 있는 문단은 한 문단으로 유지한다', () => {
    const blocks = parseAnswer('첫 줄\n둘째 줄')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].kind === 'p' && blocks[0].inlines).toEqual([{ kind: 'text', text: '첫 줄\n둘째 줄' }])
  })
})

describe('sentencesCiting', () => {
  it('해당 번호가 붙은 문장만 표시 없이 모은다', () => {
    const text = '등록을 먼저 확인합니다[1]. 서식은 따로 있어요[2].\n1. 사용자 등록 여부 확인[1]'
    expect(sentencesCiting(text, 1)).toEqual(['등록을 먼저 확인합니다.', '사용자 등록 여부 확인'])
    expect(sentencesCiting(text, 2)).toEqual(['서식은 따로 있어요.'])
    expect(sentencesCiting(text, 3)).toEqual([])
  })
})
