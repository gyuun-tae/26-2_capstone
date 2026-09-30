import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // GitHub Pages는 /저장소이름/ 아래에서 서비스되므로 배포 워크플로가 BASE_PATH를 넘긴다
  base: process.env.BASE_PATH ?? '/',
  plugins: [react()],
  server: {
    // 기본 5173. 미리보기 도구 등이 PORT를 지정하면 그 포트를 쓴다
    port: Number(process.env.PORT) || 5173,
    // VITE_USE_MOCK=false 일 때 /api 요청을 로컬 FastAPI로 보낸다
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
