import type { Source } from '../api/types'
import { STRINGS, type Strings } from './i18n'

export const formatDate = (iso: string) => iso.slice(0, 10).replaceAll('-', '.')

/** 원문 날짜 표시. 날짜가 없으면 수집일로 채우지 않고 "원문 미표기"로 둔다 (팀 규격) */
export function dateLabel(source: Source, t: Strings = STRINGS.ko): string {
  const d = t.date
  const published = source.published_at ? formatDate(source.published_at) : undefined
  const updated = source.updated_at ? formatDate(source.updated_at) : undefined
  switch (source.date_status) {
    case 'not_displayed':
      return d.notShown
    case 'page_updated':
      return updated ? d.pageUpdated(updated) : d.notShown
    case 'conflicting':
      return d.conflicting(published)
    case 'unverified_attachment':
      return d.attachment(published)
    case 'official_api_current': {
      // 법령·고시: 지금 적용되는 기준인 시행일을 앞에, 공포일은 보조로
      const effective = source.effective_at && formatDate(source.effective_at)
      if (effective) return d.effective(effective, published)
      return published ? d.promulgated(published) : d.notShown
    }
    default:
      return updated ?? published ?? d.notShown
  }
}
