# 보류 문서 후속: YGPA-033 글자 겹침 보존

2026-09-28. 배치 tables-20260928T031506597769Z에서 YGPA-022~029 8건 저장, YGPA-030·033 2건 보류를 확인했다. 저장된 8건의 출력 해시와 기존 document.txt/blocks.json 해시를 검증했다. 원문 육안 대조는 별도다.

## 이번 실행

```powershell
Set-Location -LiteralPath "C:\Users\yountae\26-2_classes\capstone"
.\.venv\Scripts\python.exe -B .\scripts\restore_tables_remaining.py --doc-ids YGPA-033 --restore
```

이 단계에서는 YGPA-033 한 건만 처리한다. 사전 검증 결과 표 5개, 셀 95개, 글자 겹침 개체 1개다. 새 패키지는 필요 없다. 저장 결과는 `data/processed/YGPA-033/20260927T070449680617Z/hwp-tables-v2/`다. v1이나 기존 본문은 덮어쓰지 않는다.

```powershell
Invoke-Item -LiteralPath "C:\Users\yountae\26-2_classes\capstone\data\processed\YGPA-033\20260927T070449680617Z\hwp-tables-v2\tables.html"
```

해당 셀의 ‘글자 겹침: ①’ 표시를 확인한다. 이 표시는 글자의 존재를 드러내는 검토 안내이며, 원본에서 문구와 겹치는 정확한 배치나 테두리를 재현한 것은 아니다.

## 원인과 데이터 규격

HWP Section0 레코드 40은 `tcps`(글자 겹침)다. [한컴 HWP 5.0 공개 규격 revision 1.2](https://cdn.hancom.com/link/docs/%ED%95%9C%EA%B8%80%EB%AC%B8%EC%84%9C%ED%8C%8C%EC%9D%BC%ED%98%95%EC%8B%9D_5.0_revision1.2.pdf)의 4.3.10.12, 표 144에 따라 글자 길이, UTF-16LE 문자열, 서식 속성 배열 길이를 검증한다. 실제 문자열은 ①이다.

이 개체는 일반 문단 텍스트 레코드와 별도로 저장되어 있어 이전 document.txt와 독립 대조용 문단 추출에서는 빠져 있었다. 이번 결과는 기존 본문을 수정하지 않고, 셀의 `inline_controls`에 글자·원본 payload·개체 및 부모 문단 위치·서식 속성을 보존한다. 개체가 있는 칸을 빈칸으로 표시하지 않는다.

- YGPA-033의 결과 버전은 hwp-tables-v2다. 다른 문서의 v1 결과를 유지한다.
- `inline_controls[].text`는 겹칠 글자 원문이며 렌더링된 외형과 구분한다.
- `raw_payload_hex`로 원래 컨트롤 payload 바이트를 복원할 수 있다.
- `paragraph_locator`는 해당 셀 안에서 어느 문단 소속인지 가리킨다. 글자를 셀의 일반 text 또는 기존 blocks에 임의로 삽입하지 않는다.
- 검색 담당자는 후속 청크 설계에서 일반 셀 텍스트만 읽으면 이 글자를 놓칠 수 있음을 유의한다. 원본 문장 내 삽입 위치·표현은 아직 확정하지 않는다.
- tables.json과 validation.json에 inline_control_count=1을 기록한다. index_approved=false다.

## 검증 범위

합성 테스트 17개 통과. 새 테스트는 UTF-16 서로게이트 글자, 컨트롤 원본 바이트, 잘린 문자열·속성 배열, 셀 소속 유지, 빈칸 판정, HTML 이스케이프, 예상하지 않은 하위 레코드 보류를 확인한다.

실제 원본의 표 5개·셀 95개는 기존 독립 대조 자료의 셀 좌표·병합·일반 텍스트와 정확히 일치했다. ‘①’는 그 대조 자료에도 누락되어 있어 원본 컨트롤 payload와 공개 규격으로 별도 확인했다. 임시 폴더에서 저장·재실행·해시·기존 본문 보존을 확인했다. 이번 문서는 실행 준비 기록이며 실제 사용자 실행 완료를 뜻하지 않는다.

## YGPA-030은 계속 보류

Section0 레코드 366 아래에 그림, 선, 도형, 글상자가 묶여 있다. 내부의 ‘통과선박’, ‘정박지’ 문단과 배치 관계가 있어 단순 건너뛰기는 누락을 만든다. 이번 코드에서도 보류한다. 지도 이미지뿐 아니라 그 위의 도형과 글상자 배치를 함께 검토하는 후속 작업이 필요하다. 현재 source 원본과 기존 본문은 보존되어 있다.

## 공유

코드·합성 테스트·이 안내는 GitHub 공유 대상이다. 생성 결과·실행 로그는 기존 .gitignore의 data/processed 제외 범위다. FAQ 접근, 청크화, 검색 등록은 수행하지 않는다.


## 후속 상태 (2026-09-28)

사용자가 YGPA-033의 저장 결과 화면·원문 대조 후 ‘확인완료’라고 응답했다. 검색 승인 상태는 변경하지 않는다. YGPA-030은 [전용 자료 보존 단계](graphics_preservation_030.md)로 이어간다. 원본 개체 데이터는 보존하되 시각 배치 재현은 여전히 보류한다.
