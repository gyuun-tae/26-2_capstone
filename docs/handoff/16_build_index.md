# 16. 개발용 dense 색인 (BGE-M3)

청크를 BGE-M3로 벡터로 바꿔 검색용 색인을 만든다. **승인 전(`index_approved=false`) 청크를 포함한 개발용 로컬 실험**이며 배포하지 않는다. 운영 색인은 승인 목록 확정 후 별도로 만든다.

## 실행

```powershell
uv venv --python 3.12 .venv            # 또는 py -3.12 -m venv .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-index.txt
.\.venv\Scripts\python.exe -B .\scripts\16_build_index.py
```

- 처음 실행 때 BGE-M3 모델 파일을 내려받는다 (ONNX 사본·이미지 제외, 약 2.3GB). `--revision <커밋>`으로 모델 버전을 고정할 수 있다.
- 결과: `data/index/<색인 버전>/` — `vectors.npy`(정규화된 벡터), `chunks.jsonl`(색인한 청크 그대로, 벡터와 같은 순서), `manifest.json`. `data/index/`는 Git 제외.
- 재사용 함수는 `src/rag/dense.py`. 테스트: `python -B -m unittest tests.test_dense_index` (합성 청크·가짜 임베딩, 모델 불필요).

## 무엇을 색인하는가

| 규칙 | 내용 |
|---|---|
| 대상 | `data/chunks/*/*/*/chunks.jsonl` 전체 (설명·표·첨부 버전을 모두 읽음. 마지막 버전만 고르지 않음) |
| 제외 | 과거 부칙(`chunk_kind=historical_addendum`) — 현재 안내 검색에서 기본 제외 |
| 차단 | `docs/contracts/data_separation_policy.json`의 FAQ 경로·`bbs_no=230` 출처가 있으면 색인하지 않고 멈춤 |
| 입력 형식 | `제목 \n 절 제목(' > '로 연결) \n\n 본문` — 문서와 질의에 같은 모델·설정 |
| 길이 검사 | BGE-M3 토크나이저로 센 토큰이 8,192를 넘으면 **자르지 않고 멈춤** (하위 청크 버전이 필요하다는 뜻) |
| 정규화 | 벡터 길이 1로 정규화 → 내적 = 코사인 유사도 |
| 색인 버전 | 모델 revision + 청크 ID·본문 해시로 이름을 만들어 다른 모델·데이터의 벡터가 섞이지 않게 함 |

## 2026-10-02 실행 결과 (로컬 CPU)

| 항목 | 값 |
|---|---|
| 색인 버전 | `bge-m3-dense-d67237d5942d` |
| 모델 | `BAAI/bge-m3` @ `5617a9f61b028005a4858fdac845db406aefb181` |
| 청크 | 145개 색인 (전체 178 − 과거 부칙 33), 승인 0개(개발용) |
| 벡터 | 145 × 1024, `vectors_sha256` `2170e77c…` |
| 토큰 | 최대 3,686 · 평균 382.8 → 8,192 초과 0개, 하위 청크 불필요 |
| 시간 | Intel Core Ultra 7 155H CPU, 인코딩 약 3분 50초 |

실행 전 `data/chunks`의 manifest 출력 해시 106개, 청크 본문 해시 178개를 대조해 불일치 0, 중복 ID 0을 확인했다.

## 운영으로 옮길 때

- 질의도 같은 모델(같은 revision)로 벡터화해야 한다. 실행 방식 B(Render + GPU 서버)에서는 GPU 서버가 임베딩을 맡는다.
- 저장소는 제안서 4.5절(Neon PostgreSQL + pgvector)로 옮긴다 → [18번](18_load_pgvector.md)이 이 폴더의 `chunks.jsonl`·`vectors.npy`를 그대로 넣는다.
- 승인 목록이 확정되면 승인된 청크만으로 새 색인 버전을 만든다.
