/**
 * 백엔드가 스트리밍하는 답변 텍스트를 화면 블록으로 나눈다 (v0.2 제안 D의 서식).
 * - 빈 줄: 문단 구분
 * - "1. " / "1) ": 번호 목록 → "진행 순서"
 * - "- " / "• ": 글머리 목록
 * - **굵게**, [n] 인용 번호
 * 스트리밍 중 덜 도착한 텍스트("**굵", "[1")도 깨지지 않고 일반 글자로 보인다.
 */

export type Inline = { kind: 'text'; text: string } | { kind: 'bold'; text: string } | { kind: 'cite'; n: number }

export type Block =
  | { kind: 'p'; inlines: Inline[] }
  | { kind: 'ol'; items: Inline[][] }
  | { kind: 'ul'; items: Inline[][] }

const ORDERED = /^\s*\d{1,2}[.)]\s+(.*)$/
const BULLET = /^\s*[-•]\s+(.*)$/
const INLINE_TOKEN = /(\*\*[^*\n]+\*\*|\[\d{1,2}\])/g
const CITE = /\[(\d{1,2})\]/g

export function parseInline(text: string): Inline[] {
  const out: Inline[] = []
  for (const part of text.split(INLINE_TOKEN)) {
    if (!part) continue
    const cite = /^\[(\d{1,2})\]$/.exec(part)
    if (cite) out.push({ kind: 'cite', n: Number(cite[1]) })
    else if (part.startsWith('**') && part.endsWith('**') && part.length > 4) out.push({ kind: 'bold', text: part.slice(2, -2) })
    else out.push({ kind: 'text', text: part })
  }
  return out
}

export function parseAnswer(text: string): Block[] {
  const blocks: Block[] = []
  let paragraph: string[] = []

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: 'p', inlines: parseInline(paragraph.join('\n')) })
    paragraph = []
  }
  const pushItem = (kind: 'ol' | 'ul', content: string) => {
    flushParagraph()
    const last = blocks.at(-1)
    if (last && last.kind === kind) last.items.push(parseInline(content))
    else blocks.push({ kind, items: [parseInline(content)] })
  }

  for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
    if (!line.trim()) {
      flushParagraph()
      continue
    }
    const ordered = ORDERED.exec(line)
    const bullet = ordered ? null : BULLET.exec(line)
    if (ordered) pushItem('ol', ordered[1])
    else if (bullet) pushItem('ul', bullet[1])
    else paragraph.push(line.trim())
  }
  flushParagraph()
  return blocks
}

/** 절차형 답변인지: 번호 목록이 2개 항목 이상이면 요약 카드 + 진행 순서로 보여준다 */
export function hasSteps(blocks: Block[]): boolean {
  return blocks.some((b) => b.kind === 'ol' && b.items.length >= 2)
}

/** 인용 번호·굵게 표시를 뺀 순수 문장 */
export function plainText(text: string): string {
  return text.replace(CITE, '').replace(/\*\*/g, '').replace(/\s+([.,!?])/g, '$1').trim()
}

/** 근거 패널의 "이 근거가 뒷받침하는 답변": 답변에서 [n]이 붙은 문장만 모은다 */
export function sentencesCiting(text: string, n: number): string[] {
  const marker = `[${n}]`
  const found: string[] = []
  for (const rawLine of text.split('\n')) {
    const line = rawLine.replace(ORDERED, '$1').replace(BULLET, '$1')
    const sentences = line.match(/[^.!?]+(?:[.!?]+|$)(?:\s*(?:\[\d{1,2}\])+)?/g) ?? []
    for (const sentence of sentences) {
      if (!sentence.includes(marker)) continue
      const clean = plainText(sentence)
      if (clean && !found.includes(clean)) found.push(clean)
    }
  }
  return found
}
