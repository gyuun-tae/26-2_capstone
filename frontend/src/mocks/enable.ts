/**
 * 백엔드가 준비되기 전까지 MSW로 /api 응답을 흉내 낸다.
 * 팀 저장소는 .env를 공유하지 않으므로 기본으로 켜고, VITE_USE_MOCK=false일 때만 끈다.
 * 목업 시작에 실패해도 페이지와 위젯은 떠야 하므로 오류를 삼키고 계속 진행한다.
 * (이 경우 질문하면 위젯의 "답변을 불러오지 못했습니다" 화면이 나온다)
 */
export async function enableMocking() {
  if (import.meta.env.VITE_USE_MOCK === 'false') return
  try {
    const { worker } = await import('./browser')
    await worker.start({
      serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
      onUnhandledFrame: 'bypass',
      quiet: true,
    })
  } catch (err) {
    console.warn('[mock] MSW를 시작하지 못해 실제 API로 요청합니다.', err)
  }
}
