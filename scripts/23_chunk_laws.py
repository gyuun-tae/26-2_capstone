"""22번이 받은 법령·고시 원문(JSON)을 조문 하나 = 청크 하나로 나눈다. 네트워크를 쓰지 않는다.

입력: data/raw/LAW-xxx/<최신 스냅샷>/source.json, metadata.json
출력: data/processed/LAW-xxx/<스냅샷>/document.txt (사람이 읽는 전체 본문)
      data/chunks/LAW-xxx/<스냅샷>/law-articles-v1/chunks.jsonl, manifest.json, review.md
규칙: 장·절 제목은 section_titles로만 붙이고, 부칙·서식(별지)·내용이 '삭제'뿐인 조문은 뺀다(manifest에 기록).
      별표(표)는 테두리 줄을 지우고 표의 행 경계에서 나눠 넣는다. law_sources.json의 annex_held에 적은 별표는 뺀다.
      MAX_CHARS를 넘는 조문은 항(없으면 호) 경계에서 나누고, 뒤 조각 첫 줄에 '제n조(제목) (계속)'을 붙인다.

  python scripts/23_chunk_laws.py
"""
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
VERSION = "law-articles-v1"
EXTRACTION = "law-api-json-v1"
MAX_CHARS = 2500  # 근거 하나당 LLM에 넣는 글자 상한(prompt.CHUNK_CHARS 3000)보다 작게

# 상자 문자로 그린 표의 가로 테두리 줄 = 행 경계. 세로 칸막이만 있는 빈 줄은 버린다
BOX_RULE = re.compile(r"^[\s┏┓┗┛┣┫┠┨┳┻╋╂━─┯┷┼├┤┬┴│┃┌┐└┘┝┥┿]*[━─][\s┏┓┗┛┣┫┠┨┳┻╋╂━─┯┷┼├┤┬┴│┃┌┐└┘┝┥┿]*$")
BOX_EMPTY = re.compile(r"^[\s┃│]*$")
DELETED_ANNEX = re.compile(r"^삭제\s*(?:<[^>]*>)?\s*$")
DELETED = re.compile(r"^제\d+조(?:의\d+)?\s*삭제\s*(?:<[^>]*>)?\s*$")
HEADING = re.compile(r"^제\d+(장|절|관)\s")
ADMRUL_ARTICLE = re.compile(r"^제(\d+)조(?:의(\d+))?\s*(?:\(([^)]*)\))?")
# 고시 본문은 항·호가 줄바꿈 없이 붙어 온다: "…같다.1. "무역항 등"이란…" → 항(①)·호(1.) 앞에서 줄을 바꾼다
CIRCLED = re.compile(r"(?<=\S)\s*(?=[①-⑳])")
# "…사용료4. 그 밖에"처럼 글자 뒤에 바로 붙기도 한다. 날짜 "2026.1.1. "의 끝자리는 호 번호가 아니다
ITEM = re.compile(r"(?<![\d\s])(?<!\d\.)\s*(?=\d{1,2}\.\s)")


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def heading(text: str) -> str:
    """장·절 제목의 개정 표시 제거: '제1장 총칙 <개정 2010.2.4>' → '제1장 총칙'"""
    return re.sub(r"\s*<[^>]*>", "", text).strip()


def mok_lines(mok: dict) -> list[str]:
    """목내용은 문자열이거나 [[줄, 줄…]] 형태(하위 1) 2) 목록)"""
    content = mok.get("목내용", "")
    if isinstance(content, str):
        return [clean(content)]
    return [clean(line) for group in content for line in as_list(group) if clean(line)]


def ho_lines(ho: dict) -> list[str]:
    lines = [clean(ho["호내용"])] if ho.get("호내용") else []
    for mok in as_list(ho.get("목")):
        lines += mok_lines(mok)
    return lines


def law_units(article: dict) -> tuple[str, list[list[str]]]:
    """(머리줄, 나눌 수 있는 단위 목록). 단위 = 항 하나(그 아래 호·목 포함). 항 번호 없이 호만 있으면 호 하나씩"""
    head = clean(article["조문내용"])
    units = []
    for hang in as_list(article.get("항")):
        if hang.get("항내용"):
            lines = [clean(hang["항내용"])]
            for ho in as_list(hang.get("호")):
                lines += ho_lines(ho)
            units.append(lines)
        else:
            units += [ho_lines(ho) for ho in as_list(hang.get("호"))]
    return head, [u for u in units if u]


def admrul_units(text: str) -> tuple[str, list[list[str]]]:
    text = ITEM.sub("\n", CIRCLED.sub("\n", clean(text)))
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    # 첫 줄(제n조(제목) 본문…)은 머리줄, 나머지는 항이 시작하는 줄마다 단위를 나눈다
    units, current = [], []
    for line in lines[1:]:
        if line[0] in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳" and current:
            units.append(current)
            current = []
        current.append(line)
    if current:
        units.append(current)
    return lines[0], units


def pack(head: str, units: list[list[str]], label: str) -> list[str]:
    """MAX_CHARS 안으로 단위를 묶는다. 한 단위가 너무 길면 줄 단위로 더 나눈다"""
    pieces = []
    for unit in units:
        if len("\n".join(unit)) <= MAX_CHARS:
            pieces.append(unit)
            continue
        part = []
        for line in unit:
            if part and len("\n".join(part + [line])) > MAX_CHARS:
                pieces.append(part)
                part = []
            part.append(line)
        pieces.append(part)

    parts, current = [], [head]
    for piece in pieces:
        if len(current) > 1 and len("\n".join(current + piece)) > MAX_CHARS:
            parts.append(current)
            current = [f"{label} (계속)"]
        current += piece
    parts.append(current)
    return ["\n".join(p) for p in parts]


def articles(source: dict) -> tuple[list[dict], dict]:
    """조문 목록 [{key, label, title, headings, head, units}]과 제외 기록"""
    found, excluded = [], {"deleted_articles": [], "addenda": 0}
    chapter = section = ""
    if "법령" in source:
        body = source["법령"]
        excluded["addenda"] = len(as_list((body.get("부칙") or {}).get("부칙단위")))
        for a in as_list(body["조문"]["조문단위"]):
            text = clean(a["조문내용"])
            if a["조문여부"] == "전문":
                if text.startswith("제") and "장" in text.split()[0]:
                    chapter, section = heading(text), ""
                else:
                    section = heading(text)
                continue
            label = f"제{a['조문번호']}조" + (f"의{a['조문가지번호']}" if a.get("조문가지번호") else "")
            if DELETED.match(text) and not a.get("항"):
                excluded["deleted_articles"].append(label)
                continue
            head, units = law_units(a)
            found.append(dict(key=a["조문키"], label=label, title=a.get("조문제목", ""),
                              headings=[h for h in (chapter, section) if h], head=head, units=units))
    else:
        body = source["AdmRulService"]
        excluded["addenda"] = len(as_list((body.get("부칙") or {}).get("부칙내용")))
        for i, text in enumerate(as_list(body["조문내용"])):
            text = clean(text)
            if HEADING.match(text):
                if "장" in text.split()[0]:
                    chapter, section = heading(text), ""
                else:
                    section = heading(text)
                continue
            m = ADMRUL_ARTICLE.match(text)
            if not m:
                raise ValueError(f"조문 형식이 아닌 줄: {text[:40]}")
            label = f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else "")
            if DELETED.match(text):
                excluded["deleted_articles"].append(label)
                continue
            head, units = admrul_units(text)
            found.append(dict(key=f"{i:04d}", label=label, title=m.group(3) or "",
                              headings=[h for h in (chapter, section) if h], head=head, units=units))
    labels = [a["label"] for a in found]
    if len(labels) != len(set(labels)):
        raise ValueError("조문 번호가 겹칩니다")
    return found, excluded


def annex_units(lines: list[str]) -> list[list[str]]:
    """표 줄 → 행 묶음. 가로 테두리에서 끊고, 연속 공백은 하나로 줄인다 (세로 칸막이 ┃는 칸 구분으로 남긴다)"""
    units, current = [], []
    for line in lines:
        if BOX_RULE.match(line):
            if current:
                units.append(current)
            current = []
        elif not BOX_EMPTY.match(line):
            current.append(re.sub(r"\s{2,}", " ", line).strip())
    if current:
        units.append(current)
    return units


def annexes(source: dict, held: dict) -> tuple[list[dict], dict]:
    """별표(표)만 넣는다. 서식·별지(빈 신청서 양식)는 본문 검색에 도움이 안 돼 개수만 기록"""
    body = source.get("법령") or source["AdmRulService"]
    found, excluded = [], {"forms": 0, "annexes_held": [], "deleted_annexes": []}
    for b in as_list((body.get("별표") or {}).get("별표단위")):
        if b.get("별표구분") != "별표":
            excluded["forms"] += 1
            continue
        number = int(b["별표번호"])
        label = "[별표" + (f" {number}" if number else "") + (f"의{int(b['별표가지번호'])}" if int(b.get("별표가지번호") or 0) else "") + "]"
        title = clean(html.unescape(b.get("별표제목", "")))  # "삭제 &lt;1998.12.31&gt;"
        if DELETED_ANNEX.match(title):
            excluded["deleted_annexes"].append(label)
            continue
        if b["별표키"] in held:
            excluded["annexes_held"].append(dict(label=label, title=title, reason=held[b["별표키"]]))
            continue
        lines = [clean(line) for group in as_list(b.get("별표내용")) for line in as_list(group)]
        # 원문 첫 줄들("[별표 1]", 제목)은 머리줄과 겹치므로 뺀다
        while lines and (not lines[0] or lines[0].startswith("[별표") or lines[0] == title):
            lines.pop(0)
        link = b.get("별표서식PDF파일링크") or ""
        found.append(dict(kind="annex", key=f"annex-{b['별표키']}", label=label, title=title, headings=[],
                          head=f"{label} {title}", units=annex_units(lines),
                          url=f"https://www.law.go.kr{link}" if link.startswith("/") else ""))
    return found, excluded


def basic_info(source: dict) -> dict:
    if "법령" in source:
        info = source["법령"]["기본정보"]
        ministry = info["소관부처"]["content"] if isinstance(info["소관부처"], dict) else info["소관부처"]
        return dict(publisher=ministry, published=info["공포일자"], effective=info["시행일자"])
    info = source["AdmRulService"]["행정규칙기본정보"]
    return dict(publisher=info["소관부처명"], published=info["발령일자"], effective=info["시행일자"])


def iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}" if len(yyyymmdd) == 8 else ""


def article_url(meta: dict, label: str) -> str:
    """법령은 조문으로 바로 가는 주소, 고시는 고시 전체 주소"""
    if meta["target"] == "law":
        return f"https://www.law.go.kr/법령/{quote(meta['title'])}/{quote(label)}"
    return meta["source_url"]


def build(meta: dict, source: dict, source_bytes: bytes, held: dict | None = None) -> tuple[list[dict], dict, str]:
    info = basic_info(source)
    found, excluded = articles(source)
    article_count = len(found)
    annex_found, annex_excluded = annexes(source, held or {})
    found += annex_found
    excluded |= annex_excluded
    document = "\n\n".join("\n".join([a["head"]] + [line for u in a["units"] for line in u]) for a in found)
    base = dict(
        doc_id=meta["doc_id"], document_version=sha(source_bytes), source_snapshot=meta["source_snapshot"],
        extraction_version=EXTRACTION, text_sha256=sha(document), title=meta["title"],
        parent_source_url=meta["source_url"], publisher=info["publisher"], fetched_at=meta["fetched_at"],
        published_at=iso(info["published"]), updated_at="", effective_at=iso(info["effective"]),
        date_status="official_api_current",
        date_evidence="국가법령정보 Open API 현행 본문의 공포(발령)일자·시행일자",
    )
    chunks = []
    for a in found:
        if a.get("kind") == "annex":
            name = a["head"]
        else:
            name = f"{a['label']}({a['title']})" if a["title"] else a["label"]
        texts = pack(a["head"], a["units"], name)
        for part, text in enumerate(texts, 1):
            chunks.append(dict(
                base,
                chunk_id=f"{meta['doc_id']}-" + sha(f"{meta['serial']}|{a['key']}|{part}")[:24],
                chunking_version=VERSION, source_url=a.get("url") or article_url(meta, a["label"]),
                section_titles=a["headings"] + [name], text=text, chunk_text_sha256=sha(text),
                chunk_kind=a.get("kind", "article"),
                source_locator=dict(kind="law_api", law_name=meta["title"], serial=meta["serial"],
                                    article_key=a["key"], article_label=name, part=part, part_count=len(texts)),
                review_status="draft_pending_chunk_review", index_approved=False, review_flags=[],
            ))
    manifest = dict(
        doc_id=meta["doc_id"], title=meta["title"], source_snapshot=meta["source_snapshot"],
        document_version=sha(source_bytes), chunking_version=VERSION, serial=meta["serial"],
        effective_at=iso(info["effective"]), article_count=article_count, annex_count=len(annex_found),
        chunk_count=len(chunks),
        split_articles=[a["label"] for a in found if sum(c["source_locator"]["article_key"] == a["key"] for c in chunks) > 1],
        excluded=excluded, index_approved=False,
    )
    return chunks, manifest, document


def save(root: Path, chunks: list[dict], manifest: dict, document: str) -> str:
    doc_id, snap = manifest["doc_id"], manifest["source_snapshot"]
    lines = [f"# {doc_id} {manifest['title']} 청크 검토",
             f"검색 승인 전 초안. 시행 {manifest['effective_at']}, 조문 {manifest['article_count']}개·별표 {manifest['annex_count']}개 → 청크 {manifest['chunk_count']}개. "
             f"제외: 삭제 조문 {len(manifest['excluded']['deleted_articles'])}개, 부칙 {manifest['excluded']['addenda']}개, "
             f"서식 {manifest['excluded']['forms']}개, 보류 별표 {len(manifest['excluded']['annexes_held'])}개."]
    for c in chunks:
        lines += [f"## {' > '.join(c['section_titles'])}", c["text"]]
    outputs = {
        "chunks.jsonl": "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks),
        "review.md": "\n\n".join(lines) + "\n",
    }
    expected = {**manifest, "output_hashes": {k: sha(v) for k, v in outputs.items()}}
    out = root / "data/chunks" / doc_id / snap / VERSION
    if (out / "manifest.json").exists():
        old = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        if all(old.get(k) == v for k, v in expected.items()):
            return "그대로"
        raise ValueError(f"{out}의 기존 청크와 다릅니다. 덮어쓰지 않습니다 (청크 규칙을 바꿨다면 VERSION을 올리세요)")
    processed = root / "data/processed" / doc_id / snap
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "document.txt").write_text(document + "\n", encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        (out / name).write_text(text, encoding="utf-8")
    created = {**expected, "created_at": datetime.now(timezone.utc).isoformat()}
    (out / "manifest.json").write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
    return "생성"


def main():
    sources = json.loads((ROOT / "docs/contracts/law_sources.json").read_text(encoding="utf-8"))
    for doc in sorted((ROOT / "data/raw").glob("LAW-*")):
        snap = sorted(p for p in doc.iterdir() if (p / "source.json").exists())[-1]  # 최신 스냅샷만
        meta = json.loads((snap / "metadata.json").read_text(encoding="utf-8"))
        source_bytes = (snap / "source.json").read_bytes()
        held = sources.get("annex_held", {}).get(meta["doc_id"], {})
        chunks, manifest, document = build(meta, json.loads(source_bytes), source_bytes, held)
        status = save(ROOT, chunks, manifest, document)
        ex = manifest["excluded"]
        print(f"{meta['doc_id']} {meta['title']} | 조문 {manifest['article_count']}·별표 {manifest['annex_count']} → 청크 {manifest['chunk_count']}"
              f" (나눈 것 {len(manifest['split_articles'])}) | 제외 삭제 {len(ex['deleted_articles'])}·부칙 {ex['addenda']}·서식 {ex['forms']}"
              f"·보류 별표 {len(ex['annexes_held'])} | {status}")


if __name__ == "__main__":
    main()
