import { describe, expect, it } from 'vitest'
import type { Source } from '../api/types'
import { dateLabel } from './dateLabel'

const base: Source = {
  doc_id: 'LAW-001',
  chunk_id: 'c1',
  title: '항만법',
  source_url: 'https://www.law.go.kr/법령/항만법/제41조',
  locator: '제41조(항만시설의 사용)',
  published_at: '2025-10-24',
  updated_at: null,
  date_status: 'official_api_current',
  fetched_at: '2026-10-03T06:13:35+00:00',
  snippet: '항만시설을 사용하려는 자는',
}

describe('dateLabel', () => {
  it('법령·고시는 시행일을 앞에, 공포일을 괄호로 보여준다', () => {
    expect(dateLabel({ ...base, effective_at: '2026-02-27' })).toBe('2026.02.27 시행 (2025.10.24 공포)')
  })

  it('시행일이 없으면 공포일만', () => {
    expect(dateLabel(base)).toBe('2025.10.24 공포')
  })

  it('기존 상태 값은 그대로', () => {
    expect(dateLabel({ ...base, date_status: 'not_displayed' })).toBe('원문 미표기')
    expect(dateLabel({ ...base, date_status: 'unverified_attachment', published_at: null })).toBe('첨부 날짜 미확인')
  })
})
