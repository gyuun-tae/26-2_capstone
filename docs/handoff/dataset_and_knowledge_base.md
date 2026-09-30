# 수집 원본·청크 현황과 지식베이스 등록 계획

2026-09-30 후속: [최종 계획서 대조·수정안 검증](plan_alignment_review_20260930.md), [번호별 실행 파일·설명 문서](00_pipeline_order.md). 현재 청킹은 의미 단위이며 parent-child 검색 확장은 아직 없습니다.

확인일: 2026-09-30. 로컬에 실제 저장된 파일 기준입니다. 이 문서 작성 중 공식 사이트를 재수집하거나 규정 현행성을 새로 검증하지 않았습니다.

## 현재 산출물

- 원본·본문 추출: 33건(HTML 20건, HWP5 11건, PDF 2건).
- 청크: 31개 문서에서 총 178개. HTML 설명 16개, HTML 표 54개, 첨부 108개.
- 첨부 108개 구성: 서식 전체 10개, 조문 63개, 과거 부칙 33개, 표 2개.
- YGPA-002·013은 청크가 0개이며, 다른 문서에도 일부 보류 범위가 있습니다.
- 178개 모두 `index_approved=false`. 임베딩과 검색 등록은 미실행이며, 임베딩 모델·검색 DB는 아직 확정하지 않았습니다.
- HTML은 2026-09-23, 첨부는 2026-09-27 수집본입니다. 수집일을 발행일·개정일로 대신 사용하지 않습니다.

## 파일을 보는 순서

로컬 프로젝트: `C:\Users\yountae\26-2_classes\capstone`.

| 단계 | 프로젝트 기준 경로 | 확인할 내용 |
|---|---|---|
| 문서 목록 | `data/catalog/ygpa_document_candidates.csv` 및 `.md` | 제목, 출처 URL, 날짜·질문 범주·수집 방식·주의점 |
| 원본 | `data/raw/<문서ID>/<수집스냅샷>/` | HTML은 `source.html`, HWP5는 `source.ole`, PDF는 `source.pdf` |
| 수집 정보 | 같은 폴더의 `metadata.json` | 출처, 수집 시각, 원본 해시, 날짜 검증 상태 |
| 추출 본문 | `data/processed/<문서ID>/<수집스냅샷>/document.txt` | 사람이 읽을 수 있는 본문 |
| 추출 근거 | 같은 폴더의 `document.json`, 첨부의 `blocks.json` | 추출 버전·원문 위치·페이지 또는 HWP 문단 위치 |
| 청크 보기 | `data/chunks/<문서ID>/<수집스냅샷>/<청크버전>/review.md` | 실제 나눈 청크를 읽는 검토용 문서 |
| 지식베이스 입력 후보 | 같은 폴더의 `chunks.jsonl` | 한 줄에 청크 하나와 출처·버전·검토 상태를 담은 JSON |
| 청크 기록 | 같은 폴더의 `manifest.json` | 입력·출력 해시, 처리 범위와 보류 범위 |

`source.ole`는 내려받은 HWP5 원본 컨테이너입니다. 확장자가 `.ole`여도 추출된 텍스트 파일이 아닙니다. 첨부 폴더의 `parent_source.html`은 다운로드 링크의 출처 확인용이며 검색 본문에 넣지 않습니다.

표·그림 보존 결과는 추출 폴더 아래 `hwp-tables-v1`, `hwp-tables-v2`, `hwp-graphics-v1`, `pdf-pages-v1` 등에 있습니다. YGPA-032는 `text-corrected-v1`의 보정 결과를 사용합니다. 기존 원본과 최초 추출 본문도 보존했습니다.

아래 표의 원본 링크는 로컬에서 자료가 있을 때 열립니다. GitHub에는 원본이 없으므로 GitHub 화면에서는 공식 출처인 제목 링크를 사용합니다.

## 문서별 원본과 청크 수

| 문서 ID | 제목·공식 출처 | 보존 원본 | 청크 수 |
|---|---|---|---:|
| YGPA-001 | [민원신청안내](https://www.ygpa.or.kr/hmpg/ygpa/mwse/onmw/mwgu/contPageDetail.do?conts_no=69ABE2DCEF294D449FCE2A530341F15D) | [source.html](../../data/raw/YGPA-001/20260923T053550880528Z/source.html) | 1 |
| YGPA-002 | [항만시설 이용절차](https://www.ygpa.or.kr/hmpg/ygpa/mwse/pmis/pmpr/pm01/contPageDetail.do?conts_no=D7600AC6607F41F1B506538F6CD0870E) | [source.html](../../data/raw/YGPA-002/20260923T065716905519Z/source.html) | 0 |
| YGPA-003 | [증명서발급절차안내](https://www.ygpa.or.kr/hmpg/ygpa/mwse/pfor/pmgu/contPageDetail.do?conts_no=F0065097172F4BB0AFE9967F38A39F6D) | [source.html](../../data/raw/YGPA-003/20260923T065718302105Z/source.html) | 1 |
| YGPA-004 | [실적증명서 발급신청 — 공개 증명서 종류](https://www.ygpa.or.kr/hmpg/ygpa/mwse/pfor/prfm/prfmRegistList.do) | [source.html](../../data/raw/YGPA-004/20260923T065719685275Z/source.html) | 1 |
| YGPA-005 | [체육시설 예약 — 소개](https://www.ygpa.or.kr/hmpg/ygpa/comu/resv/faci/contPageDetail.do?conts_no=553FFE81A6344CD4987BD450219FDFF8) | [source.html](../../data/raw/YGPA-005/20260923T065722418470Z/source.html) | 10 |
| YGPA-006 | [체육시설 예약 — 예약하기의 공개 이용 제한](https://www.ygpa.or.kr/hmpg/ygpa/comu/resv/faci/rsvtCalendar.do) | [source.html](../../data/raw/YGPA-006/20260923T065725225393Z/source.html) | 1 |
| YGPA-007 | [홍보관 예약 — 소개](https://www.ygpa.or.kr/hmpg/ygpa/comu/resv/prom/contPageDetail.do?conts_no=4A2880C709E0433B90ED90AEF01D0337) | [source.html](../../data/raw/YGPA-007/20260923T065726677043Z/source.html) | 1 |
| YGPA-008 | [항만안내선 예약 — 소개](https://www.ygpa.or.kr/hmpg/ygpa/comu/resv/ship/contPageDetail.do?conts_no=7AFB90C77B4F45B0A0ED114D46DD1E6E) | [source.html](../../data/raw/YGPA-008/20260923T065728052233Z/source.html) | 1 |
| YGPA-009 | [여수연안여객선터미널](https://www.ygpa.or.kr/hmpg/ygpa/port/term/cstt/contPageDetail.do?conts_no=CB334C8DFB0A48E3AF20234346EA74AB) | [source.html](../../data/raw/YGPA-009/20260923T065729420765Z/source.html) | 4 |
| YGPA-010 | [여수엑스포여객선터미널](https://www.ygpa.or.kr/hmpg/ygpa/port/term/expt/contPageDetail.do?conts_no=6798493037AB4EF8BA1986B003049BC4) | [source.html](../../data/raw/YGPA-010/20260923T065730786073Z/source.html) | 1 |
| YGPA-011 | [여수항 시설현황 — 총괄](https://www.ygpa.or.kr/hmpg/ygpa/port/yspt/faci/fa01/contPageDetail.do?conts_no=4140BB39301345688AC8FC546543B8FC) | [source.html](../../data/raw/YGPA-011/20260923T065732196863Z/source.html) | 16 |
| YGPA-012 | [광양항 광양지역 시설현황 — 총괄](https://www.ygpa.or.kr/hmpg/ygpa/port/gypt/faci/gygy/fa51/contPageDetail.do?conts_no=4250BDB752384A788FE0E2C8E60E154A) | [source.html](../../data/raw/YGPA-012/20260923T065733669747Z/source.html) | 22 |
| YGPA-013 | [광양항 여천지역 시설현황 — 총괄](https://www.ygpa.or.kr/hmpg/ygpa/port/gypt/faci/gyyc/fa01/contPageDetail.do?conts_no=A2100D9CE1294A4BB0A5CBEF440F5D27) | [source.html](../../data/raw/YGPA-013/20260923T065734975858Z/source.html) | 0 |
| YGPA-014 | [광양항 컨테이너 부두 — 소개](https://www.ygpa.or.kr/hmpg/ygpa/port/gypt/faci/gygy/fa53/contPageDetail.do?conts_no=B8FF3486A2D04D1985A4528F38B03D86) | [source.html](../../data/raw/YGPA-014/20260923T065736309061Z/source.html) | 3 |
| YGPA-015 | [광양항 자동차 부두 — 소개](https://www.ygpa.or.kr/hmpg/ygpa/port/gypt/faci/gygy/fa54/contPageDetail.do?conts_no=C29A3AE99AA9481ABDA8265417F4D8A6) | [source.html](../../data/raw/YGPA-015/20260923T065737677457Z/source.html) | 1 |
| YGPA-016 | [광양항 하포일반부두 — 소개](https://www.ygpa.or.kr/hmpg/ygpa/port/gypt/faci/gygy/fa52/contPageDetail.do?conts_no=15A91FC057B940AE98868B4EB943CF89) | [source.html](../../data/raw/YGPA-016/20260923T065739051779Z/source.html) | 2 |
| YGPA-017 | [광양항 항만관련부지](https://www.ygpa.or.kr/hmpg/ygpa/port/gypt/ptsi/pt01/contPageDetail.do?conts_no=8D6C358F52C648CCA956DD97DD0F234C) | [source.html](../../data/raw/YGPA-017/20260923T065740412723Z/source.html) | 2 |
| YGPA-018 | [광양항 철송장](https://www.ygpa.or.kr/hmpg/ygpa/port/gypt/ptsi/pt02/contPageDetail.do?conts_no=2923C709A80A4FCAA35FA45386437F88) | [source.html](../../data/raw/YGPA-018/20260923T065741802437Z/source.html) | 1 |
| YGPA-019 | [광양항 배후단지 입주지원 — 입주희망](https://www.ygpa.or.kr/hmpg/ygpa/port/gybe/mvsu/ms02/contPageDetail.do?conts_no=2F7614BF09354B08B5BB759D3D7788F6) | [source.html](../../data/raw/YGPA-019/20260923T065743159145Z/source.html) | 1 |
| YGPA-020 | [광양항 배후단지 입주지원 — 입주준비](https://www.ygpa.or.kr/hmpg/ygpa/port/gybe/mvsu/ms03/contPageDetail.do?conts_no=B47765FC88524CC7A2451671573FBAD7) | [source.html](../../data/raw/YGPA-020/20260923T065744608886Z/source.html) | 1 |
| YGPA-021 | [더드림스마트센터 이용 신청서](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000020472) | [source.ole](../../data/raw/YGPA-021/20260927T070327526743Z/source.ole) | 1 |
| YGPA-022 | [출입증분실경위서](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000002083) | [source.ole](../../data/raw/YGPA-022/20260927T070430605747Z/source.ole) | 1 |
| YGPA-023 | [항만시설출입업체등록신청서](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000007123) | [source.ole](../../data/raw/YGPA-023/20260927T070432617895Z/source.ole) | 1 |
| YGPA-024 | [항만 상시출입증 기간연장 신청서](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000008393) | [source.ole](../../data/raw/YGPA-024/20260927T070434618456Z/source.ole) | 1 |
| YGPA-025 | [항만상시출입증발급신청서](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000007140) | [source.ole](../../data/raw/YGPA-025/20260927T070436617251Z/source.ole) | 1 |
| YGPA-026 | [안전작업 계획서 표준양식](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000016984) | [source.ole](../../data/raw/YGPA-026/20260927T070438639016Z/source.ole) | 1 |
| YGPA-027 | [항만시설사용신청서양식(202106)](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000020296) | [source.ole](../../data/raw/YGPA-027/20260927T070439646089Z/source.ole) | 1 |
| YGPA-028 | [통과선박 인정 신청서](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000012170) | [source.ole](../../data/raw/YGPA-028/20260927T070441745924Z/source.ole) | 1 |
| YGPA-029 | [선박제원신고서](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=FILE_000000000012489) | [source.ole](../../data/raw/YGPA-029/20260927T070443727435Z/source.ole) | 1 |
| YGPA-030 | [여수항ㆍ광양항 통과선박 운영 지침](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=A062229EEE864AC3BFCFABBBC007787D) | [source.ole](../../data/raw/YGPA-030/20260927T070445774628Z/source.ole) | 11 |
| YGPA-031 | [여수광양항만공사 항만시설 운영규정](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=CAE1651DFFDD4BA2917B8B5C44A50F2B) | [source.pdf](../../data/raw/YGPA-031/20260927T070446904069Z/source.pdf) | 44 |
| YGPA-032 | [여수광양항만공사의 항만시설 사용 및 사용료 등에 관한 규정](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=C9B71D7B02744D889FAA190B7D853186) | [source.pdf](../../data/raw/YGPA-032/20260927T070447832791Z/source.pdf) | 43 |
| YGPA-033 | [체육시설 이용 신청서(안내 문구 기준 가칭)](https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=0D4AC8D2035D43F98897C1A1755F8EEC) | [source.ole](../../data/raw/YGPA-033/20260927T070449680617Z/source.ole) | 1 |

## 어떤 기준으로 청크를 나눴는가

| 버전 | 개수 | 단위 |
|---|---:|---|
| `semantic-v1` | 1 | YGPA-001 신청 자격의 예외와 신청 절차를 함께 보존 |
| `semantic-html-v1` | 15 | HTML 설명의 의미 단위. 조건·제한을 본문과 함께 보존 |
| `semantic-html-tables-v1` | 54 | 표 머리글·단위·병합 셀·공통 주의사항을 연결한 행 또는 행 묶음 |
| `semantic-attachments-v1` | 108 | 서식 전체, 조문, 날짜별 부칙, 독립 표 |

신청서는 작성 항목·안내·동의 문구의 연결을 유지하도록 서식 전체를 하나로 묶었습니다. 규정은 페이지 경계가 아니라 조문 단위로 나눴습니다. 표는 숫자만 떼어 넣지 않고 항목명·단위·예외 조건을 함께 담았습니다.

예를 들어 YGPA-005의 10개 청크는 설명 3개와 표 7개입니다. 두 버전은 서로 보완하므로 둘 다 채택 대상입니다. 폴더 이름을 정렬해서 마지막 버전 하나만 선택하면 설명이나 표가 누락됩니다.

청크의 `text`가 검색 대상 본문입니다. `chunk_id`, `doc_id`, `title`, `source_url`, `source_snapshot`, `document_version`, `chunking_version`, `chunk_text_sha256`, `source_locator` 등이 출처와 버전을 연결합니다. 원문 위치는 HTML 문자 범위·표 셀 또는 첨부 문단·PDF 페이지 등 형식별로 다릅니다. `published_at`, `updated_at`, `date_status`, `date_evidence`는 날짜의 확인 여부까지 전달합니다.

## 남은 범위와 등록 판단

- YGPA-002: 이미지 중심 절차의 분기·순서 확인이 필요합니다.
- YGPA-013: 표 머리글과 본문 열 대응이 불명확합니다.
- YGPA-009의 일부 시간 표기, 015의 병합 표, 019의 감면 조건 등은 보류 상태를 유지합니다.
- YGPA-030: 도형의 시각 배치와 관련 범위는 일반 텍스트로 답변하기 어렵습니다.
- YGPA-031: PDF 13~25쪽 별표와 26~29쪽 도면은 청크화되지 않았습니다. 도면 이미지 보존만 완료했습니다.
- YGPA-032: PDF 11~23쪽 사용료·계산·감면 관련 별표는 보류입니다. 현재 자료만으로 사용료 계산 전체를 지원한다고 설명하면 안 됩니다.
- 과거 부칙 33개는 현재 규정 안내 검색에서 기본 제외할 계획입니다. 남는 145개도 자동 승인되는 것은 아니며 검수 결과에 따라 최종 수가 정해집니다.

장식 문자 등 의미 변화가 작은 문제는 기록하고 진행합니다. 금액·시간·대상·단위·예외·적용일을 바꾸는 문제는 검색 승인 전에 확인합니다. 날짜가 불명확하면 그대로 표시하고, 요금·기간 등 현행성이 중요한 답변에는 별도 확인 기준을 적용합니다.

## 지식베이스에 넣을 계획

아래는 향후 구현 계획입니다. 지금 실행된 기능과 구분합니다.

```text
보존 원본 + 추출 본문
        ↓ 출처·숫자·조건 검토
채택할 청크·스냅샷·버전 목록 확정
        ↓ 승인된 청크만 선택
청크 본문 임베딩 + 본문·출처 메타데이터 저장
        ↓
검색 인덱스 생성 및 개발용 질문으로 확인
        ↓
사용자 질문 → 관련 근거 검색 → 근거를 사용한 답변 + 출처
```

### 1. 서버에 실제 데이터를 전달

GitHub에는 코드·문서·목록이 있고 `data/raw`, `data/processed`, `data/chunks`의 실제 자료는 제외돼 있습니다. 따라서 `git pull`만으로 178개 청크가 서버에 생기지 않습니다.

`/home/yuntae/capstone`에 채택할 데이터와 출처 확인에 필요한 원본·본문·구조 파일을 별도 전송합니다. 프로젝트 상대 경로를 유지하고 파일 목록과 SHA-256 해시를 대조합니다. 현재 서버의 데이터 전송 완료 여부는 이 문서에서 확인하지 않았습니다. FAQ 평가 자료는 이 전송 묶음에 포함하지 않습니다.

### 2. 사용할 청크 묶음을 확정

문서별 수집 스냅샷과 설명·표·첨부 버전을 명시한 채택 목록을 만듭니다. 검토 기록에는 승인 청크 ID, 근거 해시, 검토 결과와 적용일 확인 상태를 남깁니다. 현재 파일을 일괄 `index_approved=true`로 바꾸는 방식은 사용하지 않습니다.

등록기는 승인 결과와 해당 버전·해시의 일치를 확인해야 합니다. 미승인·보류·FAQ 출처는 차단하고, 과거 부칙은 기본 현재 안내 검색과 분리합니다. 최종 등록 개수는 검수 뒤 기록합니다.

### 3. 임베딩과 검색 저장소 연결

채택한 청크의 제목·절 제목·본문을 일정한 형식으로 구성해 임베딩 모델로 숫자 벡터를 만듭니다. 원본 `text`와 출처 정보도 함께 보관합니다. 원본 전체나 `review.md`를 별도 문서처럼 중복 등록하지 않습니다.

임베딩 모델은 한국어 검색 품질, 서버 실행 자원, 비용, 입력 길이를 확인한 뒤 정합니다. 서식 전체처럼 긴 청크는 실제 모델의 토큰 제한을 먼저 확인합니다. 초과하면 입력을 조용히 자르지 않고 문맥을 보존하는 하위 청크와 부모 참조를 새 버전으로 만듭니다.

벡터 저장소의 레코드는 벡터, 청크 ID, 본문, 제목, 출처 URL, 원문 위치, 문서·청크 버전, 날짜·검수 상태를 연결합니다. 복잡한 표 위치 정보는 별도 메타데이터 저장소에 보관하고 ID로 연결해도 됩니다. 모델 ID·버전·벡터 차원·입력 형식·청크 해시를 색인 기록에 남깁니다. 서로 다른 임베딩 모델의 벡터를 같은 색인에 섞지 않습니다.

문서가 갱신되면 새 버전의 색인을 검증한 후 활성 버전을 교체합니다. 이전 청크가 현재 검색에 중복 노출되지 않도록 하고, 이전 색인은 복구용으로 구분합니다.

### 4. 검색과 답변 연결

사용자 질문도 같은 임베딩 모델로 변환해 관련 청크를 찾습니다. 문서명·조문 번호·부두명처럼 정확한 단어가 중요한 질의는 키워드 검색을 함께 적용하는 방안을 개발용 질문으로 비교합니다. 검색 개수와 재정렬 여부는 실험 뒤 정합니다.

검색 결과에는 본문뿐 아니라 청크 ID·출처 URL·원문 위치를 전달합니다. 답변 생성 담당은 이 근거로 답변하고 실제 사용한 출처를 표시합니다. 근거가 부족하거나 보류된 사용료 별표에 의존하는 질문은 확인이 필요하다고 처리합니다. 금액·시간을 모델의 일반 지식으로 보충하지 않습니다.

이는 질문 때 외부 자료를 찾아 제공하는 RAG 구성입니다. 별도의 파인튜닝을 수행하는 계획은 아닙니다.

### 5. 평가 자료 분리

FAQ 경로 `/hmpg/ygpa/comu/faqs/`와 게시판 번호 `bbs_no=230`은 최종평가 전용으로 유지합니다. FAQ 질문·정답을 수집·본문·청크·임베딩·검색 DB·개발 프롬프트·튜닝에 넣지 않습니다. 개발 검증은 수집한 공식 안내·규정을 바탕으로 별도 작성한 질문으로 진행합니다.

색인과 설정을 확정한 다음 평가 담당자가 격리된 FAQ 데이터로 평가합니다. 같은 공개 사실이 안내 문서에도 나오는 것과 FAQ 질문·정답 자체를 개발에 사용한 것은 구분합니다. 사전학습된 외부 모델이 과거 공개 FAQ를 접했는지는 이 프로젝트에서 보장할 수 없으며, 우리가 관리하는 수집·색인·학습 단계의 유입을 차단합니다.

## 팀원에게 전달할 산출물

| 담당 | 전달물 |
|---|---|
| 데이터 처리 → 검색 | 채택 청크 JSONL, 승인 목록, 버전·해시, 보류 범위, 원문 위치 규격 |
| 검색 → API·답변 | 검색 함수, 청크 본문·점수·출처를 포함한 응답 규격, 색인·모델 버전 |
| API → 화면 | 답변, 실제 인용 출처, 근거 부족 상태, 문서 제목·URL·페이지 |
| 배포 | 데이터 전송·해시 대조 방법, 색인 생성·교체·복구 절차, 환경변수 이름 |
| 평가 | 고정된 색인·모델·설정 버전, 개발 검증 결과; 최종 FAQ는 평가 담당자가 분리 관리 |

다음 한 단계는 **178개 초안에서 첫 지식베이스에 넣을 청크와 제외할 범위를 확정하는 것**입니다. 아직 임베딩 실행이나 유료 API 호출은 하지 않았습니다.
