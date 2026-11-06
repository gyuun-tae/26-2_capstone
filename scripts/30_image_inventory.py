"""V3 이미지·도면: 수집한 이미지가 지금 검색 자료에 어떻게 들어가 있는지 집계한다 (GPU 불필요, 2026-11-06).

실행(저장소 루트): uv run --no-project --with pillow python scripts/30_image_inventory.py
결과: data/processed/image_inventory.json (이미지마다 상태), data/processed/image_inventory.csv (사람이 훑어볼 표)

상태 — 29번(scripts/29_process_site.py)과 같은 기준으로 판정한다
- repeated: 3개 이상 문서에 나오는 이미지(로고·아이콘·배너). 29번이 건너뜀
- manual: 사람이 원본과 대조해 옮긴 글(data/catalog/image_transcripts.json)
- small: 300×100 미만. OCR을 하지 않음
- ocr: OCR 글자가 품질 기준을 넘어 본문에 들어감 (원문 확인 필요 표시)
- alt: OCR은 못 쓰고 alt 설명만 들어감
- none: 검색 자료에 아무 글도 없음
- foreign: 영·일·중 페이지 이미지 (OCR은 한국어만 했다)
VLM 대상 = repeated·small·manual을 뺀 나머지. 이 목록으로 VLM 시험 이미지를 고른다.
"""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
CACHE = ROOT / "data/processed/ocr_cache.json"
TRANSCRIPTS = ROOT / "data/catalog/image_transcripts.json"
OUT = ROOT / "data/processed/image_inventory"
ALT_NOISE = re.compile(r"사진|모습|전경|바라본|이미지|미리보기|인천항|경인항")  # 29번과 같음


def good_ocr(text: str) -> bool:
    """29번 good_ocr과 같은 기준"""
    letters = [c for c in text if not c.isspace()]
    if len(letters) < 20:
        return False
    hangul = sum("가" <= c <= "힣" for c in letters)
    hanzi = sum("一" <= c <= "鿿" for c in letters)
    alnum = sum(c.isascii() and c.isalnum() for c in letters)
    return hanzi / len(letters) < 0.02 and (hangul + alnum) / len(letters) > 0.75


def latest_snapshots():
    for folder in sorted(RAW.iterdir()):
        if not folder.is_dir():
            continue
        snaps = sorted(p for p in folder.iterdir() if p.is_dir() and (p / "metadata.json").exists())
        if snaps:
            yield folder.name, snaps[-1], json.loads((snaps[-1] / "metadata.json").read_text(encoding="utf-8"))


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    manual = json.loads(TRANSCRIPTS.read_text(encoding="utf-8")) if TRANSCRIPTS.exists() else {}
    seen: dict[str, dict] = {}
    docs_of: dict[str, list[str]] = defaultdict(list)
    for doc_id, snap, meta in latest_snapshots():
        for im in meta.get("images", []):
            key = im.get("sha256")
            if not key:
                continue
            docs_of[key].append(doc_id)
            if key in seen:
                continue
            path = snap / im["file"] if im.get("file") else None
            item = {"sha256": key, "doc_id": doc_id, "title": meta.get("title", ""), "lang": meta.get("lang", "ko"),
                    "kind": meta.get("kind"), "src": im.get("src", ""), "alt": im.get("alt", ""),
                    "file": str(path.relative_to(ROOT)).replace("\\", "/") if path and path.exists() else "",
                    "bytes": path.stat().st_size if path and path.exists() else 0, "width": 0, "height": 0}
            if item["file"]:
                try:
                    with Image.open(path) as img:
                        item["width"], item["height"] = img.size
                except Exception as e:  # svg·깨진 파일
                    item["open_error"] = type(e).__name__
            seen[key] = item

    for key, item in seen.items():
        item["docs"] = sorted(set(docs_of[key]))
        read = cache.get(key, "")
        item["ocr_chars"] = len(re.sub(r"\s", "", read))
        alt_ok = len(item["alt"]) >= 15 and not ALT_NOISE.search(item["alt"])
        if len(item["docs"]) >= 3:
            state = "repeated"
        elif key in manual:
            state = "manual"
        elif item["lang"] != "ko":
            state = "foreign"
        elif not item["file"] or (item["width"] and (item["width"] < 300 or item["height"] < 100)):
            state = "small" if item["file"] else "none"
        elif good_ocr(read):
            state = "ocr"
        elif alt_ok:
            state = "alt"
        else:
            state = "none"
        item["state"] = state
        item["vlm_target"] = state in ("ocr", "alt", "none", "foreign") and bool(item["file"]) and "open_error" not in item

    items = sorted(seen.values(), key=lambda x: (not x["vlm_target"], x["state"], x["doc_id"]))
    OUT.with_suffix(".json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["state", "vlm_target", "doc_id", "title", "lang", "width", "height", "bytes", "ocr_chars", "alt", "file", "docs"]
    with OUT.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for x in items:
            w.writerow([" ".join(x[c]) if c == "docs" else x.get(c, "") for c in cols])

    states = Counter(x["state"] for x in items)
    targets = [x for x in items if x["vlm_target"]]
    print(f"이미지 참조 {sum(len(v) for v in docs_of.values())}개 → 서로 다른 이미지 {len(items)}개")
    print("상태:", dict(states.most_common()))
    print(f"VLM 대상 {len(targets)}개:", dict(Counter(x['state'] for x in targets).most_common()),
          "| 문서 종류", dict(Counter(x['kind'] for x in targets).most_common()))
    big = [x for x in targets if x["width"] * x["height"] >= 600 * 400]
    print(f"그중 600×400 이상(도면·표 후보) {len(big)}개")
    print("저장:", OUT.with_suffix(".json").relative_to(ROOT), OUT.with_suffix(".csv").relative_to(ROOT))


if __name__ == "__main__":
    main()
