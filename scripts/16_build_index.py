"""개발용 BGE-M3 dense 색인 생성. 승인 전 청크를 포함하므로 로컬 실험 전용이며 배포하지 않는다.

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
    args = ap.parse_args()

    policy = json.loads((ROOT / "docs/contracts/data_separation_policy.json").read_text(encoding="utf-8"))
    chunks, excluded = dense.select(dense.load_chunks(ROOT), policy)
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
        "purpose": "개발용 로컬 실험 — 승인 전(index_approved=false) 청크 포함, 배포 금지",
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
