# HTML 설명 본문 청크화 — 2026-09-29

> 후속 상태(2026-09-29): HTML 설명 청크 15개 추가 저장 완료 확인. YGPA-001을 포함한 설명 청크는 16개입니다. 아래 준비·예상 결과 설명 이후의 상태입니다.

YGPA-001 첫 청크는 사용자 실행으로 저장 완료했다. 다음 단계는 `scripts/chunk_remaining.py`로 나머지 HTML 19건을 검사하고, 설명·조건·절차에서 15개 초안 청크를 만든다. 13개 문서가 대상이며 6개 문서는 전부 보류한다. 이 수치는 실제 저장 전 미리보기 검증 결과다.

## 실행

프로젝트 최상위 폴더에서 실행한다. 추가 설치는 필요 없다.

```powershell
Set-Location -LiteralPath "C:\Users\yountae\26-2_classes\capstone"
.\.venv\Scripts\python.exe -X utf8 -B .\scripts\chunk_remaining.py --save
```

`--save`를 생략하면 미리보기만 한다. 일부만 실행하려면 `--doc-ids YGPA-003 YGPA-004`를 추가한다. 이 스크립트는 네트워크에 접속하지 않는다.

결과: `data/chunks/<doc_id>/<원본 snapshot>/semantic-html-v1/`

- `chunks.jsonl`: 검색 승인 전 청크. 문서 전체 보류 시 빈 파일이다.
- `review.md`: 청크 내용과 처리 범위. 아래 명령으로 첫 결과를 볼 수 있다.
- `manifest.json`: 원본·본문·정책·출력 해시 및 모든 본문 범위의 처리 상태.
- 배치 실행 기록: `data/chunks/_runs/html-<시각>.json`

```powershell
$review = Get-ChildItem -Path ".\data\chunks\YGPA-003\*\semantic-html-v1\review.md" | Sort-Object FullName -Descending | Select-Object -First 1
Get-Content -LiteralPath $review.FullName -Encoding UTF8
```

## 이번 처리 범위

| 문서 | 청크 수 | 포함 내용 / 보류 |
|---|---:|---|
| 002 | 0 | 입출항 흐름도 분기 및 이미지 대체문구 검토 필요 |
| 003 | 1 | 업체회원 자격 및 전체 발급 절차 |
| 004 | 1 | 공개 증명서 종류, 이동 메뉴 제외 |
| 005 | 3 | 운영 예외·예약 기한, 유의사항, 신청 방법. 시설·시간·요금 표 및 나머지 내용 보류 |
| 006 | 1 | 계정당 시간·코트 수 제한. 달력 및 예약 UI 제외 |
| 007~008 | 각 1 | 임시 예약 제한 경고와 이용 조건을 함께 유지 |
| 009~013 | 0 | 여객선 운항·터미널 및 시설 표의 행·열 관계를 복원한 후 처리 |
| 014~016 | 각 1 | 부두 설명. 제원 표와 관련 후속 내용 보류 |
| 017 | 1 | 조성배경·기간. 면적 표 등 보류 |
| 018 | 1 | 동측·서측 철송장 설명 |
| 019 | 1 | 입주자격·신청절차. 괄호로 병기된 임대료 감면 조건은 보류 |
| 020 | 1 | 입주계약·제출 서류 11개와 제출 대상 예외를 함께 유지 |

짧은 절차·조건 묶음은 한 청크로 유지하며 최대 1,200자다. 청크 수를 늘리기 위해 문장을 임의로 끊거나 겹침을 넣지 않는다. 원문의 표현을 교정하거나 금액·단위·법령의 현행성을 추정하지 않는다. 의미 영향이 낮은 기호는 별도 수정 작업을 만들지 않는다.

## 팀 연결 규격

YGPA-001의 `semantic-v1` 필드를 이어 사용한다. `chunk_id`, `doc_id`, `document_version`, `source_snapshot`, `extraction_version`, `chunking_version`, `source_url`, `text`, `title`, `section_titles`, `source_locator`, 날짜 필드, `index_approved`를 제공한다.

- `source_locator`: CRLF→LF 정규화한 `document.txt`의 문자 위치. Unicode codepoint 기준, 시작 포함·끝 제외. 해당 범위를 자르면 청크 본문과 정확히 같다.
- `coverage_spans`: 본문 처음부터 끝까지 빈틈·중복 없이 기록한다. `chunk`는 청크에 포함, `held`는 추후 처리, `excluded`는 메뉴·달력 등 제외다. 미포함 범위를 폐기한 것으로 해석하지 않는다.
- `review_flags`: `partial_document`는 일부 보류 범위가 있다는 뜻이다. 임시 예약 제한이 있는 문서는 `temporary_reservation_restriction_included`도 기록한다.
- 모든 청크는 `review_status=draft_pending_chunk_review`, `index_approved=false`. 임베딩 담당자는 폴더 전체를 자동 등록하지 않고 승인된 버전만 입력해야 한다.
- 날짜 미확인은 그대로 유지한다. 수집일·페이지 갱신일을 규정 시행일로 해석하지 않는다.
- FAQ 경로 및 `bbs_no=230`은 URL 허용 목록보다 먼저 차단한다. FAQ 본문·정답을 개발 데이터로 읽지 않는다.
- 동일 입력·출력은 재실행 시 유지하고, 손상된 출력은 덮어쓰지 않는다. 새 본문 버전은 해시 고정 검사에서 보류되므로 경계를 검토하고 버전을 올린다.

다음 개발 단계는 이번에 보류한 HTML 표를 원본의 행·열·병합 구조에 따라 청크로 만드는 것이다. 첨부 HWP/PDF는 복원된 표·페이지 정보를 이용하는 별도 단계로 이어간다. 전체 33건이 청크화됐다고 보고하지 않는다.

## Git 공유

저장소: https://github.com/gyuun-tae/26-2_capstone

코드·문서·후보 목록·정책·합성 테스트를 공유한다. 원본, 추출 본문, 청크, 가상환경, 평가 전용 자료 및 데이터 압축본은 Git에서 제외한다. 기존 커밋의 데이터 압축본·노트북 백업은 최신 트리에서 추적 해제하며 과거 이력은 다시 쓰지 않는다.

작업 완료 시 검증 후 commit과 push까지 수행한다. 인증 등으로 push가 실패하면 로컬 커밋과 원격 미반영 상태를 구분해 보고한다.

검증: 실제 HTML 19건 읽기 전용 미리보기에서 15개 청크·오류 0건. 합성 테스트는 예약 제한·달력 제외·표 보류·출처 위치·재실행·변조 감지·FAQ 차단을 검사한다.

전체 회귀 테스트: `python -B -m unittest discover -s tests -v` 66건 통과.
