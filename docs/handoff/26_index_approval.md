# 26 색인 승인 검토

기준: [index_approval_policy.md](../contracts/index_approval_policy.md) (v1.0, 2026-10-04 자료 담당 결정).

```bash
python scripts/26_review_index_approval.py              # 공식 출처를 다시 조회해 승인 기록 저장 (법령 API 등록 IP 필요)
python scripts/16_build_index.py --approved-only ...    # 승인된 청크만 서비스용 색인
python scripts/18_load_pgvector.py --index data/index/<버전>
python -m unittest tests/test_index_approval.py
```

- 승인은 청크 파일을 고치지 않고 `data/catalog/index_approvals.json`(Git에 올림)에 청크별 상태·본문 해시·사유로 남긴다. 다시 청킹돼 본문 해시가 달라진 청크는 승인되지 않는다(`stale_approval`).
- 승인 기록은 30일 유효. 지나면 `--approved-only`가 멈춘다 → 26번 다시 실행.
- YGPA 사이트가 연속 요청에 잠깐 빈 결과를 돌려준 적이 있어, 부서 조회는 빈 결과를 '확인 실패'로, 다르면 3초 뒤 한 번 더 확인한다.

## 첫 검토 결과 (2026-10-04)

| 상태 | 청크 |
|---|---:|
| approved | 1,182 |
| approved_with_notes | 13 (기한 있는 감면 4·예약 제한 공지 2·일정 공지 3·PDF 대조 전사 3·날짜 표시 충돌 1) |
| held | 0 |
| excluded | 35 (과거 부칙 33, YGPA-019·020 대체) |

- 현행성: YGPA 안내 페이지 22건 본문, 첨부 13건 파일 해시, 부서 22건, 법령 21건 현행 버전·시행일이 모두 수집본과 같음.
- 서비스용 색인은 승인 전과 같은 1,195청크 → 색인 이름이 같아 Render 설정 변경 없음. Neon 행의 청크에 `index_approved: true`와 승인 정보가 들어감.
