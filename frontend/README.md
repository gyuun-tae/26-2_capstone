# YGPA AI 업무도우미 — 웹 위젯 (frontend)

여수광양항만공사(YGPA) 홈페이지에 붙는 RAG 챗봇 프론트엔드. 팀 구조의 "채팅·출처 화면" 담당 영역.

- **데모**: https://dlghskgmll.github.io/ygpa-chatbot-web/ (홈페이지 캡처 배경 + 목업 응답, 개인 저장소에서 한시적으로 배포)
- **작업 이력**: 개인 저장소 [dlghskgmll/ygpa-chatbot-web](https://github.com/dlghskgmll/ygpa-chatbot-web)에서 개발한 내용을 옮겨 왔다.

## 실행

Node.js 22 이상이 필요하다. 저장소 최상위에서 `frontend` 폴더로 이동해 실행한다.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

MSW 목업 응답이 기본으로 켜져 있어 백엔드 없이 동작한다.

### 백엔드와 연결해서 실행

프론트엔드는 `feat/api-server`의 형식(`POST /chat`, `messages[]`, SSE `token` → `sources` → `done`)을 따른다. 자세한 대응은 [docs/api-contract.md](docs/api-contract.md)에 있다.

1. 백엔드를 `localhost:8000`에서 실행한다 (`src/api/README.md`).
2. `.env.example`을 `.env`로 복사하고 `VITE_USE_MOCK=false`로 바꾼다.
3. `npm run dev` — 개발 서버가 `/api/chat`을 백엔드의 `/chat`으로 넘긴다.

배포된 백엔드를 쓰려면 `.env`의 `VITE_API_BASE_URL`에 주소를 넣는다. 백엔드 `CORS_ORIGINS`에 프론트엔드 주소가 있어야 한다.

### 테스트

```bash
npm test          # SSE 파서, 답변 서식 해석 (Vitest)
npm run lint
npm run build
```

MSW를 업그레이드하면 `npx msw init public`으로 `public/mockServiceWorker.js`를 직접 갱신한다. Vitest가 내부에 다른 버전의 MSW를 두고 있어서, `package.json`에 워커 자동 복사 설정을 두면 설치할 때 옛 버전 워커로 덮어써진다.

### 실제 YGPA 홈페이지 위에서 시연 (`/host/`)

브라우저에서 YGPA 메인 페이지를 **"웹페이지, 전체"**로 저장한 뒤 `frontend` 폴더에서 변환한다. `host/`는 실제 기관 페이지 복제본이라 git에 올리지 않는다(`.gitignore`). 로컬 시연 전용이고 공개 배포하지 않는다.

```bash
npm run prepare-host -- ~/Desktop/여수광양항만공사.html
npm run dev        # http://localhost:5173/host/
```

- 이미지·영상은 ygpa.or.kr에서 실시간으로 불러오므로 인터넷이 필요하다. 인터넷이 없으면 캡처 배경 데모 `/`를 쓴다.
- `host/`는 공개 배포하지 않는다. 실제 기관 사이트의 동작하는 복제본이라 피싱·사칭으로 판정될 수 있다. 공개 데모는 캡처 이미지(`public/assets/ygpa-home-capture*.webp`)만 쓴다.
- 네이버 애널리틱스는 제거한다 (로컬 시연이 YGPA 통계에 잡히지 않게).
- 위젯은 Shadow DOM 안에 렌더링되어, 사이트의 전역 CSS(`button{padding:0}`, `html{line-height:1}` 등)와 서로 간섭하지 않는다.

### 목업으로 볼 수 있는 시나리오

| 입력 | 결과 (Figma 프레임) |
|---|---|
| "입항 절차를 알려주세요." | 조건 확인 + 외항선/내항선 선택지 (04) |
| └ 외항선 | 스트리밍 → 요약 카드·진행 순서·확장 화면 (05) → `[1]`·참고자료 누르면 근거 패널 (06) |
| └ 내항선 | 확인 불가 안내 (WF-06) |
| "견학 신청은 어디서 하나요?" | 짧은 답변 + 신청 버튼 (03) |
| "오류 테스트" | 스트리밍 도중 `error` 이벤트 → 다시 시도 (WF-07) |
| 그 밖의 질문 | 확인 불가 안내 |

실제 백엔드 목업은 `테스트:조건`, `테스트:확인불가`, `테스트:오류` 문구로 같은 상태를 흉내 낸다.

## 구조

```
src/
  api/types.ts        백엔드 schemas.py와 같은 형식 (docs/api-contract.md)
  api/client.ts       POST /chat SSE 스트림, 피드백, 기술 오류(ApiError) 구분
  api/sse.ts          text/event-stream 파서
  api/parseAnswer.ts  답변 텍스트 → 요약·진행 순서·인용 번호
  mocks/              같은 SSE 형식의 MSW 목업과 시나리오
  embed.tsx           외부 홈페이지 삽입용 진입점 (host/index.html에서 로드)
  main.tsx            캡처 배경 데모 페이지(/) 진입점
  widget/
    mount.tsx         Shadow DOM 마운트, 위젯 CSS 격리, visual viewport 보정
    ChatWidget.tsx    런처 · 컴팩트(440px) · 확장(1100px) 셸, 포커스 관리
    useChat.ts        화면 스택 + messages[] 대화 기록, 스트리밍 상태, 피드백
    WelcomeView.tsx   업무 카드 · 예시 질문 (02)
    ScreenView.tsx    답변 · 되묻기 · 근거 부족 · 처리 중 · 오류 · 다음 단계 바
    SourcePanel.tsx   근거 패널 (06)
    HelpDialog.tsx    이용안내 (07)
  demo/CapturePage.tsx  홈페이지 캡처 배경 데모 (공개 데모·오프라인 시연용, 복제본 아님)
  styles/tokens.css   디자인 토큰 (:root / :host 공용)
  styles/widget-base.css  Shadow DOM 기본값 (호스트 상속값 초기화)
scripts/prepare-host.mjs  저장한 YGPA 페이지 → host/ 변환
```

## 디자인 기준

- Figma: `YGPA AI 업무도우미 — UIUX Design` (Prototype 페이지 01~07)
- KRDS 자체 상징 기준: 본문 16px 이상, 행간 1.5 이상, 포커스 표시
- 귀동이: `public/assets/guidongi-*.svg`. 매뉴얼상 비율·색상 변경 금지이므로 크기만 조절한다.
- `tokens.css`의 색상은 Figma 렌더링에서 추정한 값이라, Figma 원본 값으로 교체해야 한다.
