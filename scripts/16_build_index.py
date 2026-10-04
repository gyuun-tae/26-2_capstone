"""BGE-M3 dense 색인 생성.

기본은 개발용(승인 전 청크 포함). --approved-only면 승인 기록(data/catalog/index_approvals.json, 26번)에서
승인된 청크만 넣는 서비스용 색인을 만든다 (docs/contracts/index_approval_policy.md).

실행: .\\.venv\\Scripts\\python.exe -B .\\scripts\\16_build_index.py
결과: data/index/<색인 버전>/vectors.npy, chunks.jsonl, manifest.json (Git 제외)
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag import dense  # noqa: E402


def load_model(revision=None):
    """모델 파일의 정확한 revision(커밋)을 기록해 질의 때도 같은 모델을 쓰게 한다."""
    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer

    # ONNX 사본·이미지는 쓰지 않으므로 받지 않는다 (약 2.3GB 절약)
    path = Path(snapshot_download(dense.MODEL_ID, revision=revision, ignore_patterns=["onnx/*", "imgs/*"]))
    model = SentenceTransformer(str(path), device="cpu")
    model.max_seq_length = dense.MAX_TOKENS
    return model, path.name


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--revision", help="BGE-M3 커밋. 없으면 최신을 받고 실제 커밋을 기록")
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--approved-only", action="store_true", help="승인 기록에서 승인된 청크만 (서비스용)")
    args = ap.parse_args()

    policy = json.loads((ROOT / "docs/contracts/data_separation_policy.json").read_text(encoding="utf-8"))
    chunks, excluded = dense.select(dense.load_chunks(ROOT), policy)
    ledger = None
    if args.approved_only:
        ledger = json.loads((ROOT / dense.APPROVAL_LEDGER).read_text(encoding="utf-8"))
        reviewed = dense.apply_approvals(chunks, ledger)
        held = [c for c in reviewed if not c["index_approved"]]
        for c in held:
            excluded[f"not_approved:{c['review_status']}"] = excluded.get(f"not_approved:{c['review_status']}", 0) + 1
        chunks = [c for c in reviewed if c["index_approved"]]
        if held:
            print(f"승인 안 된 청크 {len(held)}개 제외: {sorted({c['doc_id'] for c in held})[:10]}")
    model, revision = load_model(args.revision)
    print(f"청크 {len(chunks)}개 색인 (제외: {excluded}), 모델 {dense.MODEL_ID}@{revision[:12]}")

    vectors, tokens = dense.build(
        chunks,
        encode=lambda texts: model.encode(texts, batch_size=args.batch_size, show_progress_bar=True),
        count_tokens=lambda text: len(model.tokenizer(text)["input_ids"]),
    )
    version = dense.index_version(revision, chunks)
    manifest = {
        "index_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": ("서비스용 — 승인된 청크만" if ledger else "개발용 로컬 실험 — 승인 전(index_approved=false) 청크 포함"),
        "approval": ({"ledger": dense.APPROVAL_LEDGER, "policy_version": ledger["policy_version"],
                      "checked_at": ledger["checked_at"]} if ledger else None),
        "model_id": dense.MODEL_ID,
        "model_revision": revision,
        "dimension": int(vectors.shape[1]),
        "normalized": True,
        "similarity": "cosine",
        "input_format": dense.INPUT_FORMAT,
        "max_tokens": dense.MAX_TOKENS,
        "tokens": {"max": max(tokens), "mean": round(sum(tokens) / len(tokens), 1)},
        "chunk_count": len(chunks),
        "excluded": excluded,
        "approved_count": sum(bool(c.get("index_approved")) for c in chunks),
        "chunks": [{"chunk_id": c["chunk_id"], "chunk_text_sha256": c["chunk_text_sha256"]} for c in chunks],
    }
    folder = ROOT / "data/index" / version
    dense.save(folder, vectors, chunks, manifest)
    print(f"저장: {folder.relative_to(ROOT)} | 벡터 {vectors.shape} | 토큰 최대 {max(tokens)}·평균 {manifest['tokens']['mean']}")


if __name__ == "__main__":
    main()
