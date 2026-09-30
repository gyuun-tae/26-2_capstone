import type { Action } from '../api/types'

/** 링크형 행동(link·download)과 연락처(contact)를 나눈다. url 없는 링크는 버린다 */
export function splitActions(actions: Action[] = []) {
  return {
    links: actions.filter((a) => (a.type === 'link' || a.type === 'download') && a.url),
    contacts: actions.filter((a) => a.type === 'contact' && (a.phone || a.label)),
  }
}
