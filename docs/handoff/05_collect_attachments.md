# 첨부파일 수집 — 3단계

대응 실행 파일: `scripts/05_collect_attachments.py`. 작업 번호와 기본 이름을 동일하게 맞췄습니다.

2026-09-27. 후보 목록 33건 중 첨부 13건(YGPA-021~033)을 처리하는 수집기다. 기본 선택은 우선 7건이며 나머지는 명시적으로 선택한다. 기존 HTML 수집·추출 스크립트와 별개다. 현재 검증은 오프라인 테스트와 실제 CSV의 대상 확인까지이며, 실서버 다운로드 성공 여부는 아직 확인하지 않았다.

## 팀원 환경 준비

저장소를 받은 후 프로젝트 최상위 폴더에서 PowerShell을 연다. Python 3.12 환경으로 확인했다. 가상환경 활성화 없이 해당 Python을 직접 호출하므로 PowerShell 실행 정책 변경이 필요 없다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-collection.txt
```

이미 프로젝트 가상환경과 requests가 있다면 환경 생성은 생략한다. 위 파일은 수집기의 직접 의존성만 고정하며, 향후 검색·서버·화면의 의존성은 담당자가 따로 추가한다.

## 실행 순서

1. 대상 확인: 네트워크 요청과 데이터 저장이 없다.

```powershell
.\.venv\Scripts\python.exe -B .\scripts\05_collect_attachments.py
```

기본 대상은 YGPA-021, 026, 027, 030, 031, 032, 033의 7건이다. 처음에는 021 한 건을 다운로드해 결과를 확인한다.

```powershell
.\.venv\Scripts\python.exe -B .\scripts\05_collect_attachments.py --doc-ids YGPA-021 --download
```

2. 첫 결과 확인 후 우선 7건 또는 전체 첨부 13건으로 확대한다. 아래 두 명령 중 원하는 범위를 선택한다.

```powershell
.\.venv\Scripts\python.exe -B .\scripts\05_collect_attachments.py --priority first --download
.\.venv\Scripts\python.exe -B .\scripts\05_collect_attachments.py --priority all --download
```

유효한 원본과 해시가 남아 있는 문서는 건너뛰므로 보류 문서만 재시도할 수 있다. 갱신 수집은 `--refresh`를 추가하며 기존 스냅샷을 덮어쓰지 않는다. 부모 링크 변화나 robots 차단은 URL 정책을 우회하지 말고 원인을 확인한다. 보류가 하나라도 있으면 종료 코드는 1이고, 개별 오류와 집계는 실행 기록에 남는다.

## 저장 형식과 다음 담당자

```text
data/raw/YGPA-021/<UTC snapshot>/
  source.pdf | source.ole | source.hwpx | source.docx
  parent_source.html
  metadata.json
data/raw/_collection_failures/attachments-<UTC>/
  YGPA-xxx.json     보류 사유가 있는 문서만
  summary.json      성공·기존·보류 및 경로
```

- `source.*`는 다운로드한 바이트 그대로이고 서버 파일명은 metadata의 `server_filename`에 보존한다. 서버 파일명을 저장 경로로 사용하지 않는다.
- `actual_format`은 파일 시그니처·컨테이너 식별 결과다. OLE는 HWP와 예전 Office가 공유하는 형식이므로 `.ole`로 저장하고 HWP로 단정하지 않는다. 추출 담당자가 HWP 여부와 실제 구조를 확인한다. PDF/HWPX/DOCX도 본문 해석·완전성 확인을 마친 상태가 아니다.
- `doc_id`, `source_url`, `raw_path`, `content_sha256`, `fetched_at`, `collection_batch`로 원본·추출본을 연결한다. 날짜 미확인은 그대로 유지한다.
- `parent_source.html`은 첨부 연결을 입증하는 출처 확인용이다. 메뉴 등 공통 HTML을 포함하므로 검색·본문 추출 대상에 넣지 않는다. `provenance.parent_sha256`과 `parent_fetched_at`을 검증에 사용한다.
- 신규 수집 결과도 `ingestion_status=raw_saved_pending_review`, `index_approved=false`다. 청크화·임베딩·검색 승인은 별도 단계다.
- `04_extract_remaining.py`는 HTML 19건 전용이라 새 첨부에 사용하지 않는다. 첨부의 형식별 추출은 다음 단계다.

## 수집 규칙

CSV와 정책의 ID·첨부 URL·부모 URL이 모두 일치해야 한다. FAQ 경로와 게시판 번호는 허용 목록보다 먼저 차단한다. 등록된 부모 화면에 실제 href 또는 location 이동 버튼으로 해당 첨부가 연결돼 있는지 재확인한다. 임의 JavaScript 함수를 실행하지 않으므로 인식하지 못한 동적 링크는 보류될 수 있다. 링크의 연결 관계를 확인하는 기능이며 파일 내용이 FAQ 복사본인지 자동 판별하지는 않는다. 그 검토는 추출 후 별도로 필요하다.

등록된 URL과 robots.txt만 요청하고 리다이렉트·다른 링크 순회는 하지 않는다. robots 파서는 호스트별로 재사용하되 허용 여부는 각 URL에 다시 확인한다. robots 404는 규칙 없음으로 기록하고, 나머지 오류·차단은 보류한다. 최소 1초 간격 및 robots의 더 긴 간격을 적용한다. 일시적인 연결 오류·429·5xx는 최대 3번 요청하며, 60초를 넘는 서버 대기 요청은 보류한다. 파일은 최대 25 MiB, 부모 HTML은 5 MiB로 제한한다. HTTP 200이어도 HTML/JSON 오류 응답이나 알 수 없는 파일 형식은 저장하지 않는다.

## 오프라인 테스트

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_collect_attachments.py" -v
```

테스트에는 직접 만든 가짜 응답만 사용한다. 실서버 요청과 실제 FAQ 질문·정답이 없다. FAQ URL 차단, 출처 불일치, URL별 robots 판정, 리다이렉트, 재시도, 용량 제한, 오류 HTML, 저장 메타데이터·해시·재실행을 확인한다.

## GitHub 공유

공유 대상은 수집 코드, 의존성 파일, 합성 데이터만 쓰는 테스트, CSV/Markdown 목록과 정책·인수인계 문서다. 절대 사용자 경로를 코드에 넣지 않았으므로 clone 위치가 달라도 동작한다. 원본·추출 데이터·가상환경·개인 환경 변수·FAQ 평가 데이터·이전 노트북 백업은 `.gitignore`로 제외한다. 팀원은 목록과 실행 방법으로 원본을 다시 수집한다. Git 저장소 생성·remote 연결·commit·push는 아직 수행하지 않았다.

`.gitignore`는 이미 커밋된 파일을 제거하는 기능이 아니다. 추후 최초 commit 전에 `git status --short`와 `git diff --cached --stat`으로 실제 포함 파일을 확인한 뒤 push한다.


## 이후 진행 기록 — 2026-09-27

사용자 실행으로 첨부 13건 수집 완료(첫 실행 1건, 확대 실행 성공 12건·기존 1건·보류 0건). 13건의 원본·부모 페이지 해시를 확인했다. 원본은 HWP 5.x 11건과 PDF 2건이다. 다음 실행 방법은 [첨부 본문 추출 안내](06_extract_attachments.md)에 있다. 위의 실서버 미검증 표시는 수집기 준비 시점의 기록이다.
