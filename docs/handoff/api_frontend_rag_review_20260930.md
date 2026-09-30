# API PR·프론트엔드·지식베이스 연결 검토

확인일: 2026-09-30. PR은 병합하지 않았으며 서버 배포·실제 청크 임베딩·색인 등록은 실행하지 않았다. 검토 결과 문서만 main에 반영한다.

## 결론과 검토 기준

Git 충돌은 없고 수정된 API mock은 동작한다. 그러나 프론트엔드와 API는 서로 다른 규격이어서 지금 그대로 연결되지 않는다. 실제 RAG는 저장소 연결 이후의 등록·검색·생성 구현이 남아 있다.

| 대상 | 검토 커밋 | 상태 |
|---|---|---|
| main | `0915bb709e5cbed1562c9997456b58cc191ffe9a` | 검토 시작·완료 직전 fetch에서 동일 |
| [PR #1](https://github.com/gyuun-tae/26-2_capstone/pull/1), feat/api-server | `0f48ee495395b861e09db72f3be0f838f05e5303` | open, 미병합, GitHub mergeable=true |
| feat/frontend-widget | `02061de0cbb0941f92e21e7e57e8778a51bc991d` | 실제 프론트 구현을 포함한 원격 브랜치 |

격리한 로컬 체크아웃에서 main → API → 프론트 순으로 실제 병합하여 파일 충돌이 없음을 확인했다. 이 검증용 병합 커밋은 원격에 올리지 않는다. PR이 열린 상태에서는 `git pull origin main`만으로 API·프론트 코드가 들어오지 않는다.

## 즉시 해결할 연동 문제

### 1. P1 — 채팅 경로·요청·응답 전송 방식이 모두 다름

근거: [프론트 client.ts](https://github.com/gyuun-tae/26-2_capstone/blob/02061de0cbb0941f92e21e7e57e8778a51bc991d/frontend/src/api/client.ts#L17), [Vite proxy](https://github.com/gyuun-tae/26-2_capstone/blob/02061de0cbb0941f92e21e7e57e8778a51bc991d/frontend/vite.config.ts#L12), [API chat](https://github.com/gyuun-tae/26-2_capstone/blob/0f48ee495395b861e09db72f3be0f838f05e5303/src/api/app/main.py#L37).

| 항목 | 프론트엔드 | 백엔드 | 재현 결과 |
|---|---|---|---|
| 경로 | `POST /api/chat` | `POST /chat` | 기본 프록시에 rewrite가 없어 404 |
| 질문 본문 | `{message, session_id, locale, clarification?}` | `{messages:[{role,content}]}` | 경로만 `/chat`으로 고쳐도 422 |
| 응답 읽기 | `res.json()` | `text/event-stream`, token → sources → done | 백엔드 규격으로 요청해도 JSON 해석 실패 |

프론트 기본 mock이 요청을 가로채므로 화면 시연 성공만으로 이 불일치가 드러나지 않는다. `VITE_USE_MOCK=false` 상태의 통합 검증이 필요하다. URL 환경변수 하나로 세 문제를 모두 해결할 수 없다.

### 2. P1 — 구조화된 화면 데이터·조건 선택 계약이 없음

근거: [프론트 타입](https://github.com/gyuun-tae/26-2_capstone/blob/02061de0cbb0941f92e21e7e57e8778a51bc991d/frontend/src/api/types.ts#L83), [조건 선택 요청](https://github.com/gyuun-tae/26-2_capstone/blob/02061de0cbb0941f92e21e7e57e8778a51bc991d/frontend/src/widget/useChat.ts#L117), [API Source와 AnswerType](https://github.com/gyuun-tae/26-2_capstone/blob/0f48ee495395b861e09db72f3be0f838f05e5303/src/api/app/schemas.py#L26).

- 프론트는 `type`, `title`, `lead`, `sections`, `citations`, `actions`를 사용한다. 백엔드는 문자열 토큰, `sources`, `message_id`, `answer_type`을 보낸다.
- 근거 부족은 FE `insufficient`, BE `unknown`이다. 이름 변환과 화면 표시를 함께 맞춰야 한다.
- FE의 `clarify`는 `options[]`가 필수이며 선택한 `response_id/option_id`를 다시 보낸다. 현재 BE에는 옵션 생성·선택 해석이 없다. 질문 문자열만 바꾸는 어댑터로는 조건 선택이 완성되지 않는다.
- 화면 인용 번호와 `doc_id/chunk_id` 연결, `source_url → url`, `locator → section`, `snippet → excerpt` 변환을 정의해야 한다. 수정일·수집일·문서 버전을 잃거나 임의로 만들면 안 된다.
- `supports`는 실제 답변 문장과 사용 근거의 관계여야 한다. 검색 결과 전체를 사용한 인용처럼 표시하지 않는다.

### 3. P2 — 피드백 API도 다름

FE는 `POST /api/feedback`에 `{response_id, helpful, reason?, comment?}`를 보내고 JSON을 기대한다. BE는 `PUT /messages/{정수 id}/feedback`에 `{rating:"up"|"down"}`을 받고 본문 없는 204를 반환한다. FE 방식은 404, BE 방식은 204로 재현했다. FE 피드백 UI는 아직 연결 전이므로 연결할 때 메서드·ID·본문·204 처리를 함께 바꿔야 한다. 현재 DB는 사유·댓글을 저장하지 않는다.

### 4. P2 — 짧은 답변 화면이 sections를 표시하지 않음

[ScreenView.tsx의 SimpleAnswer](https://github.com/gyuun-tae/26-2_capstone/blob/02061de0cbb0941f92e21e7e57e8778a51bc991d/frontend/src/widget/ScreenView.tsx#L169)는 `summary`가 없으면 `lead`와 행동 버튼을 표시하고 `sections`는 표시하지 않는다. 계약상 유효한 `answer + sections + summary 없음 + lead 없음`을 보내면 본문이 보이지 않는다. 짧은 응답의 본문 필드를 확정하고 그 필드로 실제 렌더링을 검증해야 한다. 이 항목은 코드 경로 검토 결과이며 브라우저 화면 테스트는 수행하지 않았다.

## PR #1의 이전 오류 수정 검증

이전 `4093800`에서 문제였던 검색 시작·로그 저장 예외 처리가 `0f48ee4`에서는 동일한 try/except 안에 있다.

| 상황 | 확인 결과 |
|---|---|
| 정상 답변 | HTTP 200, token 여러 개 → sources → done |
| 검색 시작 예외 | error 하나로 종료, done 없음 |
| 생성 중 예외 | 기존 API 테스트 통과, error 종료 |
| DB 세션 생성 실패 | 기존 API 테스트 통과, error 종료 |
| 실제 `Session.commit()` 예외 주입 | token → sources → error, done 없음, 실패 로그 추가 0건 |
| 근거 부족 | `answer_type=unknown`, sources 빈 목록 |
| 조건 확인 | `answer_type=clarify`; 구조화된 선택지는 아직 없음 |
| 정상 피드백 | 204; 없는 ID는 404, 잘못된 rating은 422 |

이전 SSE 결함은 해결된 것으로 판단한다. 서버가 보낸 `error`와 네트워크 단절·정상 종결 이벤트 없는 EOF는 FE에서 각각 처리해야 한다. DB 저장 전에 토큰·출처가 이미 도착할 수 있으므로 `done` 수신 전에는 성공 완료나 피드백 가능 상태로 확정하지 않는다.

## 실제 RAG 준비 상태

현재 구조는 다음과 같다.

```text
SQLite app.db       : 질문·답변·출처 JSON·피드백을 남기는 chat_logs
Chroma data/chroma  : PersistentClient와 컬렉션 생성 함수만 있음
rag.answer()        : 고정 mock 답변; Chroma 검색이나 LLM 호출 없음
청크 JSONL          : 178개 초안; 승인·등록·검색 연결 전
```

벡터 DB와 로그 DB는 역할이 다르다. SQLite에 채팅 로그가 저장된다는 사실은 지식베이스가 등록됐다는 뜻이 아니다. 현재 코드에는 승인 명세를 읽는 등록기, 검색 함수, 근거를 이용한 실제 생성기가 없다. `/health`는 Chroma heartbeat만 확인하므로 색인·임베딩·답변 생성 준비 완료로 해석하지 않는다.

읽기 전용으로 `data/chunks/YGPA-*/*/*/chunks.jsonl`을 확인한 결과, 31개 문서·178개 청크·승인 0개·중복 ID 0개·본문 해시 불일치 0개다. FAQ 평가 파일은 열람하지 않았다. 원문 해시 전체 재검증이나 내용·현행성 재승인을 수행한 것은 아니다.

### 등록 전에 필요한 처리

1. **승인 목록과 출처 검사**: 스냅샷·청크 버전·ID·본문 해시를 명시한 채택 목록을 읽는다. 미승인·보류·FAQ 경로 및 `bbs_no=230`은 차단한다. 과거 부칙 33개는 현재 안내 검색에서 기본 제외한다. 나머지 145개도 자동 승인하지 않는다. 설명·표의 상호 보완 버전을 함께 보존한다.
2. **서버 데이터 전달**: raw/processed/chunks는 Git 제외이므로 별도 전달하고 파일 목록·해시를 대조한다. 이번 검토는 `/home/yuntae/capstone`의 실제 자료·접속·배포 상태를 검증하지 않았다.
3. **임베딩 설정 고정**: 모델 ID·버전·차원·입력 형식·거리 지표·청크 해시를 색인 명세에 남긴다. 문서와 질문은 동일한 임베딩 공간을 사용하며 모델별 query/document 입력 규칙을 적용한다. 긴 청크의 토큰 한도를 확인하고 임의 절단을 금지한다. 현재 `get_collection()`의 기본 임베딩을 최종 모델로 간주하지 않는다.
4. **메타데이터 변환**: 벡터와 함께 원문 `text`, ID, 출처, 날짜, 버전, 승인 상태를 저장한다. 중첩 `source_locator` 객체를 Chroma metadata에 그대로 넘기는 합성 테스트는 `ValueError`였다. 검색 필터용 값을 평탄화하고 전체 구조는 JSON 문자열이나 별도 메타데이터 테이블에 보존한다. 실제 청크를 등록하지 않고 합성 벡터로만 확인했다.
5. **검색 결과 → API 변환**: 실제 청크를 `Source`에 그대로 넣으면 `locator`, `snippet` 누락으로 검증 실패한다. `processed_text`, `html_table`, `attachment_composite` 각각의 화면용 위치 문구를 만들고 원래 위치 객체를 보존한다. 빈 날짜는 null로 정규화하고 수집일을 수정일로 대신 쓰지 않는다.
6. **검색 → 생성 연결**: 승인된 활성 색인에서만 관련 청크를 검색하여 본문과 ID를 생성기에 전달한다. 반환된 답변과 실제 사용 인용을 대조한다. 부족한 근거, 보류된 사용료 별표, 현행성이 불확실한 금액·기간은 확인 불가 또는 조건 확인으로 처리한다. 자료 없는 질문에 고정 mock 답변을 돌려주는 경로를 운영에서 막는다.
7. **저장·교체·복구**: 같은 데이터 재등록 시 중복을 만들지 않고, 새 색인 검증 후 활성 버전을 바꾼다. Chroma 경로와 메타데이터·로그 DB에 영구 저장 경로와 백업을 지정한다. 현재 Dockerfile만으로 영구 볼륨이 구성되지는 않는다.

## 다음 구현 순서 제안

먼저 FE/API의 공통 규격을 하나로 확정한다. 현재 구조화된 위젯을 유지하려면 공통 RAG 서비스 위에 `POST /api/chat` JSON 응답 계층을 추가하는 방식이 변경 범위를 줄인다. 기존 `/chat` SSE는 별도 클라이언트용으로 유지할 수 있다. 이것은 이번 검토의 제안이며 구현 완료나 팀 합의로 기록하지 않는다.

SSE를 주 계약으로 선택한다면 FE에 POST 스트림 파서, 오류·EOF·취소 처리, 구조화된 완료 응답, 조건 선택 규격을 함께 구현해야 한다. 단순 URL 치환으로 끝내지 않는다. 어느 방식을 선택해도 근거 ID·버전과 실제 인용 관계를 보존한다.

그다음 합성 데이터로 정상 답변·조건 선택·근거 부족·검색/생성/저장 실패·피드백까지 FE → API → DB 계약 테스트를 만든다. 이후 승인 목록 → 임베딩 등록 → 검색 → 실제 답변 생성 순으로 진행하고 개발 질문으로 검색·인용 정확도를 확인한다. FAQ는 최종평가 전까지 개발·검색·튜닝에서 제외한다.

## 검증 기록과 한계

- 통합 체크아웃에서 `python -m unittest discover -s tests -q`: 82개 통과.
- 최신 `src/api/test_api.py`: 통과. 직전 검토와 uv.lock이 같아 해당 잠금 환경을 재사용했다.
- FE: `npm ci --ignore-scripts --no-audit --no-fund`, `npm run build`, `npm run lint` 통과.
- 추가 HTTP 검증: 404/422/SSE JSON 해석 실패, 피드백 404/204, 검색 시작·DB commit 예외, localhost CORS preflight 확인.
- 임시 Chroma에서 명시한 합성 벡터의 저장·조회 성공. 중첩 metadata 거절 확인. 실제 임베딩 모델 다운로드·청크 등록·유료 API 호출 없음.
- FastAPI 0.141.1, Starlette 1.6.0, SQLAlchemy 2.0.54, Chroma 1.5.9, Vite 8.3.1 환경.
- 첫 테스트·빌드는 Windows 샌드박스 임시 폴더/하위 프로세스 권한으로 실패했고 같은 명령을 허용된 실행 환경에서 다시 실행하여 통과했다. 코드 결함과 구분한다.
- GitHub에서 반환된 PR 커밋 status 목록은 비어 있었다. 이를 CI 통과로 해석하지 않으며 위 결과는 로컬 검증이다.
- 브라우저 전체 흐름, 실서버, 실제 검색 품질, LLM 근거 충실도, 부하·중단·배포 복구는 미검증이다. 코드 병합 가능과 운영 준비 완료를 구분한다.

PR #1은 API mock 기반으로 검토할 수 있다. FE를 포함한 서비스 연결 완료 또는 RAG 완료로 승인할 상태는 아니다.
