import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../styles/widget-base.css'
import { ChatWidget } from './ChatWidget'

const HOST_ID = 'ygpa-ai-widget'

// 개발 서버가 <head>에 넣는 <style data-vite-dev-id> 중 위젯 것만 골라낸다
const WIDGET_STYLE_ID = /\/src\/(widget\/|styles\/widget-base\.css)/

/**
 * 위젯 CSS를 Shadow DOM 안으로 가져온다.
 * - 개발: Vite가 head에 넣은 style 요소를 shadow root로 "이동"한다. 요소 자체를 옮기므로
 *   HMR이 같은 요소의 textContent를 갱신해도 그대로 반영된다.
 * - 빌드: 번들된 CSS <link>를 shadow root에 복제한다.
 */
function adoptStyles(shadow: ShadowRoot) {
  if (import.meta.env.DEV) {
    const move = (node: Node) => {
      if (node instanceof HTMLStyleElement && WIDGET_STYLE_ID.test(node.dataset.viteDevId ?? '')) {
        shadow.appendChild(node)
      }
    }
    document.head.querySelectorAll('style[data-vite-dev-id]').forEach(move)
    new MutationObserver((records) => {
      for (const record of records) record.addedNodes.forEach(move)
    }).observe(document.head, { childList: true })
    return
  }

  const assetPrefix = new URL(`${import.meta.env.BASE_URL}assets/`, location.href).href
  document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]').forEach((link) => {
    if (link.href.startsWith(assetPrefix)) shadow.appendChild(link.cloneNode())
  })
}

/**
 * 실제로 보이는 영역(visual viewport)을 CSS 변수로 넘긴다.
 * 호스트 페이지가 가로로 넘치면 position: fixed의 기준(layout viewport)이 화면보다 커져
 * 런처가 화면 밖에 놓이고, 모바일 키보드가 올라오면 입력창이 가려진다. 이를 보정한다.
 */
function trackVisualViewport(el: HTMLElement) {
  const vv = window.visualViewport
  if (!vv) return
  const update = () => {
    el.style.setProperty('--vv-left', `${vv.offsetLeft}px`)
    el.style.setProperty('--vv-top', `${vv.offsetTop}px`)
    el.style.setProperty('--vv-width', `${vv.width}px`)
    el.style.setProperty('--vv-height', `${vv.height}px`)
    el.style.setProperty('--vv-right-gap', `${Math.max(0, window.innerWidth - vv.offsetLeft - vv.width)}px`)
    el.style.setProperty('--vv-bottom-gap', `${Math.max(0, window.innerHeight - vv.offsetTop - vv.height)}px`)
  }
  update()
  vv.addEventListener('resize', update)
  vv.addEventListener('scroll', update)
}

/**
 * 어떤 홈페이지에든 위젯을 붙인다. 호스트 페이지 CSS와 서로 간섭하지 않도록
 * Shadow DOM 안에 렌더링한다.
 */
export function mountWidget() {
  if (document.getElementById(HOST_ID)) return

  const host = document.createElement('div')
  host.id = HOST_ID
  document.body.appendChild(host)

  const shadow = host.attachShadow({ mode: 'open' })
  adoptStyles(shadow)

  const container = document.createElement('div')
  container.className = 'ygpa-widget-root'
  shadow.appendChild(container)
  trackVisualViewport(container)

  createRoot(container).render(
    <StrictMode>
      <ChatWidget />
    </StrictMode>,
  )
}
