# 첫 청크 생성 — YGPA-001

대응 실행 파일: `scripts/12_chunk_one.py`. 작업 번호와 기본 이름을 동일하게 맞췄습니다.

2026-09-29. YGPA-032 특수문자 보정 실행 완료 보고를 받았다. 이제 청크화로 전환한다. 사용자 요청에 따라 정보 의미에 영향이 작은 장식 기호·괄호 문제는 기록만 남기고 진행한다. 숫자, 단위, 날짜, 부정·예외, 신청 자격, 순서, 표의 대상·조건 연결처럼 답을 바꿀 수 있는 문제는 우선 검토한다. 모든 미해결 문서 검토를 청크 초안 생성의 선행 조건으로 두지 않는다.

## 실행

```powershell
Set-Location -LiteralPath "C:\Users\yountae\26-2_classes\capstone"
.\.venv\Scripts\python.exe -B .\scripts\12_chunk_one.py --save
```

옵션 없이 실행하면 청크 본문을 미리 보여주며 파일을 저장하지 않는다. 기존 환경을 사용하며 새 패키지 설치, 네트워크 요청, 임베딩 또는 벡터DB 등록은 없다.

## 청크 결정

실제 입력 본문 중 신청자격과 1~4단계 절차는 합쳐서 173자(LF 줄바꿈 포함)다. 짧으므로 한 청크로 유지한다. 억지로 자격과 절차를 나누면 회원가입 예외나 절차 순서가 빠질 수 있다. 문자 수는 토큰 수가 아니다. 토큰 제한 기반 일반 청커는 아직 구현하지 않았다.

‘사진촬영신청’, ‘항만시설견학신청’은 원본 HTML에서 신청 화면으로 이동하는 링크 버튼임을 확인했다. 청크 본문에서는 제외하고 제외 원문·문자 위치·이유를 manifest에 남긴다. 링크를 따라가거나 해당 신청 화면을 수집하지 않는다. 청크와 제외 영역을 이어 붙이면 정규화한 원문 전체가 복원된다.

## 출력과 팀 규격

경로: `data/chunks/YGPA-001/20260923T053550880528Z/semantic-v1/`

- `chunks.jsonl`: 한 줄에 청크 JSON 1개. 이번 문서는 1줄이다.
- `manifest.json`: 원본·메타데이터·본문 파일 해시, 정책 해시, 원문/포함 문자 수, 제외 범위, 출력 해시, 생성 시각.
- `review.md`: 청크 본문과 출처를 사람이 볼 수 있는 문서.

핵심 필드:

| 필드 | 의미 |
|---|---|
| chunk_id | doc_id와 원본·추출·청크 버전·본문 위치·텍스트의 해시로 만든 결정적 ID |
| doc_id / document_version | 문서 ID / 원본 HTML SHA-256 |
| source_snapshot / extraction_version / chunking_version | 수집·추출·청크 처리 버전 |
| source_url / title / section_titles | 원문 인용 주소와 문서·절 제목 |
| text / chunk_text_sha256 | 청크 본문과 그 UTF-8 해시 |
| text_sha256 | CRLF를 LF로 정규화한 입력 본문 해시. 기존 추출 메타데이터와 일치 |
| source_locator | 처리 파일 상대 경로, 문자 시작·끝, 행 범위. HTML에 가상 페이지 번호를 만들지 않음 |
| published_at / updated_at / date_status / date_evidence / fetched_at | 원문 확인 날짜·그 의미와 수집 시각을 구분해 전달 |
| review_status / index_approved | draft_pending_chunk_review / false |

source_locator 문자 오프셋은 CRLF→LF 정규화 후 Python Unicode 코드포인트 기준 0부터이며 끝은 미포함이다. 실제 첫 청크는 [0,173), 행 1~15다. 원본 파일을 수정하지 않고, manifest에는 실제 파일 바이트 해시도 별도로 기록한다. 입력에 없는 발행일을 수집일로 채우지 않는다.

검색 담당자는 문서별 사용할 snapshot과 처리 버전을 명시해서 읽어야 한다. data/chunks 아래 모든 버전을 재귀적으로 모으면 같은 문서의 이전 결과가 중복될 수 있다. API 담당자는 source_url·title·source_locator·document_version을 인용 근거로 연결할 수 있다. 아직 임베딩·색인 기능은 없으며 index_approved=false를 자동으로 true로 바꾸지 않는다.

## 입력 확인과 검증

공식 목록의 YGPA-001만 읽는다. 목록/원본/처리 결과의 URL·문서 ID가 같은지, 원본과 본문 해시가 맞는지 검사한다. FAQ 경로 및 bbs_no=230은 URL 허용 목록보다 먼저 차단한다. 평가 문답이나 파생 문답을 가져오지 않는다. 정책 검사에 수집기 함수를 재사용하지만 HTTP 요청 함수는 호출하지 않는다.

실제 본문으로 임시 생성 시험을 했고 동일 입력에서 같은 ID·본문을 얻었다. 재실행 시 결과 유지와 변경된 출력 거부를 확인했다. 합성 테스트 4개는 자격·절차 순서 보존, 제외 영역을 포함한 원문 복원, CRLF 위치, 입력·원본 변경 탐지, FAQ 차단, 저장·재실행·변조 탐지를 검증했다.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_chunk_one.py" -v
```

코드·테스트·이 문서는 공유하며 실제 청크는 기존 data/chunks Git 제외 규칙을 따른다. 최초 사용자 실행은 아직 대기 상태다. 실행 결과를 확인한 뒤 다른 HTML 문서로 확대하고, 표는 제목·행 머리글·단위·조건을 포함하는 별도 청크 규칙으로 이어간다. 미해결 도면이나 현행성 검토가 필요한 규정은 자동으로 포함하지 않는다.
