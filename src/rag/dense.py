"""BGE-M3 dense 색인·검색 (MVP 1단계, 개발용).

모델 호출(encode, 토큰 세기)은 바깥에서 넘겨받는다. 테스트는 가짜 함수로, 나중에는 GPU 서버 호출로 바꿀 수 있다.
검색 결과 형식은 docs/contracts/rag_interface_proposal.md 1절: {"chunk": 청크 그대로, "score": 유사도}.
"""
import hashlib
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

MODEL_ID = "BAAI/bge-m3"
MAX_TOKENS = 8192  # BGE-M3 모델 카드의 최대 입력 길이. 넘으면 자르지 않고 멈춘다
EXCLUDED_KINDS = {"historical_addendum"}  # 과거 부칙은 현재 안내 검색에서 기본 제외 (등록 계획)
# 같은 내용을 더 자세히 담은 새 수집본이 있는 문서 → 대체 문서. 옛 페이지(단계 이름만 나열)가 1위로 올라와
# 상세 표(기한·근거)를 가린다 (docs/handoff/25_org_hinterland.md)
SUPERSEDED = {"YGPA-019": "YGPA-039", "YGPA-020": "YGPA-039"}
APPROVAL_LEDGER = "data/catalog/index_approvals.json"  # scripts/26_review_index_approval.py
APPROVAL_VALID_DAYS = 30  # docs/contracts/index_approval_policy.md 유효 기간
APPROVED = {"approved", "approved_with_notes"}
INPUT_FORMAT = "{title}\\n{section_titles joined by ' > '}\\n\\n{text}"


def load_chunks(root: Path) -> list[dict]:
    rows = [json.loads(line) for f in sorted(root.glob("data/chunks/*/*/*/chunks.jsonl"))
            for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sorted(rows, key=lambda r: (r["doc_id"], r["chunk_id"]))


def is_blocked(url: str, policy: dict) -> bool:
    """FAQ 등 평가 전용 출처인지 (docs/contracts/data_separation_policy.json 기준)"""
    u = urlparse(url)
    if any(u.path.startswith(p) for p in policy.get("blocked_path_prefixes", [])):
        return True
    query = parse_qs(u.query)
    return any(v in query.get(k, []) for k, values in policy.get("blocked_query_values", {}).items() for v in values)


def apply_approvals(chunks: list[dict], ledger: dict, now: datetime | None = None) -> list[dict]:
    """승인 기록을 청크에 반영한 사본. 기록의 본문 해시와 다르면(다시 수집·청킹됨) 승인하지 않는다.
    승인 기록이 유효 기간을 넘었으면 멈춘다"""
    checked = datetime.fromisoformat(ledger["checked_at"])
    age = (now or datetime.now(timezone.utc)) - checked
    if age > timedelta(days=APPROVAL_VALID_DAYS):
        raise ValueError(f"승인 기록이 {age.days}일 지났습니다 (유효 {APPROVAL_VALID_DAYS}일). 26번을 다시 실행하세요")
    out = []
    for c in chunks:
        d = ledger["chunks"].get(c["chunk_id"])
        ok = bool(d) and d["status"] in APPROVED and d["chunk_text_sha256"] == c["chunk_text_sha256"]
        status = d["status"] if ok else ("stale_approval" if d else "not_reviewed")
        out.append({**c, "index_approved": ok, "review_status": status,
                    "approval": {"policy_version": ledger["policy_version"], "checked_at": ledger["checked_at"],
                                 "notes": d["notes"] if d else []}})
    return out


def select(chunks: list[dict], policy: dict) -> tuple[list[dict], dict]:
    """색인할 청크와 제외 기록. 평가 전용 출처가 섞여 있으면 색인하지 않고 멈춘다."""
    blocked = [c["chunk_id"] for c in chunks if is_blocked(c["source_url"], policy)]
    if blocked:
        raise ValueError(f"평가 전용 출처가 청크에 있습니다: {blocked[:5]}")
    kept = [c for c in chunks if c.get("chunk_kind") not in EXCLUDED_KINDS and c["doc_id"] not in SUPERSEDED]
    excluded: dict[str, int] = {}
    for c in chunks:
        if c.get("chunk_kind") in EXCLUDED_KINDS:
            excluded[c["chunk_kind"]] = excluded.get(c["chunk_kind"], 0) + 1
        elif c["doc_id"] in SUPERSEDED:
            key = f"superseded:{c['doc_id']}->{SUPERSEDED[c['doc_id']]}"
            excluded[key] = excluded.get(key, 0) + 1
    return kept, excluded


def input_text(chunk: dict) -> str:
    """임베딩에 넣을 글: 제목 + 절 제목 + 본문. 문서와 질의에 같은 모델·설정을 쓴다."""
    return f"{chunk['title']}\n{' > '.join(chunk.get('section_titles') or [])}\n\n{chunk['text']}"


def build(chunks: list[dict], encode, count_tokens) -> tuple[np.ndarray, list[int]]:
    """청크 → 정규화된 벡터. 토큰 한도를 넘는 청크가 있으면 자르지 않고 멈춘다."""
    texts = [input_text(c) for c in chunks]
    tokens = [count_tokens(t) for t in texts]
    over = [(c["chunk_id"], n) for c, n in zip(chunks, tokens) if n > MAX_TOKENS]
    if over:
        raise ValueError(f"토큰 한도 {MAX_TOKENS} 초과 청크 (하위 청크 버전이 필요): {over}")
    vectors = np.asarray(encode(texts), dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True), tokens


def search(query_vector, vectors: np.ndarray, chunks: list[dict], k: int = 5) -> list[dict]:
    """코사인 유사도 상위 k개. 청크는 가공하지 않고 그대로 돌려준다.
    ponytail: 전체 비교(청크 수백 개). 운영은 pgvector 검색으로 바꾼다 (제안서 4.5절)"""
    q = np.asarray(query_vector, dtype=np.float32)
    scores = vectors @ (q / np.linalg.norm(q))
    top = np.argsort(-scores)[:k]
    return [{"chunk": chunks[i], "score": float(scores[i])} for i in top]


def index_version(model_revision: str, chunks: list[dict]) -> str:
    """모델 revision과 청크 본문 해시가 같으면 같은 이름 → 다른 모델·데이터의 벡터가 섞이지 않는다"""
    h = hashlib.sha256(model_revision.encode())
    for c in chunks:
        h.update(f"{c['chunk_id']}:{c['chunk_text_sha256']}".encode())
    return f"bge-m3-dense-{h.hexdigest()[:12]}"


def save(folder: Path, vectors: np.ndarray, chunks: list[dict], manifest: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    np.save(folder / "vectors.npy", vectors)
    (folder / "chunks.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
    manifest["vectors_sha256"] = hashlib.sha256((folder / "vectors.npy").read_bytes()).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def load(folder: Path) -> tuple[np.ndarray, list[dict], dict]:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256((folder / "vectors.npy").read_bytes()).hexdigest() != manifest["vectors_sha256"]:
        raise ValueError(f"벡터 파일 해시가 색인 기록과 다릅니다: {folder}")
    chunks = [json.loads(line) for line in (folder / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    return np.load(folder / "vectors.npy"), chunks, manifest
