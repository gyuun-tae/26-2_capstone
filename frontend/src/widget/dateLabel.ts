import type { Source } from '../api/types'

export const formatDate = (iso: string) => iso.slice(0, 10).replaceAll('-', '.')

/** 원문 날짜 표시. 날짜가 없으면 수집일로 채우지 않고 "원문 미표기"로 둔다 (팀 규격) */
export function dateLabel(source: Source): string {
  const published = source.published_at && formatDate(source.published_at)
  const updated = source.updated_at && formatDate(source.updated_at)
  switch (source.date_status) {
    case 'not_displayed':
      return '원문 미표기'
    case 'page_updated':
      return updated ? `${updated} (페이지 수정일)` : '원문 미표기'
    case 'conflicting':
      return `확인 필요 · 원문 날짜가 서로 다름${published ? ` (${published})` : ''}`
    case 'unverified_attachment':
      return published ? `${published} (첨부 날짜 미확인)` : '첨부 날짜 미확인'
    case 'official_api_current': {
      // 법령·고시: 지금 적용되는 기준인 시행일을 앞에, 공포일은 보조로
      const effective = source.effective_at && formatDate(source.effective_at)
      if (effective) return published ? `${effective} 시행 (${published} 공포)` : `${effective} 시행`
      return published ? `${published} 공포` : '원문 미표기'
    }
    default:
      return updated ?? published ?? '원문 미표기'
  }
}
