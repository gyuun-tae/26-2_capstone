# YGPA-021 표 구조 복원

대응 실행 파일: `scripts/07_restore_tables_one.py`. 작업 번호와 기본 이름을 동일하게 맞췄습니다.

2026-09-27. 더드림스마트센터 이용 신청서 1건을 대상으로 기존 문단과 표의 셀 위치를 연결하는 단계다. 다른 HWP의 처리는 아직 확대하지 않는다. 네트워크를 사용하지 않으며 추가 패키지 설치도 없다. 앞 단계의 requirements-extraction.txt 환경을 사용한다.

## 실행

프로젝트 최상위 폴더의 PowerShell에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -B .\scripts\07_restore_tables_one.py --restore
```

옵션 없이 실행하면 준비 안내만 출력하며 파일을 저장하지 않는다. 원본, document.txt, document.json, blocks.json을 보존하고 다음 하위 폴더에 별도 결과를 쓴다.

```text
data/processed/YGPA-021/<원본 snapshot>/hwp-tables-v1/
  tables.json              표·셀·병합·문단 정보
  blocks_with_tables.json  기존 문단 + table_id/cell_id 연결
  tables.html              사람이 확인할 표 구조 화면
  validation.json          원본·입력·출력 해시와 검사 수치
```

검증된 같은 결과가 있으면 건너뛴다. 기존 결과가 손상됐거나 버전이 다르면 덮어쓰지 않고 보류한다. 이번 코드는 YGPA-021의 확인된 HWP 구조만 지원하며, 자동으로 다른 문서를 처리하지 않는다.

## 결과 열기

```powershell
$snapshot = Get-ChildItem -LiteralPath '.\data\processed\YGPA-021' -Directory |
    Sort-Object Name -Descending | Select-Object -First 1
Invoke-Item -LiteralPath (Join-Path $snapshot.FullName 'hwp-tables-v1\tables.html')
```

기본 브라우저로 표 구조를 볼 수 있다. 원본 글꼴·열 너비·페이지 배치를 재현한 것이 아니라 행·열·병합과 텍스트를 확인하는 화면이다. 중첩 표는 부모 셀의 '포함 표' 링크로 연결한다. 회색 셀은 내용이 비어 있는 셀이다. 빈 신청란에 값을 만들어 넣지 않았다.

## 실제 파일 시험 결과

프로젝트 처리 파일을 덮어쓰지 않고 원본을 읽어 임시 폴더에서 시험했다.

| 항목 | 수치 |
|---|---:|
| 표 | 11 |
| 셀 | 193 |
| 텍스트·중첩 표가 모두 없는 빈 셀 | 88 |
| rowspan 또는 colspan이 2 이상인 셀 | 45 |
| 표의 셀과 연결한 기존 텍스트 문단 | 123 |
| 표 밖의 기존 텍스트 문단 | 8 |

총 131개 기존 문단을 보존했다. 이전 1차 검토에서 독립 도구로 만든 대조 자료와 193개 셀의 행·열·병합 범위·셀 텍스트를 비교해 모두 일치함을 확인했다. 이번 구현은 그 대조 JSON을 복사하는 방식이 아니라 원본 HWP 레코드를 직접 읽는다. 대조 자료가 없는 팀원 환경에서도 실행할 수 있다.

각 표의 격자에 빈 영역이나 중복 점유가 없는지, 선언한 문단 수와 실제 문단 수가 같은지, 셀 텍스트와 기존 blocks의 문단이 정확히 같은지 확인한다. 예상하지 않은 셀·캡션·컨트롤 구조는 추정해서 이어 붙이지 않고 보류한다.

## 팀원이 사용할 데이터 규격

- `tables.json`의 `source_sha256`과 `source_snapshot`으로 원본 버전을 식별한다. `coordinate_base=0`이며 `row`, `column`은 0부터 센다.
- 각 표는 `table_id`, `rows`, `columns`, `locator`, `parent_cell_id`, `cells`를 가진다. `locator`는 HWP 구역·레코드 위치이지 페이지 번호가 아니다.
- 셀은 `cell_id`, `row`, `column`, `rowspan`, `colspan`, `paragraphs`, `text`, `nested_table_ids`를 가진다. `is_text_blank`와 `is_blank`는 다르다. 글자는 없어도 내부 표가 들어 있으면 빈 셀이 아니다.
- `parent_cell_id`와 부모 셀의 `nested_table_ids`로 중첩 관계를 유지한다. 내부 표의 문장을 부모 셀 텍스트에 중복 복사하지 않는다.
- `blocks_with_tables.json`은 기존 문단·순서를 보존하고 연결 ID만 추가한다. 표 밖 문단의 ID는 null이다. 이것은 아직 검색 청크가 아니다.
- `validation.json`의 해시는 실제 출력 파일 바이트를 기준으로 한다. 표 ID는 이 원본 버전 안에서 안정적이며, 원본이 바뀌면 위치·순서도 달라질 수 있다.

물리적인 셀 구조 복원이지, 어떤 셀이 질문·답변·열 머리글인지 의미를 자동 확정한 결과가 아니다. 예를 들어 이름·연락처 입력란은 신청자의 실제 정보가 아니다. 서식의 자격·의무·현행성도 별도 검토가 필요하다. 기존 index_approved=false를 유지하고 새 결과도 검색 승인 전으로 표시한다.

## 테스트 및 GitHub 공유

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_restore_tables_one.py" -v
```

합성 테스트 9개가 통과했다. 병합·빈 셀, 격자 중복·누락·범위 초과, 중첩 후 부모 셀 복귀, 문단 수 불일치, 예상하지 않은 구조, 연결 누락·변조, HTML 이스케이프, 기존 결과 보존과 재실행을 확인한다. 실제 공식 서식이나 FAQ 문답은 테스트 파일에 포함하지 않았다.

코드·테스트·실행 안내를 GitHub에 공유한다. 결과는 기존 data/processed 제외 규칙을 따르며 저장소에 포함하지 않는다. 구현은 [한컴 공개 HWP 형식 규격](https://cdn.hancom.com/link/docs/%ED%95%9C%EA%B8%80%EB%AC%B8%EC%84%9C%ED%8C%8C%EC%9D%BC%ED%98%95%EC%8B%9D_5.0_revision1.3.pdf)의 표·셀 속성과 실제 원본 레코드를 확인해 작성했다. 독립 검토용 도구 소스를 복사하거나 프로젝트 의존성에 추가하지 않았다.

다음에는 생성된 표 화면을 원문과 대조한 뒤 다른 HWP 문서로 확대 여부를 판단한다. OCR·도면 보완, 날짜·현행성 검토, 청크화·색인은 이번 단계에 포함하지 않는다.


## 2026-09-28 후속 단계

사용자가 표 화면 대조 후 문제를 발견하지 못했다고 보고했다. 위 내용은 최초 시범 단계 기록이다. 현재 공통 함수는 여러 HWP 구역도 지원하며, 이 파일의 단독 실행 대상은 계속 YGPA-021이다. 나머지 10건 실행 방법, 2건의 보류 사항, 사용자 확인 범위는 [나머지 HWP 표 복원](08_restore_tables_remaining.md)을 따른다. 검색 승인 상태는 변경하지 않는다.
