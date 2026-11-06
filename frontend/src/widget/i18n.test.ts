import { describe, expect, it } from 'vitest'
import { copyText } from '../api/parseAnswer'
import type { Source } from '../api/types'
import { dateLabel } from './dateLabel'
import { STRINGS } from './i18n'
import { EXAMPLE_QUESTIONS, PORT_MIS_URL, TASKS } from './tasks'

const law: Source = {
  doc_id: 'LAW-001',
  chunk_id: 'c1',
  title: '항만법',
  source_url: 'https://www.law.go.kr/',
  locator: '제41조',
  published_at: '2025-10-24',
  updated_at: null,
  date_status: 'official_api_current',
  effective_at: '2026-02-27',
  fetched_at: null,
  snippet: '',
}

const LANGS = ['ko', 'en', 'ja', 'zh'] as const
// 한글 음절 — 영·일·중 화면에 한국어가 섞여 나오면 안 된다 (원문이 한국어임을 밝히는 문구는 외국어로 씀)
const HANGUL = /[가-힣]/

describe('화면 언어 (한·영·일·중)', () => {
  it('네 언어 문구의 항목이 같다', () => {
    const keys = (o: object): string[] =>
      Object.entries(o).flatMap(([k, v]) => (v && typeof v === 'object' && !Array.isArray(v) ? keys(v).map((x) => `${k}.${x}`) : [k]))
    for (const l of LANGS) expect(keys(STRINGS[l]).sort()).toEqual(keys(STRINGS.ko).sort())
  })

  it('외국어 화면 문구에 한글이 섞이지 않는다', () => {
    const texts = (o: object): string[] =>
      Object.values(o).flatMap((v) =>
        typeof v === 'string' ? [v] : typeof v === 'function' ? [String(v(1, '2026.01.01'))] : Array.isArray(v) ? v : texts(v),
      )
    for (const l of ['en', 'ja', 'zh'] as const) {
      expect(texts(STRINGS[l]).filter((s) => HANGUL.test(s))).toEqual([])
      for (const task of TASKS) {
        expect(HANGUL.test(task.label[l])).toBe(false)
        if (task.kind === 'ask') expect(HANGUL.test(task.question[l])).toBe(false)
      }
      expect(EXAMPLE_QUESTIONS[l].some((q) => HANGUL.test(q))).toBe(false)
    }
  })

  it('업무 카드와 예시 질문이 네 언어 모두 있다', () => {
    for (const task of TASKS) {
      for (const l of LANGS) {
        expect(task.label[l]).toBeTruthy()
        if (task.kind === 'ask') expect(task.question[l]).toBeTruthy()
      }
    }
    for (const l of LANGS) expect(EXAMPLE_QUESTIONS[l].length).toBe(EXAMPLE_QUESTIONS.ko.length)
  })

  it('Port-MIS는 새 주소 (옛 portmis.go.kr은 종료)', () => {
    expect(PORT_MIS_URL).toBe('https://new.portmis.go.kr/')
    expect(TASKS.find((t) => t.id === 'portmis')).toMatchObject({ url: PORT_MIS_URL })
  })

  it('원문 날짜·복사 글도 화면 언어로', () => {
    expect(dateLabel(law, STRINGS.en)).toBe('In force 2026.02.27 (promulgated 2025.10.24)')
    expect(dateLabel({ ...law, date_status: 'not_displayed' }, STRINGS.en)).toBe('Not shown in the source')
    expect(copyText('Answer[1].', [{ title: '항만법', source_url: 'https://x' }], STRINGS.en.referencesShort)).toBe(
      'Answer[1].\n\nReferences\n[1] 항만법 https://x',
    )
    expect(STRINGS.en.references(1)).toBe('1 reference')
    expect(STRINGS.en.references(3)).toBe('3 references')
  })
})
