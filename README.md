# 여수광양항만공사 RAG 챗봇

공식 자료를 근거로 이용 대상·신청 절차·시설 안내에 답하고 출처를 보여주는 팀 프로젝트입니다.

## 현재 단계

- 수집·본문 추출: HTML 20건 + 첨부 13건, 총 33건 완료.
- YGPA-001: 사용자 실행으로 첫 청크 1개 저장 완료.
- 나머지 HTML 19건: 설명·조건 중심 청크화 코드 준비. 미리보기 결과 13개 문서에서 15개 청크, 표·흐름도 중심 6개 문서는 보류. [실행 및 팀 연결 안내](docs/handoff/chunking_html_batch.md).
- 첨부 표·이미지 보존 결과는 [작업 현황](docs/handoff/dataset_checkpoint_20260928.md)과 문서별 후속 안내를 참조합니다. 청크화는 아직 하지 않았습니다.
- 모든 청크는 검색 승인 전 초안입니다. 임베딩·검색 등록은 아직 하지 않았습니다.
- FAQ는 최종평가 전용이며 개발 수집·검색·튜닝에서 제외합니다.
- GitHub에는 코드·목록·규격·합성 테스트를 공유합니다. 원본·추출 본문·청크·가상환경·평가 자료는 제외하며 변경 완료 시 commit·push합니다.

## 첨부 수집 시작

Python 3.12 환경에서 프로젝트 최상위 폴더를 기준으로 실행합니다. 기존 가상환경이 있다면 생성 단계는 생략합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-collection.txt
.\.venv\Scripts\python.exe -B .\scripts\collect_attachments.py
```

마지막 명령은 우선 7건의 목록만 확인하며 네트워크에 접속하지 않습니다. 실제 다운로드 옵션과 결과 확인은 [첨부 수집 안내](docs/handoff/attachment_collection.md)를 따릅니다. 기존 `collect_remaining.py`와 `extract_remaining.py`는 HTML 19건 전용이므로 현재 확장 목록으로 재실행하지 않습니다.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_collect_attachments.py" -v
```

테스트는 합성 응답만 사용하며 FAQ 질문·정답이나 네트워크 요청을 포함하지 않습니다.

## 첨부 본문 추출

기존 가상환경에 추출 의존성을 설치한 뒤 한 건부터 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-extraction.txt
.\.venv\Scripts\python.exe -B .\scripts\extract_attachments.py --doc-ids YGPA-021 --extract
```

[첨부 본문 추출·검토 안내](docs/handoff/attachment_extraction.md)에 전체 실행 방법, 출력 규격, HWP 표·PDF 도면의 검토 한계를 정리했습니다. YGPA-030의 위치도 및 PDF 031의 26~29쪽 도면 등 이미지 속 글자는 OCR·주석과 원문 대조가 추가로 필요합니다. 현재 모든 결과는 검색 승인 전입니다.

## YGPA-021 표 구조 복원

첫 HWP 문서의 표·셀·병합·중첩 구조 복원 코드를 준비했습니다. 원본으로 시험한 표 11개·셀 193개의 위치·병합·글자가 별도 대조 자료와 일치했습니다. 기존 추출 결과를 보존하는 실행 방법은 [표 복원 안내](docs/handoff/table_restoration_021.md)에 있습니다. 실제 결과 저장은 아래 명령으로 실행합니다.

```powershell
.\.venv\Scripts\python.exe -B .\scripts\restore_tables_one.py --restore
```

표 구조 복원이 검색 승인이나 신청 조건의 의미 검수를 뜻하지 않습니다.

## 폴더 구조

```text
docs/
  planning/        전체 계획과 업무 범위·결정 기록
  contracts/       데이터·API 공통 규격
  handoff/         담당별 실행 방법과 인수인계
data/
  catalog/         공식 문서 후보 CSV·Markdown 및 검토 기록
  raw/             수집한 원본 HTML·PDF·첨부파일
  processed/       추출·정리한 본문과 메타데이터
  chunks/          검색용 청크와 출처·문서 버전
src/
  ingestion/       수집 기능
  preprocessing/   본문 추출·정리·청크화
  rag/             임베딩·검색·답변 생성
  api/             질문·답변 서버
frontend/          채팅·출처 화면
evaluation/
  datasets/        공유 가능한 개발용 질문·정답·근거
  reports/         평가 결과와 오류 분석
tests/             기능·연결 검증
infra/             DB·배포·실행 환경 설정
scripts/           수집·색인·평가 기능의 실행 진입점
```

`src/`에는 재사용할 기능을, `scripts/`에는 그 기능을 호출하는 실행 파일을 둡니다. `.gitkeep`는 빈 폴더를 Git으로 공유하기 위한 파일입니다.

## 담당 영역

| 역할 | 주 작업 위치 | 다음 담당자에게 전달할 산출물 |
|---|---|---|
| 업무·자료 | data/catalog, src/ingestion | 검증한 URL 목록, 원본, 수집 기록 |
| 정답·평가 | evaluation | 개발용 질문·기대 답변·근거, 평가 결과 |
| 문서 처리·검색 | src/preprocessing, src/rag | 출처와 버전이 연결된 청크, 검색 결과 |
| API·답변 제어 | src/api, src/rag | 공통 응답 형식, 답변 생성·보류·오류 처리 |
| 채팅·출처 화면 | frontend | 질문 입력, 답변·출처·응답 상태 표시 |
| 배포·사용성 | infra, docs/handoff | 실행·배포·복구 방법, 사용성·시연 기록 |

실제 담당자는 기존 팀 배정을 유지합니다. `src/rag`의 검색 기능과 답변 생성 기능은 파일을 나누어 담당합니다.

## 협업 문서

- [FAQ 평가 데이터 분리 규칙](docs/contracts/evaluation_boundary.md)

- [전체 진행 계획 초안](docs/planning/항만공사_RAG_챗봇_전체진행계획_초안.md)
- [공통 규격 초안](docs/contracts/README.md)
- [인수인계 안내](docs/handoff/README.md)
- [공식 문서 후보 33건 및 검토 메모](data/catalog/ygpa_document_candidates.md)
- [공식 문서 후보 CSV](data/catalog/ygpa_document_candidates.csv)

## 단계별 진행

1. 폴더와 협업 구조 준비 — 완료
2. 공식 이용·신청·시설 안내 문서 후보 20건 검증 및 목록 작성 — 완료(날짜·내용 검토 사항 별도 기록)
3. 기존 HTML 20건 수집·추출 완료 → 신규 첨부 13건 수집·검토 진행
4. 첨부 형식별 본문 추출·검토 → 청크화 및 검색 담당자에게 전달
5. 검색·답변 API·화면 연결
6. GitHub 저장소 생성, 공유 파일 검토, push

## Git 공유 범위

소스, 문서 목록, 공통 규격, 실행 안내, 공유 가능한 평가 자료를 공유합니다. `.gitignore`는 비밀키, 가상환경, 설치 라이브러리, 수집 원본·파생 데이터, 로컬 DB 볼륨을 기본적으로 제외합니다. 원본 공유가 필요하면 재배포 가능 여부와 용량을 확인하고 별도 경로를 합의합니다.

최종평가 질문·정답은 초안대로 평가 담당자가 별도 보관합니다. 필요할 경우 `evaluation/private/`를 사용할 수 있으며 이 경로는 Git에서 제외합니다.


## HWP 표 복원 후속 단계 (2026-09-28)

YGPA-021은 사용자 화면 확인에서 문제 제보가 없었습니다. 나머지 HWP 10건을 실행할 코드를 준비했습니다. 저장 전 시험에서 8건은 복원 가능했고 2건은 셀 내부 개체 처리 때문에 보류됩니다. [실행 방법과 인수인계](docs/handoff/table_restoration_remaining.md)를 확인하세요. 배치 실행 및 원문 검토, 청크화·검색 승인은 아직 별도 단계입니다.


HWP 배치에서 8건 저장·2건 보류를 확인하고 파일 해시를 검증했습니다. YGPA-033 한 건의 글자 겹침을 보존하는 후속 코드를 준비했습니다. [실행 안내](docs/handoff/table_restoration_controls.md)를 따르세요. YGPA-030의 묶인 그림·도형은 계속 보류합니다.


YGPA-033은 사용자 화면·원문 대조를 완료했습니다. 남은 YGPA-030은 [표·그림·도형 원본 데이터 보존 코드](docs/handoff/graphics_preservation_030.md)를 준비했습니다. 전용 실행 파일을 사용하며, 도형의 시각 배치 재현과 검색 승인은 아직 보류 상태입니다.


## PDF 도면 보존 준비 (2026-09-29)

YGPA-031 PDF 파일 26~29쪽을 전체 이미지로 보존하는 실행 코드를 준비했습니다. [실행·검토·인수인계 안내](docs/handoff/pdf_pages_031.md)를 따릅니다. 임시 시험과 테스트는 통과했으며, 사용자 실제 저장·원문 대조 및 OCR·검색 승인은 별도 단계입니다.


## 청크화로 전환 (2026-09-29)

YGPA-032 9쪽의 두 특수문자 보정 코드를 준비했습니다. [보정 실행 및 청크화 시작 범위](docs/handoff/symbol_correction_032.md)를 따릅니다. 사용자 요청에 따라 이 실행 다음 단계는 YGPA-001 청크화 시범입니다. 미해결 자료의 보완은 별도 진행하며 검색 승인과 구분합니다.


## 청크화 시작 (2026-09-29)

YGPA-001 본문의 첫 청크 생성 코드를 준비했습니다. [실행·인수인계 안내](docs/handoff/chunking_001.md)를 따르세요. 짧은 자격·절차 본문 173자를 한 청크로 유지하고 이동 버튼 문구만 제외합니다. 사용자 요청에 따라 의미 영향이 작은 기호 문제는 기록 후 진행하며, 답을 바꾸는 조건·수치·표 관계를 우선 검토합니다.
