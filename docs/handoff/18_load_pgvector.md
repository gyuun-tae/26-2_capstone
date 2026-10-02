# 18. 색인을 Neon pgvector에 넣기

16번 색인(`data/index/<버전>/`)을 Neon PostgreSQL의 pgvector 테이블에 넣고, **로컬 numpy 검색과 같은 결과가 나오는지** 확인한다. 실행 방식 B에서 Render API는 이 테이블로 검색한다.

```powershell
# 저장소 루트 .env (Git 제외)에 한 줄: DATABASE_URL=postgresql://...  (Render의 DATABASE_URL과 같은 Neon 주소)
.\.venv\Scripts\python.exe -B .\scripts\18_load_pgvector.py          # 가장 최근 색인
.\.venv\Scripts\python.exe -B .\scripts\18_load_pgvector.py --index data\index\<버전>
```

- 주소는 채팅·저장소에 올리지 않는다. 스크립트도 화면에 출력하지 않는다.
- 같은 색인 버전을 다시 넣으면 그 버전만 지우고 새로 넣는다. 한 트랜잭션이라 중간에 실패하면 이전 상태가 유지된다.
- 재사용 함수는 `src/rag/pg_store.py` (`ensure_schema`, `replace_version`, `search`). 테스트: `python -B -m unittest tests.test_pg_store`.

## 테이블

| 테이블 | 열 | 설명 |
|---|---|---|
| `rag_index_versions` | `index_version` (PK), `manifest` jsonb, `loaded_at` | 색인 버전과 16번 manifest 그대로 |
| `rag_chunks` | (`index_version`, `chunk_id`) PK, `doc_id`, `embedding vector(1024)`, `chunk` jsonb | 청크 원본 그대로 + 정규화된 벡터. 버전을 지우면 함께 지워짐 |

검색: `ORDER BY embedding <=> 질의 벡터` (코사인 거리), 점수 = 1 − 거리. 청크가 수백 개라 ANN 인덱스 없이 전체 비교 → numpy 검색과 결과가 같다. 수만 개로 늘면 HNSW 인덱스를 추가한다. API는 쓸 색인 버전을 명시적으로 지정한다 (버전이 섞이지 않게).

## 검증 방법

1. 행 수와 청크 JSON이 원본과 같은지.
2. 145개 청크 벡터를 각각 질의로 써서 DB 검색과 `dense.search`의 상위 5개 순위·점수 비교 (모델 불필요). 점수 차 1e-5 이내의 동점끼리 순서가 바뀐 것은 일치로 본다.

## 2026-10-02 결과 (색인 `bge-m3-dense-d67237d5942d`)

| 항목 | 결과 |
|---|---|
| pgvector | 0.8.6 (Neon) |
| 행 수 · 청크 내용 | 145/145 · 145/145 일치 |
| 상위 5개 비교 | 145개 질의 중 불일치 0, 점수 차 최대 4.47e-07 |
| 검색 시간 | 중앙값 82ms, 최대 724ms (이 PC→Neon 왕복 포함, 첫 연결 대기 포함) |

**승인 전 청크다** (`approved_count=0`, 개발용). 테이블에 저장만 했으며 사용자에게 보이지 않는다. 운영 전에 승인된 청크만으로 새 색인 버전을 만들어 넣고 API가 그 버전을 쓰게 바꾼다.
