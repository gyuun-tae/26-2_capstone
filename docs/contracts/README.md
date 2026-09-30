# 공통 데이터 규격 초안

이 문서는 구현 전 팀원이 맞출 데이터 항목의 초안입니다. 실제 CSV 열과 JSON 형식은 후보 문서 검증 단계에서 예시와 함께 확정합니다.

## 연결 흐름

공식 문서 목록 → 원본 수집 → 본문 추출·검토 → 청크 → 검색 → 답변 API → 화면

## 문서 후보 목록

저장 예정 위치: `data/catalog/ygpa_document_candidates.csv` 및 같은 이름의 `.md`.

| 항목 | 의미 |
|---|---|
| doc_id | 목록·원본·청크·평가에서 공통으로 사용할 안정적인 문서 ID |
| source_url | 검증한 공식 원문 URL |
| title | 실제 문서 제목 |
| published_at / updated_at | 원문에서 확인한 발행일·갱신일, 확인 불가 시 빈 값 |
| date_status / date_note | 날짜 확인 여부와 원문 표시의 의미·정확도 |
| question_category | 해당 문서가 답할 수 있는 사용자 질문 범주 |
| collection_method | HTML 수집, 첨부파일 다운로드 등 제안 방식 |
| chunking_notes | 절차·표·조건·단위를 보존하기 위한 청크화 주의점 |
| access_status / access_note | 원문 접근 성공·불가·미검증 상태와 이유 |
| verified_at | 원문 접근·내용을 확인한 시각 |
| review_status | 후보·검토 필요·수집 승인 등 팀 검토 상태 |

접근 상태와 날짜 상태는 독립적으로 기록합니다. 접근 불가 문서를 검증 완료로 표시하지 않고, 날짜가 불명확한 문서에는 임의의 날짜를 채우지 않습니다. 수집 시각·검색 결과의 날짜·사이트 저작권 연도를 발행·갱신일로 대체하지 않습니다.

## 수집·정리 문서

`doc_id`, 제목, 제공 기관, 원문 URL, 업무 분류, 언어, 확인 가능한 발행·갱신·시행일, 실제 수집 시각, 원본 경로, 내용 해시, 문서 버전, 추출·검토 상태를 유지합니다.

## 검색용 청크

`chunk_id`, `doc_id`, 문서 버전, 본문, 절 제목·페이지 등 근거 위치, 원문 URL을 전달합니다. 표의 대상·금액·조건·단위와 절차 순서를 함께 보존합니다. 페이지가 없는 HTML에는 가상의 페이지 번호를 만들지 않습니다.

## API와 화면

답변 내용, 응답 유형(답변·조건 확인·확인 불가·오류), 인용 근거 목록을 공통 예시로 맞춥니다. 근거 목록에는 문서 ID, 청크 ID, 제목, 원문 URL, 근거 위치, 확인 가능한 날짜와 수집 시각을 포함합니다. 경로·필드 타입·예시 응답은 서버와 화면 담당자가 연결 전에 확정합니다.

## 후보 목록 0.1 규격 — 2026-09-23

[후보 CSV](../../data/catalog/ygpa_document_candidates.csv)의 실제 필드와 상태값은 [목록 문서의 CSV 규격](../../data/catalog/ygpa_document_candidates.md#csv-규격)을 기준으로 연결합니다. 위의 초기 제안 중 정확한 확인 시각을 뜻하는 `verified_at` 대신, 이번 목록은 확인 날짜만 알 수 있어 `verified_on`을 사용합니다. 실제 수집 시각 `fetched_at`은 다음 단계의 수집 기록에 시간대와 함께 별도로 남깁니다.

20개 `doc_id`를 원본·처리 문서·청크·평가의 공통 식별자로 유지합니다. `date_status`와 `review_status`는 서로 다른 항목이며, 날짜 미표시나 충돌을 수집일로 덮어쓰지 않습니다. `web_readable`은 웹 도구 반환본의 공개 본문 확인을 뜻하며 사용자 PC의 HTTP 수집 성공을 보장하지 않습니다. `priority=first_batch`인 5건부터 수집 실습을 제안하며, 색인 승인 상태는 추출·원문 대조 후 별도 관리합니다.

## FAQ 평가 데이터 분리

사용자 결정에 따라 [평가 데이터 분리 규칙](evaluation_boundary.md)과 [URL 수집 정책](data_separation_policy.json)을 우선 적용합니다. FAQ는 최종평가 전용이며 수집·본문 처리·검색 색인·프롬프트 예시·개발 튜닝에서 제외합니다. 초기 수집 기록은 `ingestion_status=raw_saved_pending_review`, `index_approved=false`로 남기고 검토 후 별도 승인합니다.

## 후보 목록 0.2 확장 — 2026-09-27

CSV에 YGPA-021~033 첨부 후보 13건을 추가하여 총 33건으로 관리한다. 기존 20개 ID와 기존 열의 값은 유지했다. parent_source_url, parent_published_at, format_hint, discovery_id를 끝에 추가했다. 부모 게시글의 작성일은 첨부의 발행·개정일이 아니다. 신규 날짜는 unverified_attachment, 접근 상태는 attachment_link_verified이며 첨부 본문은 아직 검증하지 않았다. 우선순위와 8건의 보류 이유는 [현재 목록](../../data/catalog/ygpa_document_candidates.md)을 기준으로 연결한다.

수집 정책 1.1의 allowed_urls는 등록한 source_url 33개다. allowed_parent_urls는 출처 검증용이고 attachment_sources는 첨부별 부모 관계다. FAQ 제외·리다이렉트 금지·링크 순회 금지는 유지한다. 후보 등록 및 URL 지정은 실제 수집이나 검색 승인이 아니다. 기존 일괄 코드는 19건 제한 및 HTML 전용이므로 다음 단계에서 변경 전 재실행하지 않는다. require_attachment_provenance 요구는 새 수집기에서 구현해야 한다.


## 첨부 수집기 연결 — 2026-09-27

`scripts/05_collect_attachments.py`가 정책 1.1의 정확한 첨부·부모 URL 대응과 `require_attachment_provenance`를 검사한다. 준비 상태는 `collector_ready_live_unverified`이며 실서버 수집 완료 상태가 아니다. [실행·인수인계 안내](../handoff/05_collect_attachments.md)를 현재 수집 절차로 사용한다.

원본 메타데이터에 `actual_format`, `format_validation`, `server_filename`, `bytes`, `content_sha256`과 `provenance`를 추가한다. `actual_format=ole_compound`는 HWP로 확정된 값이 아니므로 추출 담당자가 컨테이너 내부 구조를 확인한다. `provenance.parent_raw_path`는 링크 근거 확인용이며 검색·본문 추출 입력에서 제외한다. 문서 연결에는 `doc_id`, `source_url`, `raw_path`, `collection_batch`를 사용한다. 수집 후에도 `index_approved=false`이며 날짜 미확인을 수집일로 채우지 않는다.


## 첨부 본문 추출 규격 — 2026-09-27

`scripts/06_extract_attachments.py`는 기존 원본·출처 해시와 URL 대응을 검사하고 HWP 5/PDF 본문을 읽는다. [현재 추출 안내](../handoff/06_extract_attachments.md)를 따른다. 출력은 원본 snapshot과 같은 이름의 처리 폴더에 `document.txt`, `document.json`, `blocks.json`, `review.md`다.

수집 때의 `actual_format`은 보존하고 `extracted_format`으로 확인된 내부 형식을 기록한다. `blocks`의 위치는 PDF 파일 페이지 번호 또는 HWP 구역·레코드이며 검색용 청크가 아니다. `review_flags`, `extraction_details`의 표·빈 페이지·짧은 페이지 기록을 검수에 사용한다. HWP 표 셀 관계와 이미지 내용은 미복원이며 모든 출력은 `index_approved=false`, `review_status=pending_manual_comparison`이다. 날짜 검증과 현행성 판단은 별도다.


## YGPA-021 표 복원 규격 — 2026-09-27

`07_restore_tables_one.py`는 기존 처리 snapshot 아래 `hwp-tables-v1/`에 별도 결과를 만든다. `tables.json`의 행·열은 0부터 시작하며 병합 정보는 rowspan/colspan이다. parent_cell_id 및 nested_table_ids로 중첩 표를 연결한다. blocks_with_tables.json은 기존 문단의 텍스트·위치를 유지하고 table_id/cell_id만 추가한다. 표 밖 문단의 연결 값은 null이다.

실행·전체 필드 설명은 [표 복원 안내](../handoff/07_restore_tables_one.md)를 따른다. 원본 버전 해시와 출력 해시를 유지하며 물리적인 표 구조 복원 이후에도 의미·현행성 검수와 검색 승인은 별도다. 이 단계에서는 YGPA-021만 지원한다.


## YGPA-030 개체 보존 결과

`hwp-graphics-v1`은 표·이미지·도형 레코드와 내부 문단을 보존하는 별도 형식이다. `graphic_object_id`로 기존 문단과 개체를 연결한다. `visual_layout_status=not_rendered_pending_review`, `index_approved=false`를 유지한다. `tables.json`의 graphic_objects와 `graphics.json`의 objects는 같은 개체이므로 중복 처리하지 않는다. [세부 규격](../handoff/09_restore_graphics_030.md)을 따른다.


## 첫 청크 규격 semantic-v1 (2026-09-29)

YGPA-001은 신청자격 예외와 4단계 절차를 한 청크로 유지한다. chunks.jsonl에 출처·원본 해시·추출/청크 버전·정규화된 원문 문자/행 위치·날짜 의미를 포함한다. index_approved=false다. [실행 방법과 확정한 시범 규격](../handoff/12_chunk_one.md)을 따른다. 이 시범 코드를 다른 문서에 그대로 적용하지 않는다.


## HTML 청크화 확대 (2026-09-29)

[현재 실행·처리 범위·팀 연결 규격](../handoff/13_chunk_remaining.md)을 따릅니다. HTML 19건을 검사하여 13개 문서에서 15개 초안 청크를 준비합니다. 나머지 6개 문서 및 일부 표 범위는 명시적으로 보류합니다. FAQ 제외, 원문 위치 추적, index_approved=false를 유지합니다.


## HTML 표 청크화 (2026-09-29)

[표 청크 실행·규격](../handoff/14_chunk_html_tables.md): 설명 청크 16개 실제 저장 확인 후, 표 14개의 구조를 보존하는 청크 54개를 준비했습니다. source_locator.kind=html_table 및 context_locators로 원본 셀·조건을 연결합니다. 표가 일부 보류됐으므로 전체 문서 완료나 검색 승인으로 해석하지 않습니다.


## 현재 첨부 청크화 단계 (2026-09-29)

HTML 청크 70개 실제 저장 확인. [첨부 13건 청크화 실행·규격](../handoff/15_chunk_attachments.md)에서 108개 추가 청크를 준비했습니다. source_locator.kind=attachment_composite로 문단/페이지/표를 연결합니다. 부칙은 과거 적용 규정 표시를 붙이며 PDF 별표·도형 배치는 보류합니다. 코드·설명 문서 갱신 후 커밋·main push까지 수행합니다.


## 첨부 청크 실제 저장 확인 (2026-09-29)

첨부 108개 저장 완료. HTML 70개와 합쳐 31개 문서에서 총 178개입니다. 출력 해시·개수·ID 고유성·검색 미승인 상태를 확인했습니다. [최신 저장 기록](../handoff/chunking_attachments.md)을 따릅니다. YGPA-002·013 및 일부 표·도형·날짜 검토는 남아 있으며, 다음 단계는 보류/검수 결과에 따라 검색용 청크와 채택 버전을 확정하는 것입니다.
