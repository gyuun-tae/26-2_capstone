# 첨부 13건 청크화 — 2026-09-29

현재 프로젝트에 HTML 설명·표 청크 70개가 실제 저장되어 있다. 첨부 청크는 다음 코드와 미리보기·임시 저장 검증까지 완료했으며, 아래 명령으로 실제 저장한다. 추가 설치와 API 키는 필요 없다.

```powershell
Set-Location -LiteralPath "C:\Users\yountae\26-2_classes\capstone"
.\.venv\Scripts\python.exe -X utf8 -B .\scripts\chunk_attachments.py --save
```

`--save`를 생략하면 읽기 전용 미리보기다. 한 건부터 하려면 `--doc-ids YGPA-021`을 추가한다. FAQ를 읽거나 외부 링크에 접속하지 않으며 유료 모델 API를 호출하지 않는다.

## 처리 결과 예상

| 문서 | 청크 | 방식 |
|---|---:|---|
| YGPA-021~029 | 각 1개, 총 9개 | 짧은 서식 전체를 본문·표·작성 조건과 함께 유지 |
| YGPA-030 통과선박 운영 지침 | 11 | 본문 6조, 부칙 3개, 별지 표 2개 |
| YGPA-031 항만시설 운영규정 | 44 | 본문 31조, 부칙 13개 |
| YGPA-032 시설 사용·사용료 규정 | 43 | 본문 26조(제4조의2 포함), 부칙 17개 |
| YGPA-033 체육시설 이용 신청서 | 1 | 작성 항목·동의·겹친 글자 포함 서식 전체 |
| 합계 | **108** | 기존 70개와 합치면 **178개** |

서식 청크의 실제 길이는 770~6,427자다. 이름·서명 등의 빈 입력 칸을 채운 데이터가 아니라 공사에서 제공하는 서식의 작성 항목·안내다. 문서를 작게 나누다가 작성 조건이나 동의 문구가 떨어지는 것을 피하기 위해 짧은 서식은 전체를 유지했다. 검색 실험에서 긴 서식의 검색 품질이 낮으면 이후 제목·조건을 공유하는 하위 청크로 조정한다.

## 출력과 확인

저장 위치는 `data/chunks/<doc_id>/<snapshot>/semantic-attachments-v1/`이다.

- `chunks.jsonl`: 검색 승인 전 첨부 청크.
- `review.md`: 생성한 청크와 보류 사유.
- `manifest.json`: 원본 버전, 입력·출력 해시, 원문 범위별 처리 상태.
- `data/chunks/_runs/attachments-<시각>.json`: 배치 실행 기록.

첫 결과를 확인하려면:

```powershell
$review = Get-ChildItem -Path ".\data\chunks\YGPA-021\*\semantic-attachments-v1\review.md" | Sort-Object FullName -Descending | Select-Object -First 1
Get-Content -LiteralPath $review.FullName -Encoding UTF8
```

## 보존 및 분할 규칙

- 기존 원본·추출 본문·HWP 표 복원본을 읽기만 한다. 기존 HTML 청크도 변경하지 않는다. 원본 URL·FAQ 경계·출처 대응·해시를 검증한다.
- HWP 서식은 표의 좌표·병합 범위·중첩 표 연결·표 밖 안내를 함께 담는다. 비어 있는 셀의 위치는 기존 `tables.json`에 유지하고, 검색 텍스트에는 빈 셀 개수를 기록한다. 빈칸을 0이나 해당 없음으로 해석하지 않는다. YGPA-033의 겹친 글자 ①도 유지한다.
- HWP/PDF 규정은 조항 제목을 경계로 나눈다. 페이지가 바뀌어도 같은 조항의 항·호·예외를 한 청크로 유지한다. `제3조에 따라` 같은 참조 문구는 새 조항으로 인식하지 않는다.
- 부칙은 해당 날짜가 있는 부칙 제목부터 다음 부칙 전까지 묶는다. `historical_provision_not_current_rule`을 붙여 과거 시행·적용 내용과 본문 조항을 구분한다. 수집일을 시행일로 채우지 않는다.
- YGPA-032는 검증된 `text-corrected-v1`을 사용한다. 이미 보정한 두 특수문자 외에 표현을 새로 수정하지 않는다.
- 서식 전체는 12,000자, 조항·부칙·별지 표는 6,000자를 넘으면 의미 단위를 임의로 자르지 않고 보류한다. 이번 원본에서는 길이 때문에 보류된 청크가 없다.

## 이번에도 남는 보류 범위

| 대상 | 남는 내용 |
|---|---|
| YGPA-030 | 도형·지도 배치를 포함한 별지 표 1개와 관련 제목/맥락. 제·개정 이력은 독립 검색 청크로 만들지 않음 |
| YGPA-031 | PDF 13~25쪽 별표와 26~29쪽 도면. 이번에는 1~12쪽 조항·부칙만 청크화 |
| YGPA-032 | PDF 11~23쪽 요금·산정기준·감면 표. 이번에는 1~10쪽 조항·부칙만 청크화 |
| 전체 | 날짜·현행성 확인 및 검색 승인. 서식에 보류 단위가 0개여도 의미·현행성 검수가 끝난 것은 아님 |

실행 로그의 보류 단위에는 규정 앞의 제·개정 이력도 들어간다. 이것은 정보가 유실됐다는 뜻이 아니라 원문 위치를 기록하고 독립 청크 생성을 보류했다는 뜻이다. PDF 별표가 빠져 있으므로 요금·감면·시설 수치를 완전히 답할 수 있는 데이터로 간주하지 않는다. HTML의 기존 보류 부분도 그대로 남는다.

## 팀 연결 규격

공통 필드 `chunk_id`, `doc_id`, `document_version`, `source_snapshot`, `source_url`, 제목·날짜 필드, `index_approved`를 유지한다. `chunk_kind`는 `whole_form`, `article`, `historical_addendum`, `table`이다.

`source_locator.kind=attachment_composite`이며 다음 필드를 사용한다.

- `source_refs`: 기존 `blocks.json` 경로, 0부터 시작하는 `block_index`, PDF 페이지/HWP 레코드 위치, 블록 내 문자 시작·끝(끝 제외). Unicode codepoint 기준이다.
- `table_ids`, `tables_path`: 같은 원본의 복원 표·셀·중첩 관계에 연결한다. 서식 텍스트는 구조를 풀어 쓴 결과이므로 원문 연속 문자열과 같지 않을 수 있다.
- `context_refs`: 별지 표 앞 제목 등 추가 맥락의 정확한 원문 위치. 주 본문 범위와 구분하여 관리한다.
- `structure_version`: HWP의 `hwp-tables-v1`, `hwp-tables-v2`, `hwp-graphics-v1` 또는 PDF 본문 보정 버전.

`manifest.coverage`는 각 원문 블록의 모든 문자를 빈틈·중복 없이 `chunk`, `held`, `context_only`에 배정한다. 맥락으로 반복 인용한 범위는 주 범위 처리와 별도로 표시한다. 검색 담당자는 현재 원본 snapshot과 채택한 청크 버전을 명시하고 `chunk_id`로 중복을 방지한다.

모든 결과는 `index_approved=false`, `review_status=draft_pending_chunk_review`다. 임베딩·검색 등록 담당자는 생성된 파일 전체를 무조건 등록하지 않고 승인 대상만 선택해야 한다. PDF/HWP 규정에는 `appendix_material_partially_held` 표시가 있으며 부칙의 현재 적용 여부를 자동 판정하지 않는다.

## 검증·공유 상태

전체 테스트 82건 통과(첨부 청크 테스트 7건 추가). 실제 첨부 13건에서 고유 청크 ID, 원문 위치, 원본 보존, 임시 폴더 저장·동일 입력 재실행을 확인했다. 실제 프로젝트에는 이 검증으로 새 청크를 쓰지 않았다.

이 코드·테스트·설명 문서는 Git 공유 대상이다. 실제 원본·본문·청크는 `.gitignore`로 제외한다. 이후에도 코드·문서 변경은 검증하고 커밋하여 `origin/main`에 push한다.
