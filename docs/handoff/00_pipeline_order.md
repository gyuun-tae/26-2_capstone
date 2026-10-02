# 데이터 처리 실행 순서와 설명 문서

번호는 작업을 이해하는 순서입니다. 완료한 원본 수집·추출을 전부 재실행하라는 뜻은 아닙니다. 모든 명령은 프로젝트 루트에서 실행합니다.

| 순서 | 작업 | Python | 설명 |
|---|---|---|---|
| 01 | HTML 첫 문서 수집 | [실행 파일](../../scripts/01_collect_one.py) | [01_collect_one.md](01_collect_one.md) |
| 02 | HTML 첫 문서 본문 추출 | [실행 파일](../../scripts/02_extract_one.py) | [02_extract_one.md](02_extract_one.md) |
| 03 | 나머지 HTML 수집 | [실행 파일](../../scripts/03_collect_remaining.py) | [03_collect_remaining.md](03_collect_remaining.md) |
| 04 | 나머지 HTML 본문 추출 | [실행 파일](../../scripts/04_extract_remaining.py) | [04_extract_remaining.md](04_extract_remaining.md) |
| 05 | 첨부 원본 수집 | [실행 파일](../../scripts/05_collect_attachments.py) | [05_collect_attachments.md](05_collect_attachments.md) |
| 06 | 첨부 본문 추출 | [실행 파일](../../scripts/06_extract_attachments.py) | [06_extract_attachments.md](06_extract_attachments.md) |
| 07 | HWP 표 복원 시범 | [실행 파일](../../scripts/07_restore_tables_one.py) | [07_restore_tables_one.md](07_restore_tables_one.md) |
| 08 | HWP 표 복원 확대 | [실행 파일](../../scripts/08_restore_tables_remaining.py) | [08_restore_tables_remaining.md](08_restore_tables_remaining.md) |
| 09 | HWP 도형 보존 | [실행 파일](../../scripts/09_restore_graphics_030.py) | [09_restore_graphics_030.md](09_restore_graphics_030.md) |
| 10 | PDF 도면 페이지 보존 | [실행 파일](../../scripts/10_preserve_pdf_pages_031.py) | [10_preserve_pdf_pages_031.md](10_preserve_pdf_pages_031.md) |
| 11 | PDF 특수문자 보정 | [실행 파일](../../scripts/11_correct_symbols_032.py) | [11_correct_symbols_032.md](11_correct_symbols_032.md) |
| 12 | 첫 의미 청크 생성 | [실행 파일](../../scripts/12_chunk_one.py) | [12_chunk_one.md](12_chunk_one.md) |
| 13 | HTML 설명 청킹 | [실행 파일](../../scripts/13_chunk_remaining.py) | [13_chunk_remaining.md](13_chunk_remaining.md) |
| 14 | HTML 표 청킹 | [실행 파일](../../scripts/14_chunk_html_tables.py) | [14_chunk_html_tables.md](14_chunk_html_tables.md) |
| 15 | 첨부 조문·서식 청킹 | [실행 파일](../../scripts/15_chunk_attachments.py) | [15_chunk_attachments.md](15_chunk_attachments.md) |
| 16 | 개발용 dense 색인 (BGE-M3) | [실행 파일](../../scripts/16_build_index.py) | [16_build_index.md](16_build_index.md) |
| 17 | 개발용 검색 기준선 측정 | [실행 파일](../../scripts/17_search_eval.py) | [17_search_eval.md](17_search_eval.md) |
| 18 | 색인을 Neon pgvector에 넣기·검증 | [실행 파일](../../scripts/18_load_pgvector.py) | [18_load_pgvector.md](18_load_pgvector.md) |
| 19 | "확인 불가" 조기 판단 기준 측정 | [실행 파일](../../scripts/19_unknown_threshold.py) | [19_unknown_threshold.md](19_unknown_threshold.md) |
| 20 | 개발용 질문 묶음으로 실제 RAG 측정 | [실행 파일](../../src/api/eval_dev.py) | [20_dev_eval.md](20_dev_eval.md) |

08의 겹친 글자 후속 검토는 [보충 문서](08_restore_tables_remaining_controls.md)를 참고합니다. 테스트 파일은 unittest 발견 규칙인 `test_*.py`를 유지합니다. 숫자로 시작하는 실행 파일은 일반 import 문법에 맞지 않으므로 코드 내부는 명시적 `__import__`로 연결합니다. 처리 버전·청크 ID·출력 경로·원본 데이터는 바꾸지 않았습니다.

`chunking_001.md`, `chunking_attachments.md`는 미병합 API와 기존 링크용 이동 안내만 남겼습니다. 실제 설명은 번호 문서에만 있습니다.
