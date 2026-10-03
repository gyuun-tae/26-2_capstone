/**
 * 데모 페이지 진입점 (/). 홈페이지 캡처 이미지 위에 위젯을 띄운다 (GitHub Pages 공개 데모).
 * 실제 홈페이지 복제본 위 시연은 로컬 전용 /host/ (src/embed.tsx) 를 쓴다.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { CapturePage } from './demo/CapturePage'
import { enableMocking } from './mocks/enable'
import { mountWidget } from './widget/mount'
import './styles/global.css'

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <CapturePage />
    </StrictMode>,
  )
  mountWidget()
})
