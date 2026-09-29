# 첨부 본문 추출 — 4단계

2026-09-27 기준. 저장된 첨부 13건은 HWP 5.x 11건과 PDF 2건이다. HWP는 FileHeader와 BodyText 구조로 확인했다. PDF는 YGPA-031 29쪽, YGPA-032 23쪽이다. 추출 시험은 임시 폴더에서 13건 모두 텍스트가 나오는 것까지 확인했으며, 프로젝트의 처리 결과는 아래 명령으로 생성한다.

## 설치와 첫 실행

프로젝트 최상위 폴더에서 PowerShell을 연다. 기존 `.venv`를 사용한다. 새 팀원은 먼저 README에 따라 Python 3.12 가상환경을 만든다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-extraction.txt
.\.venv\Scripts\python.exe -B .\scripts\extract_attachments.py --doc-ids YGPA-021 --extract
```

`--extract` 없이 실행하면 대상 목록만 보여준다. 스크립트는 외부 URL에 요청하지 않고 이미 수집한 파일만 읽는다. `.ole`를 `.hwp`로 이름 변경할 필요는 없다. 설치하는 추가 직접 의존성은 `olefile==0.47`, `pypdf==6.19.0`이며 requests는 기존 수집기와 공유한다.

## 첫 결과 확인 후 13건 확대

```powershell
.\.venv\Scripts\python.exe -B .\scripts\extract_attachments.py --all --extract
```

이미 같은 원본·추출기 버전으로 생성했고 해시가 일치하는 결과는 유지한다. 불완전하거나 다른 버전인 결과가 있으면 덮어쓰지 않고 보류한다. 오류 기록의 문서 ID와 원인을 확인한 후 처리한다. 보류가 하나라도 있으면 종료 코드는 1이다.

## 결과 열기

```powershell
$snapshot = Get-ChildItem -LiteralPath '.\data\processed\YGPA-021' -Directory |
    Sort-Object Name -Descending | Select-Object -First 1
Get-Content -LiteralPath (Join-Path $snapshot.FullName 'document.txt') -Encoding UTF8
```

저장 구조:

```text
data/processed/YGPA-021/<원본 snapshot>/
  document.txt    사람이 대조할 본문
  document.json  출처·원본 해시·본문 해시·상태·검토 사항
  blocks.json    PDF 페이지 / HWP 구역·레코드별 텍스트
  review.md      문서별 대조 항목
data/processed/_extraction_failures/extract-attachments-<UTC>/
  YGPA-xxx.json  보류한 문서의 오류
  summary.json   전체 처리 결과
```

TXT의 `[PDF 파일 페이지 N]`, `[HWP 구역 SectionN]`은 추출기가 넣은 위치 표식이다. 원문의 제목으로 해석하지 않는다. PDF 번호는 1부터 세는 파일 페이지이며 인쇄 쪽번호와 다를 수 있다. HWP 구역·레코드는 페이지 번호가 아니다. `blocks.json`은 검색 청크가 아니므로 그대로 색인하지 않는다.

## 검증 범위와 남은 검토

- 원본·부모 HTML의 해시, CSV와 정책의 URL 대응, 부모 페이지의 첨부 링크를 확인한 후 본문을 읽는다. 부모 HTML은 출처 증명용으로만 읽으며 본문에 합치지 않는다. FAQ 차단 정책을 그대로 적용한다.
- HWP 5의 문단 레코드와 제어문자를 읽는다. 압축 스트림의 크기를 제한하고 수집 파일에 있는 CRC·길이 꼬리 정보를 검증한다. 손상·암호화·배포용·DRM 문서는 보류한다. HWPX·DOCX는 현재 표본에 없으므로 이번 추출기는 지원하지 않는다.
- HWP 표는 셀 안의 문자가 문단 순서로 추출되지만 셀의 행·열·병합 관계는 복원하지 않았다. `extraction_details.tables`에 표의 구역·레코드 위치와 행·열 수를 남긴다. 한 줄씩 이어진 신청 항목을 일반 문장이나 확정 조건으로 해석하지 않는다.
- HWP 자동번호·레이아웃·이미지·수식은 완전히 재현되지 않는다. 본문 외의 미리보기 텍스트를 본문 대신 사용하지 않는다. 표·자동번호·이미지의 누락 여부는 원문을 열어 확인한다.
- PDF는 페이지별 레이아웃 텍스트를 보존하지만 정확한 표 구조가 아니다. OCR은 수행하지 않았다. 빈 페이지·글자가 적은 페이지는 페이지 번호를 기록한다.
- 실제 시험에서 **YGPA-031 파일 28~29쪽은 도면**이며 텍스트 추출만으로 도면 안 글자·치수를 확보하지 못했다. 해당 쪽은 이미지 대조 또는 OCR 후 검수가 필요하다. 문서 전체가 완전히 추출됐다고 판단하면 안 된다.
- **YGPA-032 파일 9쪽에는 사설 영역 문자 1종**이 있어 원문 대조가 필요하다. 문자를 추측해서 자동 치환하지 않았다.
- PDF 대표 페이지(031의 1·28·29쪽, 032의 9·15쪽)를 이미지로 확인했다. 전체 52쪽을 시각 검수한 것은 아니다. HWP 전체 서식의 시각 대조 역시 미완료다.
- 모든 결과는 `index_approved=false`, `review_status=pending_manual_comparison`이다. 추출 상태가 성공이어도 내용 검수·현행성 검토·검색 승인을 뜻하지 않는다. 발행일·개정일은 임의로 채우지 않는다.

## 다음 담당자에게 전달할 규격

`doc_id`, `source_url`, `document_version`(원본 SHA-256), `source_snapshot`으로 수집과 추출을 연결한다. `text_sha256`과 `blocks_sha256`은 각각 저장한 TXT·blocks JSON 파일의 바이트 해시다. `extraction_version`은 이번 구현에서 `attachments-text-v1`이다.

`actual_format`은 수집 당시의 컨테이너 판정(예: ole_compound)을 유지하며, 새 `extracted_format=hwp5/pdf`가 내부 구조를 확인한 추출 형식이다. 라이브러리 버전은 `extractor_dependencies`에 남긴다. 과거 수집 당시의 후보 검증 문구보다 새 추출 상태·검토 사항을 기준으로 현재 처리 상태를 판단한다.

검색 담당자는 `data/processed` 전체를 바로 색인하지 않는다. 문서 처리 담당자가 표·숫자·예외·날짜를 원문 대조한 후 별도 승인한 청크만 넘긴다. 청크화는 이번 단계에 포함하지 않는다.

## 테스트와 GitHub 공유

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_extract_attachments.py" -v
```

합성 데이터 테스트 11개가 통과했다. HWP 제어문자·확장 레코드·압축 손상·구역 순서·지원하지 않는 보호 형식, PDF 빈 페이지·암호화, 원본 해시·경로 검증, 결과 저장·재실행·손상 결과 보호를 확인한다. 실제 FAQ 문답이나 수집 문서는 테스트에 넣지 않았다.

GitHub에는 스크립트·의존성 파일·합성 테스트·이 안내를 공유한다. 원본과 추출 결과는 기존 `.gitignore` 규칙에 따라 제외한다. 코드에 사용자 PC의 절대 경로를 넣지 않았으므로 팀원도 같은 저장소 구조에서 실행할 수 있다. 임시 시험 결과나 로컬 설치 라이브러리는 프로젝트에 포함하지 않는다.

## 구현 참고

- [한컴 HWP 5 공개 형식 규격](https://cdn.hancom.com/link/docs/%ED%95%9C%EA%B8%80%EB%AC%B8%EC%84%9C%ED%8C%8C%EC%9D%BC%ED%98%95%EC%8B%9D_5.0_revision1.3.pdf): 파일 헤더, 레코드, 제어문자, 표 구조.
- [한컴의 Python HWP 구조 설명](https://tech.hancom.com/python-hwp-parsing-1/): OLE 스트림과 레코드 접근 방식.
- [pypdf 텍스트 추출 문서](https://pypdf.readthedocs.io/en/stable/user/extract-text.html): 레이아웃 추출과 OCR·표 구조의 한계.

한컴 공개 규격을 바탕으로 제한된 문단 추출 기능을 작성했다. pyhwp의 소스 코드를 복사하거나 런타임 의존성으로 포함하지 않았다.


## 실제 추출 및 1차 대조 완료 — 2026-09-27

사용자 실행으로 첨부 13건이 모두 처리 폴더에 저장됐고 해시 검증을 통과했다. [1차 검토 결과](attachment_review_20260927.md)를 후속 보완 기준으로 사용한다. 위 시험 단계의 031 도면 28~29쪽 표시는 **26~29쪽 전체로 확대**한다. HWP 030에도 본문에서 빠진 위치도 이미지가 있다. HWP 전체 문단의 공백 제거 후 내용·순서는 별도 파서와 일치했지만 표 구조 검수와 검색 승인은 아직 아니다.
