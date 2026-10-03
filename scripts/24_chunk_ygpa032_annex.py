"""YGPA-032(여수광양항만공사 사용료 규정) PDF 11~23쪽 별표를 쪽 단위 청크로 만든다. 네트워크를 쓰지 않는다.

15번은 이 범위를 '표·도면·한시 요율 검토 전'으로 보류했다(semantic-attachments-v1 manifest의 pdf_appendix).
요율은 해수부 고시와 비교해 확인했고(선박입출항료 135원/톤 등), 한시 감면("2024년 12월 31일까지")은 기한이
지났을 수 있어 review_flags에 남기고 답변 단계(app/prompt.py)에서 기한 지난 날짜를 짚는다.
기존 청크는 건드리지 않고 같은 스냅샷 아래 pdf-annex-v1 폴더를 따로 만든다.

  python scripts/24_chunk_ygpa032_annex.py
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ID = "YGPA-032"
VERSION = "pdf-annex-v1"
STRUCTURE = "text-corrected-v1"
# 쪽 → 별표 이름 (원문 머리글 기준: 11쪽 【별표 1】 1.사용료의 종류 및 요율, 15쪽 2.산정기준, 19쪽 【별표 2】)
SECTIONS = [
    (range(11, 15), "【별표 1】 항만시설사용료의 종류·요율"),
    (range(15, 19), "【별표 1】 항만시설사용료의 산정기준"),
    (range(19, 24), "【별표 2】 항만시설사용료별 감면율 및 감면대상"),
]
TIME_LIMITED = re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일\s*까지")


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def tidy(text: str) -> str:
    """PDF 배치용 공백을 줄인다. 칸 사이(공백 3개 이상)는 두 칸으로 남겨 표의 열 구분을 유지한다"""
    lines = [re.sub(r" {3,}", "  ", line.rstrip()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def build(root: Path) -> tuple[list[dict], dict]:
    base_dir = sorted((root / "data/chunks" / DOC_ID).glob("*/semantic-attachments-v1"))[-1]
    base = json.loads((base_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()[0])
    snap = base["source_snapshot"]
    blocks_path = f"data/processed/{DOC_ID}/{snap}/{STRUCTURE}/blocks.json"
    blocks_bytes = (root / blocks_path).read_bytes()
    blocks = json.loads(blocks_bytes)

    keep = ("doc_id", "document_version", "source_snapshot", "extraction_version", "text_sha256", "title",
            "source_url", "parent_source_url", "publisher", "fetched_at", "published_at", "updated_at",
            "date_status", "date_evidence")
    chunks = []
    for pages, section in SECTIONS:
        for page in pages:
            index, block = next((i, b) for i, b in enumerate(blocks) if b["locator"].get("page_number") == page)
            text = f"{section} ({page}쪽)\n{tidy(block['text'])}"
            flags = ["currentness_not_verified"] + (["time_limited_items"] if TIME_LIMITED.search(text) else [])
            chunks.append({
                **{k: base[k] for k in keep},
                "chunk_id": f"{DOC_ID}-" + sha(f"{VERSION}|{page}")[:24],
                "chunking_version": VERSION, "structure_version": STRUCTURE,
                "section_titles": [section], "text": text, "chunk_text_sha256": sha(text), "chunk_kind": "table",
                "source_locator": {"kind": "attachment_composite", "source_refs": [{
                    "path": blocks_path, "block_index": index, "locator": block["locator"],
                    "char_start": 0, "char_end": len(block["text"]), "offset_unit": "unicode_codepoint", "end_exclusive": True,
                }], "table_ids": []},
                "review_status": "draft_pending_chunk_review", "index_approved": False, "review_flags": flags,
            })
    manifest = dict(doc_id=DOC_ID, source_snapshot=snap, document_version=base["document_version"],
                    chunking_version=VERSION, input_hashes={blocks_path: sha(blocks_bytes)},
                    covers="semantic-attachments-v1 manifest의 pdf_appendix(보류) 범위, PDF 11~23쪽",
                    chunk_count=len(chunks), index_approved=False)
    return chunks, manifest


def save(root: Path, chunks: list[dict], manifest: dict) -> str:
    lines = [f"# {DOC_ID} 별표 청크 검토 ({VERSION})", "검색 승인 전 초안. 한시 감면(…까지)은 기한이 지났을 수 있다."]
    for c in chunks:
        lines += [f"## {c['section_titles'][0]} · {c['source_locator']['source_refs'][0]['locator']['page_number']}쪽", c["text"]]
    outputs = {"chunks.jsonl": "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks),
               "review.md": "\n\n".join(lines) + "\n"}
    expected = {**manifest, "output_hashes": {k: sha(v) for k, v in outputs.items()}}
    out = root / "data/chunks" / DOC_ID / manifest["source_snapshot"] / VERSION
    if (out / "manifest.json").exists():
        old = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        if all(old.get(k) == v for k, v in expected.items()):
            return "그대로"
        raise ValueError(f"{out}의 기존 청크와 다릅니다. 덮어쓰지 않습니다")
    out.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        (out / name).write_text(text, encoding="utf-8")
    created = {**expected, "created_at": datetime.now(timezone.utc).isoformat()}
    (out / "manifest.json").write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
    return "생성"


if __name__ == "__main__":
    chunks, manifest = build(ROOT)
    status = save(ROOT, chunks, manifest)
    limited = sum("time_limited_items" in c["review_flags"] for c in chunks)
    print(f"{DOC_ID} 별표 {len(chunks)}개 청크 (한시 조항 포함 {limited}개), 최대 {max(len(c['text']) for c in chunks)}자 | {status}")
