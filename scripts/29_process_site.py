"""28번이 받은 원본(페이지·게시글·첨부·이미지)을 청크로 만든다. 승인(26번)·색인(16번)은 따로.

실행: OCR을 쓰므로 Windows + 별도 가상환경 (pymupdf, winocr, olefile, pypdf, openpyxl, pillow)
  python scripts/29_process_site.py [--no-ocr]

- 페이지 본문: 25번 html_text. 외국어 페이지는 경계 문구가 달라 <div class="contents"> 영역을 쓴다
- 여러 문서에 반복되는 탭 메뉴·안내 줄은 뺀다
- 이미지: alt 글자 + OCR. 품질 기준을 넘긴 글만 쓰고, review_flags에 ocr_text_unverified를 남긴다.
  사람이 원본과 대조해 옮긴 글은 data/catalog/image_transcripts.json이 OCR보다 우선한다
  글자 이미지는 VLM이 옮긴 글(data/processed/vlm_accepted.json, 31번 --split)이 OCR보다 우선하고 vlm_text_unverified 표시 (2026-11-09)
- 첨부: PDF(글자 없는 쪽만 OCR), HWP, XLSX
- 게시글: 게시일을 본문 첫 줄에 적고 time_sensitive_notice 표시
- 페이지 아래 담당 부서·전화는 연락처 버튼(contacts.json의 site- 항목)으로
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "site-pages-v1"
MAX_CHARS = 2500
CACHE = ROOT / "data/processed/ocr_cache.json"
TRANSCRIPTS = ROOT / "data/catalog/image_transcripts.json"
VLM = ROOT / "data/processed/vlm_accepted.json"  # 31번 --split의 auto (글자 이미지를 VLM이 옮긴 글, 2026-11-09). 없으면 OCR만 쓴다
CONTACTS = ROOT / "src/api/app/contacts.json"
PUBLISHER = "여수광양항만공사"
TAIL = re.compile(r"\n(이전글|다음글|이전 글|다음 글|목록)\n")
BORDER = re.compile(r"담당자\n(.+?)\n전화\n([\d-]+)")


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


c25 = load("c25", "25_collect_ygpa_org_hinterland.py")
sys.path.insert(0, str(ROOT / "scripts"))


def sha(data):
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def contents_slice(raw: str) -> str:
    m = re.search(r'(?s)<div class="contents">(.*?)(?:<footer|class="footer-contents|id="footer")', raw)
    return m.group(1) if m else ""


def page_text(raw: str) -> tuple[str, dict]:
    text = c25.html_text(raw)
    start, end = text.find("X(Twitter)"), text.find("담당자 만족도 평가")
    if 0 <= start < end:
        body, foot = text[start + len("X(Twitter)"):end].strip(), text[end:end + 200]
        m = BORDER.search(foot)
        return body, ({"dept": m.group(1).strip(), "phone": m.group(2)} if m else {})
    return c25.html_text(contents_slice(raw) or raw), {}  # 해양수산청 원본은 본문 영역만 저장돼 있다


def good_ocr(text: str) -> bool:
    """글자 수가 적거나, 한자·기호가 섞여 잘못 읽은 흔적이 있으면 쓰지 않는다"""
    letters = [c for c in text if not c.isspace()]
    if len(letters) < 20:
        return False
    hangul = sum("가" <= c <= "힣" for c in letters)
    hanzi = sum("一" <= c <= "鿿" for c in letters)
    alnum = sum(c.isascii() and c.isalnum() for c in letters)
    return hanzi / len(letters) < 0.02 and (hangul + alnum) / len(letters) > 0.75


class Ocr:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
        self.loop = asyncio.new_event_loop()

    def read(self, blob: bytes, key: str) -> str:
        if key in self.cache:
            return self.cache[key]
        if not self.enabled:
            return ""
        import winocr
        from PIL import Image

        async def run(image):
            return await winocr.recognize_pil(image, "ko")
        try:
            image = Image.open(io.BytesIO(blob)).convert("RGBA")
            if image.width < 300 or image.height < 100:
                text = ""
            else:
                text = self.loop.run_until_complete(run(image)).text
        except Exception as e:
            print("OCR 실패", key[:10], type(e).__name__)
            text = ""
        self.cache[key] = text
        return text

    def save(self):
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0), encoding="utf-8")


def pack(title: str, text: str) -> list[str]:
    parts, current = [], [title]
    for line in text.splitlines():
        while len(line) > MAX_CHARS:  # 줄바꿈 없는 긴 글
            head, line = line[:MAX_CHARS], line[MAX_CHARS:]
            if len(current) > 1:
                parts.append("\n".join(current))
                current = [f"{title} (계속)"]
            parts.append("\n".join(current + [head]))
            current = [f"{title} (계속)"]
        if len(current) > 1 and len("\n".join(current + [line])) > MAX_CHARS:
            parts.append("\n".join(current))
            current = [f"{title} (계속)"]
        current.append(line)
    if len(current) > 1:
        parts.append("\n".join(current))
    return parts


def make_chunks(meta: dict, snap: str, text: str, kind: str, flags: list[str], images: list[str] = ()) -> list[dict]:
    """images: VLM이 옮긴 이미지 글. 이미지마다 따로 청크로 만든다 — 카드뉴스 여러 장을 본문 한 청크에 합치면
    주제가 흐려져 검색 점수가 떨어졌다 (2026-11-09, 크루즈 카드뉴스 7장 → 터미널이용료 질문이 5위 밖)"""
    # 줄 구분으로 읽히는 특수 문자(U+2028 등)가 있으면 chunks.jsonl을 splitlines()로 읽을 때 한 청크가 둘로 갈라진다
    clean = lambda t: re.sub(r"[\u2028\u2029\x0b\x0c\x1c-\x1e\x85]", "\n", t)
    title = meta["title"]
    out = []
    sections = [(p, flags) for p in pack(title, clean(text))] if text.strip() else []
    for n, image in enumerate(images, 1):
        sections += [(p, [*flags, "vlm_text_unverified"]) for p in pack(f"{title} (이미지 {n})", clean(image))]
    for i, (part, part_flags) in enumerate(sections, 1):
        out.append(dict(
            doc_id=meta["doc_id"], document_version=meta.get("source_sha256", ""), source_snapshot=snap, extraction_version=VERSION,
            text_sha256=sha(part), title=title, source_url=meta["source_url"], parent_source_url=meta.get("parent_source_url", meta["source_url"]),
            publisher=meta.get("publisher", PUBLISHER), fetched_at=meta["fetched_at"], published_at=meta.get("date", ""), updated_at="",
            date_status="board_posted" if meta.get("date") else "not_displayed",
            date_evidence="게시판 작성일" if meta.get("date") else "페이지에 발행일 표시 없음. 수집 시각으로 대체하지 않음.",
            language=meta.get("lang", "ko"), chunk_id=f"{meta['doc_id']}-" + sha(f"{VERSION}|{meta['doc_id']}|{i}")[:24],
            chunking_version=VERSION, section_titles=[title], text=part, chunk_text_sha256=sha(part), chunk_kind=kind,
            source_locator={"kind": "processed_text"}, review_status="draft_pending_chunk_review", index_approved=False,
            review_flags=["currentness_not_verified", *part_flags]))
    return out


def save(meta: dict, snap: str, document: str, chunks: list[dict]):
    proc = ROOT / "data/processed" / meta["doc_id"] / snap
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "document.txt").write_text(document + "\n", encoding="utf-8")
    out = ROOT / "data/chunks" / meta["doc_id"] / snap / VERSION
    out.mkdir(parents=True, exist_ok=True)
    (out / "chunks.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(dict(
        doc_id=meta["doc_id"], source_snapshot=snap, chunking_version=VERSION, chunk_count=len(chunks), index_approved=False,
        created_at=datetime.now(timezone.utc).isoformat()), ensure_ascii=False, indent=2), encoding="utf-8")


def post_parts(body: str) -> tuple[str, str, str]:
    """게시글: (제목, 게시일, 본문). 이전글·다음글 뒤를 자른다"""
    m = TAIL.search("\n" + body + "\n")
    if m:
        body = body[:max(0, m.start() - 1)]
    lines = [x for x in body.splitlines() if x.strip()]
    title = lines[0] if lines else ""
    date = ""
    for line in lines[:10]:
        d = re.search(r"(20\d{2}|19\d{2})[-.]\s?(\d{1,2})[-.]\s?(\d{1,2})", line)
        if d:
            date = f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}"
            break
    return title, date, "\n".join(lines[1:])


def fix_name(name: str) -> str:
    """다운로드 헤더의 UTF-8 파일 이름이 latin-1로 읽혀 깨진 경우 되돌린다 (예: 'ì²¨ë¶' → '첨부')"""
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def pdf_text(blob: bytes, ocr: Ocr, key: str) -> tuple[str, bool]:
    import fitz
    used = False
    pages = []
    with fitz.open(stream=blob, filetype="pdf") as doc:
        for i, page in enumerate(doc, 1):
            text = page.get_text().strip()
            if len(text) < 40 and page.get_images() and i <= 80:
                png = page.get_pixmap(dpi=200).tobytes("png")
                read = ocr.read(png, f"{key}-p{i}")
                if good_ocr(read):
                    text, used = read, True
            if text:
                pages.append(f"({i}쪽)\n" + "\n".join(x.strip() for x in text.splitlines() if x.strip()))
    return "\n".join(pages), used


def hwp_text(blob: bytes) -> str:
    extract = __import__("06_extract_attachments", fromlist=["extract_hwp"]).extract_hwp
    return "\n".join(b["text"] for b in extract(blob)["blocks"])


NUMBER = re.compile(r"[-\d,.%]+")


def cell(value) -> str:
    """엑셀 숫자: 정수는 천 단위 쉼표, 소수는 둘째 자리까지 (1862939.25 → 1,862,939.25, -1.9192 → -1.92)"""
    if isinstance(value, float):
        return f"{value:,.0f}" if value.is_integer() else f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return re.sub(r"\s+", " ", str(value)).strip()


def xlsx_text(blob: bytes) -> str:
    """머리글 행(앞 8행 중 글자 칸이 가장 많은 행)과 값을 짝지어 '행 이름 — 머리글: 값; …'으로 적는다.
    머리글 없이 숫자만 나열하면 LLM이 열을 잘못 고른다 (h22: 2026년에 '24년 열을 '작년'으로 읽음)"""
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(blob), data_only=True, read_only=True)
    lines = []
    for sheet in book.worksheets:
        rows = [[cell(c) if c is not None else "" for c in row] for row in sheet.iter_rows(values_only=True)]
        rows = [r for r in rows if any(r)]
        if not rows:
            continue
        head_i = max(range(min(8, len(rows))), key=lambda i: sum(bool(c) and not NUMBER.fullmatch(c) for c in rows[i]))
        head = rows[head_i]
        lines.append(f"[{sheet.title}]")
        lines += [" ".join(c for c in r if c) for r in rows[:head_i]]  # 표 제목·단위
        for r in rows[head_i + 1:]:
            label = " ".join(c for c in r if c and not NUMBER.fullmatch(c)) or "-"
            pairs = [f"{h or '열'}: {c}" for c, h in zip(r, head) if c and NUMBER.fullmatch(c)]
            lines.append(f"{label} — " + "; ".join(pairs) if pairs else label)
    return "\n".join(lines)


def low_quality(text: str) -> str:
    """색인하지 않을 글의 사유: 인포그래픽 PDF처럼 숫자·짧은 조각만 흩어진 글, 내용 없는 목차 (v3 u04·h22)"""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if not lines:
        return "빈 글"
    short = sum(len(x) <= 8 for x in lines) / len(lines)
    if len(lines) >= 30 and short > 0.6:
        return f"짧은 조각 비율 {short:.0%} (인포그래픽 추출 잡음)"
    outline = sum(bool(re.match(r"([가-하]\.|\d+\)|\d+\.|표\s*\d)", x)) and len(x) < 40 for x in lines) / len(lines)
    if len(lines) >= 15 and outline > 0.7:
        return f"목차 줄 비율 {outline:.0%}"
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-ocr", action="store_true")
    args = ap.parse_args()
    ocr = Ocr(not args.no_ocr)
    manual = json.loads(TRANSCRIPTS.read_text(encoding="utf-8")) if TRANSCRIPTS.exists() else {}
    vlm = json.loads(VLM.read_text(encoding="utf-8")) if VLM.exists() else {}
    docs = []
    for folder in sorted([*(ROOT / "data/raw").glob("YGPA-*"), *(ROOT / "data/raw").glob("MOF-*")]):
        snaps = sorted(p for p in folder.iterdir() if p.is_dir())
        if not snaps or not (snaps[-1] / "metadata.json").exists():
            continue
        meta = json.loads((snaps[-1] / "metadata.json").read_text(encoding="utf-8"))
        if meta.get("kind") in ("page", "board_post") or folder.name.startswith("YGPA-F"):
            docs.append((folder.name, snaps[-1], meta))
    print("문서", len(docs), flush=True)

    # 페이지·게시글 본문 준비와 반복 줄 세기
    prepared, line_docs, image_docs = {}, {}, Counter()
    for doc_id, snap, meta in docs:
        if doc_id.startswith("YGPA-F"):
            continue
        raw = (snap / "source.html").read_text(encoding="utf-8", errors="replace")
        body, contact = page_text(raw)
        prepared[doc_id] = (body, contact)
        for line in set(body.splitlines()):
            if len(line) < 60:
                line_docs.setdefault(meta.get("lang", "ko"), Counter())[line] += 1
        for im in meta.get("images", []):
            if im.get("sha256"):
                image_docs[im["sha256"]] += 1

    stats, contacts, skipped, seen_images = Counter(), [], [], set()
    for doc_id, snap, meta in docs:
        name = snap.name
        if doc_id.startswith("YGPA-F"):
            source = next(p for p in snap.iterdir() if p.name.startswith("source."))
            blob, suffix, flags = source.read_bytes(), source.suffix.lower(), []
            try:
                if suffix == ".pdf":
                    text, used = pdf_text(blob, ocr, sha(blob)[:16])
                    if used:
                        flags.append("ocr_text_unverified")
                elif suffix == ".hwp":
                    text = hwp_text(blob)
                elif suffix == ".xlsx":
                    text = xlsx_text(blob)
                else:
                    skipped.append((doc_id, f"형식 미지원 {suffix}"))
                    continue
            except Exception as e:
                skipped.append((doc_id, f"{type(e).__name__}: {str(e)[:60]}"))
                continue
            if len(text.strip()) < 30:
                skipped.append((doc_id, "추출 글자 없음"))
                continue
            if reason := low_quality(text):
                skipped.append((doc_id, reason))
                continue
            meta["title"] = fix_name(meta["title"]).replace("_", " ")
            save(meta, name, text, chunks := make_chunks(meta, name, text, "attachment", flags))
            stats["attachment"] += 1
            stats["chunks"] += len(chunks)
            continue

        body, contact = prepared[doc_id]
        kind, flags = "web_page", []
        if meta["kind"] == "board_post":
            title, date, body = post_parts(body)
            board = meta.get("board") or ""
            meta["date"] = date
            if board == "용어사전":
                kind = "glossary"
                meta["title"] = f"항만 용어: {title}"
            else:
                kind = "notice"
                flags.append("time_sensitive_notice")
                meta["title"] = f"{title} ({board})"
                if date:
                    body = f"게시일: {date}\n{body}"
        repeated = line_docs.get(meta.get("lang", "ko"), Counter())
        # 표 머리글은 여러 문서에 같아도 값의 뜻을 알려 주므로 남긴다
        lines = [x for x in body.splitlines() if repeated[x] < 5 or len(x) >= 60 or "|" in x or "—" in x]
        extra, images = [], []
        for im in meta.get("images", []):
            key = im.get("sha256")
            if not key or key in seen_images or image_docs[key] >= 3:
                continue
            seen_images.add(key)
            alt = im.get("alt", "")
            if key in manual:
                extra.append(manual[key])
                continue
            # 사진 설명 alt는 검색 잡음이고, 다른 항만 이름이 적힌 alt는 사이트 오타라 쓰지 않는다
            if len(alt) >= 15 and not re.search(r"사진|모습|전경|바라본|이미지|미리보기|인천항|경인항", alt):
                extra.append(alt)
            # 우선순위: 사람 전사 > VLM(글자 이미지만, 지도·도면은 31번이 걸러 냄) > OCR
            if key in vlm:
                images.append("(이미지 내용을 AI가 글로 옮긴 것이므로 숫자·이름은 원문 확인 필요)\n" + vlm[key]["text"])
                stats["vlm_images"] += 1
                continue
            if meta.get("lang", "ko") == "ko" and im.get("file") and (snap / im["file"]).exists():
                read = ocr.read((snap / im["file"]).read_bytes(), key)
                if good_ocr(read) and read not in body:
                    extra.append("(이미지에서 자동으로 읽은 글자이므로 원문 확인 필요) " + re.sub(r"\s+", " ", read))
                    if "ocr_text_unverified" not in flags:
                        flags.append("ocr_text_unverified")
                    stats["ocr_images"] += 1
        # 이미지별 청크는 게시글(카드뉴스·공고 — 이미지가 곧 본문)만. 안내 페이지는 본문에 합친다: 페이지 흐름도 이미지가
        # 따로 청크가 되면 같은 내용이 여러 자리를 차지해 정의 문서(h17 Port-MIS)·다른 문서(t24)를 밀어냈다 (2026-11-09)
        if kind != "notice":
            extra, images = extra + images, []
            if any("AI가 글로 옮긴" in x for x in extra) and "vlm_text_unverified" not in flags:
                flags.append("vlm_text_unverified")
        text = "\n".join(lines + extra).strip()
        # 게시판(용어사전·공지)의 담당자는 게시판 관리 부서라 업무 담당이 아니다 (org o07·o12: 용어마다 'AI디지털부'가 붙어 부서 질문을 모두 AI디지털부로 답함)
        if contact and kind == "web_page":
            text += f"\n이 안내 페이지 담당 부서: {contact['dept']} (전화 {contact['phone']})"
            contacts.append({"key": f"site-{doc_id}", "label": contact["dept"], "phone": contact["phone"], "note": meta["title"][:40],
                             "doc_ids": [doc_id], "source": f"{meta['title'][:40]} 페이지 담당자 안내", "source_url": meta["source_url"],
                             "fetched_on": meta["fetched_at"][:10]})
        if len(re.sub(r"\s", "", text + "".join(images))) < 30:
            skipped.append((doc_id, "본문 거의 없음"))
            continue
        # 페이지에는 목차 기준만 쓴다 (업체 목록 같은 짧은 줄 표는 정상 내용, MOF-4157)
        if reason := ("목차 페이지" if "목차" in meta["title"] else "".join(r for r in [low_quality(text)] if r.startswith("목차"))):
            skipped.append((doc_id, reason))
            continue
        save(meta, name, "\n".join([text, *images]).strip(), chunks := make_chunks(meta, name, text, kind, flags, images))
        stats[kind] += 1
        stats["chunks"] += len(chunks)
    ocr.save()
    data = json.loads(CONTACTS.read_text(encoding="utf-8"))
    data["contacts"] = [c for c in data["contacts"] if not c["key"].startswith("site-")] + contacts
    CONTACTS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(dict(stats), "연락처", len(contacts), "건너뜀", len(skipped))
    (ROOT / "data/catalog/site_processing_skipped.json").write_text(json.dumps(skipped, ensure_ascii=False, indent=0), encoding="utf-8")


if __name__ == "__main__":
    main()
