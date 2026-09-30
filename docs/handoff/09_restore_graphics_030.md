# YGPA-030 표와 그리기 개체 보존

대응 실행 파일: `scripts/09_restore_graphics_030.py`. 작업 번호와 기본 이름을 동일하게 맞췄습니다.

2026-09-28. 이 단계는 누락 없이 자료를 보존하는 단계다. 원본 지도 위의 선·도형·글상자 합성 화면을 재현한 것은 아니며, 시각 배치와 의미 검토는 보류한다.

## 사용자 실행

```powershell
Set-Location -LiteralPath "C:\Users\yountae\26-2_classes\capstone"
.\.venv\Scripts\python.exe -B .\scripts\09_restore_graphics_030.py --restore
```

옵션 없이 실행하면 준비 안내만 출력한다. 앞 단계의 requirements-extraction.txt 환경을 사용하고 네트워크 요청이나 새 패키지 설치는 하지 않는다. 기존 배치 08_restore_tables_remaining.py의 YGPA-030 처리는 여전히 보류하며, 이 문서의 전용 진입점으로 실행한다.

예상 결과는 표 3개, 셀 58개, 묶인 그리기 개체 1개, 내부 레코드 35개, 그림 1개, 내부 문단 2개다. 결과는 `data/processed/YGPA-030/20260927T070445774628Z/hwp-graphics-v1/`에 저장한다. 원본과 기존 본문·메타데이터·문단 파일 및 다른 복원 결과는 보존한다. 같은 원본과 같은 결과는 건너뛰고 손상되거나 다른 기존 결과는 덮어쓰지 않는다.

## 검토 화면

```powershell
Invoke-Item -LiteralPath "C:\Users\yountae\26-2_classes\capstone\data\processed\YGPA-030\20260927T070445774628Z\hwp-graphics-v1\tables.html"
```

두 번째 표에 있는 ‘그림·도형·글상자 보기’를 누르면 graphics.html로 이동한다. 내장 지도 이미지와 별도의 ‘통과선박’, ‘정박지’ 문단, 보존한 구성 목록을 확인한다. 그림은 원본 파일의 내장 JPEG를 압축 해제한 것이며 선·도형·글상자를 합성한 화면이 아니다. 내장 이미지 자체에 인쇄된 글자와 별도 HWP 글상자를 구별해야 한다. 이 화면을 근거로 위치·경계를 판단하지 않는다.

## 팀원이 사용할 파일과 상태

- tables.json: 표·셀 좌표, 병합, 일반 문단, graphic_objects. 개체가 들어 있는 셀을 빈칸으로 취급하지 않는다.
- graphics.json: 개체의 소속 table_id/cell_id, 원본 및 부모 문단 locator, 레코드 계층과 원본 바이트, 내부 text_records, 그림 참조, 이미지 출처·해시.
- blocks_with_tables.json: 기존 문단 순서·텍스트 보존, table_id/cell_id와 graphic_object_id 연결. 개체 안의 두 문단을 일반 셀 text로 중복 복사하지 않는다.
- image-001.jpg: 내장 지도 이미지. 압축된 원본 스트림 해시와 압축 해제한 이미지 해시를 assets에 모두 기록한다.
- tables.html, graphics.html: 사람이 보는 구조·자료 검토 화면.
- validation.json: 입력·출력 해시, 검증 수치, visual_layout_status=not_rendered_pending_review 및 index_approved=false.

셀의 graphic_objects와 graphics.json.objects는 동일한 object_id로 같은 개체를 표현한다. 둘을 합쳐 중복 색인하지 않는다. 레코드의 level_parent_record는 HWP 레벨 구조에 따른 상위 레코드 번호다. 좌표·변환·서식의 의미를 새로 추정한 필드가 아니다. raw_record_hex는 헤더를 포함한 레코드 전체 바이트이고 payload_hex는 그 내용만이다. 내부 문단의 기록 순서는 시각적 읽기 순서와 구분한다.

그림 연결은 그림 속성의 BinItem 참조 → DocInfo 항목 → BinData 저장 ID 순서로 검증한다. 임의의 첫 이미지를 연결하지 않는다. 외부 링크 그림은 접근하지 않으며, 지원하지 않는 형식이나 불일치가 발견되면 보류한다. JPEG/PNG 시그니처 및 압축 스트림을 확인한다.

## 검증 결과와 제한

실제 원본을 읽고 임시 폴더에서 저장·재실행·변조 탐지 검증을 수행했다. 이번 안내는 실행 준비 기록이며 사용자 실행 완료 기록은 별도다.

- 표 3개·셀 58개의 좌표·병합·일반 텍스트가 기존 독립 대조 자료와 일치한다.
- Section0의 레코드 366~400, 총 35개가 원본의 연속 바이트 구간과 정확히 일치한다. 여기에는 개체 구성 15개, 선 6개, 사각형 2개, 타원 1개, 그림 1개의 레코드가 포함된다. 이 수치는 최상위 개체 수가 아니다.
- 그림 파일 바이트가 원본 BinData/BIN0001.jpg 압축 해제 결과와 동일하다. 내부 문단 2개는 기존 blocks의 위치·글자와 정확히 일치한다. 총 66개 문단이 셀에 연결된다.
- 합성 테스트 23개 통과. 개체 원본 바이트, 부모 셀 복귀, 문단 누락 검출, BinItem 참조 선택, 외부 링크·잘린 항목·이미지 시그니처 거부, HTML 이스케이프, 저장·재실행·변조 탐지를 확인했다.
- 지도에 포함된 글자 OCR, 도형 합성, 위치 관계 판독은 하지 않았다. 원본 지면 대조와 문서 날짜·현행성 검토는 미완료다.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_restore*.py" -v
```

구조 해석은 [한컴 공개 HWP 5.0 revision 1.2](https://cdn.hancom.com/link/docs/%ED%95%9C%EA%B8%80%EB%AC%B8%EC%84%9C%ED%8C%8C%EC%9D%BC%ED%98%95%EC%8B%9D_5.0_revision1.2.pdf)의 레코드 계층, 표 17·18(BinData), 표 32(그림 정보), 표 107(그림 속성)을 기준으로 한다. 공개 규격을 넘어 도형 배치를 추정하지 않았다.

## 이전 단계 사용자 확인

YGPA-033의 hwp-tables-v2 화면 확인 안내 후 사용자가 2026-09-28 ‘확인완료’라고 응답했다. 이 기록은 해당 화면·원문 대조 완료를 뜻하며, 검색 승인이나 문서 현행성 승인으로 확대하지 않는다.

- YGPA-033 snapshot: 20260927T070449680617Z
- 원본 SHA-256: f31e725f0692e6e7d8138fba0b8ca2b19223faf793faf5eede38d88a8db30c71
- 확인 화면 SHA-256: 80b9a78709c6b3c332a7ea17106b23816dfb647d871c11d175ad3aaea42d26c1

## GitHub와 다음 단계

실행 코드·합성 테스트·인수인계 문서를 공유한다. 원본·이미지·생성 결과는 data/raw 및 data/processed 기존 제외 규칙을 따른다. FAQ, 청크화, 검색 등록은 이번 단계에서 다루지 않는다. 다음 단계는 이 보존 결과 확인 후 원본 지도 지면의 시각적 대조/재현 방법을 정하는 것이다. 자료 보존 완료와 시각 복원 완료를 구분한다.

## 사용자 실행 및 확인 완료

2026-09-28 사용자 실행 결과에서 표 3개·셀 58개·그림 1개·개체 내부 문단 2개 저장을 확인하고, 출력 및 기존 본문·문단 해시를 검증했다. 이후 사용자가 검토 화면의 자료 표시와 연결을 확인했다. 도형의 원본 배치 재현 상태는 계속 not_rendered_pending_review다. 전체 후속 현황은 [체크포인트](dataset_checkpoint_20260928.md)를 따른다.
