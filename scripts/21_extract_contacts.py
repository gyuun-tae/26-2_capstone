"""수집한 공식 페이지에서 연락처를 뽑아 API의 연락처 버튼 목록(src/api/app/contacts.json)을 만든다.

LLM이 전화번호를 만들지 않게, 버튼의 번호는 이 목록에서만 가져온다. 개인 이름은 넣지 않고 역할 이름만 쓴다.
- 대표전화: 모든 페이지 하단 (tel: 링크, "여수광양항만공사 전화걸기")
- 서식 담당: 서식 게시판 페이지의 "업무내용 · 담당자 · 광양/여수 지역 연락처"
- 시설 문의: 안내 페이지 본문의 문의 번호 (홍보관·항만안내선·체육시설)

실행: .\\.venv\\Scripts\\python.exe -B .\\scripts\\21_extract_contacts.py
"""
from collections import Counter
import html
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src/api/app/contacts.json"
PHONE = r"0\d{1,2}-\d{3,4}-\d{4}"

# 시설 문의: (문서, 버튼 이름, 본문에서 번호를 찾는 패턴). 번호는 반드시 원본에서 읽는다
FACILITY = [
    ("YGPA-007", "홍보관 문의", rf"문의\s*:\s*({PHONE})"),
    ("YGPA-008", "항만안내선 담당", rf"항만안내선 담당자\s*\(T\.\s*({PHONE})\)"),
    ("YGPA-005", "체육시설 예약 문의", rf"\[전화\]:\s*({PHONE})"),
]


def text_of(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def snapshot(path: Path) -> str:
    """수집 시각 폴더 이름(20260927T070430...Z) → 날짜"""
    s = path.parent.name
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def main_phone() -> dict:
    found = Counter()
    for page in ROOT.glob("data/raw/*/*/*source.html"):
        raw = page.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(rf'href="tel:({PHONE})" title="여수광양항만공사 전화걸기"', raw):
            found[m.group(1)] += 1
    if len(found) != 1:
        sys.exit(f"대표전화가 하나로 정해지지 않습니다: {dict(found)}")
    phone, n = found.most_common(1)[0]
    return {"key": "main", "label": "여수광양항만공사 대표전화", "phone": phone,
            "note": "담당 부서를 모를 때", "doc_ids": [], "source": f"홈페이지 하단 (수집 페이지 {n}개 공통)",
            "source_url": "https://www.ygpa.or.kr/"}


def form_contacts(catalog: dict) -> list[dict]:
    block = re.compile(rf"업무내용 : (.+?) 담당자 : (.+?) 광양 지역 연락처 TEL : ({PHONE}) .*? 여수 지역 연락처 TEL : ({PHONE})")
    by_role: dict[tuple, dict] = {}
    for doc_id in sorted(catalog):
        for page in sorted(ROOT.glob(f"data/raw/{doc_id}/*/parent_source.html"))[-1:]:
            m = block.search(text_of(page))
            if not m:
                continue
            role = m.group(2).strip()
            for region, phone in (("광양", m.group(3)), ("여수", m.group(4))):
                key = (role, region, phone)
                entry = by_role.setdefault(key, {
                    "key": f"form-{len(by_role) + 1}", "label": f"{role} ({region})", "phone": phone,
                    "note": f"{region} 지역", "doc_ids": [], "source": "서식 게시판 담당 안내",
                    "source_url": catalog[doc_id]["parent_source_url"] or catalog[doc_id]["source_url"],
                    "fetched_on": snapshot(page)})
                entry["doc_ids"].append(doc_id)
    return list(by_role.values())


def facility_contacts(catalog: dict) -> list[dict]:
    chunks_root = ROOT / "data/chunks"
    out = []
    for doc_id, label, pattern in FACILITY:
        texts = [json.loads(line)["text"] for f in chunks_root.glob(f"{doc_id}/*/*/chunks.jsonl")
                 for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
        phones = {m.group(1) for t in texts for m in re.finditer(pattern, " ".join(t.split()))}
        if len(phones) != 1:
            sys.exit(f"{doc_id} {label}: 번호가 하나로 정해지지 않습니다 {phones}")
        out.append({"key": f"facility-{doc_id}", "label": label, "phone": phones.pop(), "note": None,
                    "doc_ids": [doc_id], "source": "안내 페이지 본문", "source_url": catalog[doc_id]["source_url"]})
    return out


def main():
    import csv
    catalog = {r["doc_id"]: r for r in csv.DictReader(
        (ROOT / "data/catalog/ygpa_document_candidates.csv").open(encoding="utf-8-sig"))}
    contacts = [main_phone(), *form_contacts(catalog), *facility_contacts(catalog)]
    OUT.write_text(json.dumps({"generated_by": "scripts/21_extract_contacts.py", "contacts": contacts},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for c in contacts:
        print(f"{c['label']:<28} {c['phone']}  문서 {c['doc_ids'] or '전체'}")
    print("저장:", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
