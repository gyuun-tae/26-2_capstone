"""YGPA 공식 사이트에서 배후단지 입주 안내 페이지와 부서별 담당업무를 받아 청크로 만든다.

왜: 팀원 시험에서 "배후단지 입주 절차"가 단계 이름만 나열돼 👎, "담당부서를 찾고 싶어요"는 부서 자료가 없어
대표전화로만 끝났다. 배후단지 메뉴(입주정보·입주지원)와 '조직 및 직원검색'(부서명·담당업무·전화, 직원 이름 없음)을 넣는다.

- 배후단지 페이지(PAGES) → YGPA-034~039. 페이지 아래 '담당자' 부서·전화는 연락처 버튼(contacts.json)으로.
- 부서별 담당업무 → 부서마다 ORG-xxx 문서 하나 + 조직 개요 ORG-000. 부서 연락처 버튼은 '업무 총괄' 번호(없으면 첫 번호).
- 원본: data/raw/<id>/<스냅샷>/source.html 또는 source.json, 청크: data/chunks/<id>/<스냅샷>/web-pages-v1/
- contacts.json의 key가 "page-"·"dept-"로 시작하는 항목은 이 스크립트가 다시 만든다(다른 항목은 그대로).

  python scripts/25_collect_ygpa_org_hinterland.py
"""
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
HOST = "https://www.ygpa.or.kr"
USER_AGENT = "YGPA-Capstone/0.2"
VERSION = "web-pages-v1"
MAX_CHARS = 2500
CONTACTS = ROOT / "src/api/app/contacts.json"

PAGES = [
    ("YGPA-034", "광양항 배후단지 입주정보 — 임대조건", "/hmpg/ygpa/port/gybe/mvin/mv01/contPageDetail.do?conts_no=100AE3FE95BF410B8DC1FDBF3A544797"),
    ("YGPA-035", "광양항 배후단지 입주정보 — 입주자격", "/hmpg/ygpa/port/gybe/mvin/mv02/contPageDetail.do?conts_no=8613460E64A24FBA918BCDB0324B75BE"),
    ("YGPA-036", "광양항 배후단지 입주정보 — 입주절차", "/hmpg/ygpa/port/gybe/mvin/mv03/contPageDetail.do?conts_no=CD4B5BF76A874E338C2426014ACF83B5"),
    ("YGPA-037", "광양항 배후단지 입주정보 — 입주기업 선정기준", "/hmpg/ygpa/port/gybe/mvin/mv04/contPageDetail.do?conts_no=844CF4E513734286940C6E1E3D24B326"),
    ("YGPA-038", "광양항 배후단지 입주정보 — 세제감면", "/hmpg/ygpa/port/gybe/mvin/mv05/contPageDetail.do?conts_no=D36403CD1A1C48E4ADA70DB154EF30FD"),
    ("YGPA-039", "광양항 배후단지 맞춤형 입주지원 (전 기간)", "/hmpg/ygpa/port/gybe/mvsu/ms01/contPageDetail.do?conts_no=F0D3217ED281457C9D6F55854160CD76"),
]
# 본문 앞에 반복되는 탭 메뉴·안내 줄
NAV = {"※ 문사항이 있을 경우 상담센터 Q&A 게시판에 문의해주세요.", "상담센터 Q&A", "임대조건", "입주자격", "입주절차",
       "입주기업 선정기준", "세제감면", "맞춤형 입주지원 (전 기간)", "입주희망", "입주준비", "입주개시", "사업확장",
       "기관별 지원내용 (종합)"}
ORG_CHART = "/hmpg/ygpa/ygpa/orga/ogch/orgaChartPage.do"
ORG_LIST = "/hmpg/ygpa/ygpa/orga/empl/orgaChartList.do"
# 조직도의 본부 → 소속 부서 (조직도 페이지 순서). 본부 이름이 아닌 항목은 사장 직속
HEADQUARTERS = ("경영본부", "운영본부", "개발사업본부", "여수엑스포해양복합사업단")


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def fetch(path: str, data: dict | None = None) -> bytes:
    body = urlencode(data).encode() if data is not None else None
    with urlopen(Request(HOST + path, data=body, headers={"User-Agent": USER_AGENT}), timeout=30) as r:
        raw = r.read()
    time.sleep(0.7)  # 공공기관 사이트에 몰아서 요청하지 않는다
    return raw


def _cells(row: str) -> list[str]:
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() or "-"
            for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", row)]


def _table(match: re.Match) -> str:
    """첫 행을 머리글로 보고, 칸 수가 같은 행은 '첫 칸 — 머리글: 값; …'으로 (LLM이 기한·근거를 짝지어 읽게).
    병합 칸 때문에 칸 수가 다른 행은 '칸 | 칸'으로 둔다"""
    rows = [_cells(r) for r in re.findall(r"(?is)<tr\b.*?</tr>", match.group(0))]
    if not rows:
        return "\n"
    head, lines = rows[0], [" | ".join(rows[0])]
    for cells in rows[1:]:
        if len(cells) == len(head) > 1:
            lines.append(f"{cells[0]} — " + "; ".join(f"{h}: {c}" for h, c in zip(head[1:], cells[1:])))
        else:
            lines.append(" | ".join(cells))
    return "\n" + "\n".join(lines) + "\n"


def html_text(fragment: str) -> str:
    """표는 _table(행 단위 문장), 나머지 블록은 줄바꿈으로 남기는 단순 변환. 표 설명(caption)은 뺀다"""
    s = re.sub(r"(?is)<(script|style|caption)\b.*?</\1>|<!--.*?-->", "", fragment)
    s = re.sub(r"(?is)<table\b.*?</table>", _table, s)
    s = re.sub(r"(?i)<br\s*/?>|</(tr|p|li|div|h\d|dt|dd|caption)\s*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    lines = [re.sub(r"\s+", " ", line).strip(" |") for line in s.splitlines()]
    return "\n".join(line for line in lines if line)


def page_body(raw: str) -> tuple[str, dict]:
    """본문(공유 버튼 뒤 ~ '담당자 만족도 평가' 앞)과 페이지 아래 담당 부서·전화"""
    text = html_text(raw)
    start = text.find("X(Twitter)")
    end = text.find("담당자 만족도 평가")
    if start < 0 or end < start:
        raise ValueError("본문 경계를 찾지 못했습니다 (페이지 구조 변경?)")
    lines = text[start + len("X(Twitter)"):end].strip().splitlines()
    while lines and lines[0] in NAV:  # 본문 앞 탭 메뉴
        lines.pop(0)
    body = "\n".join(lines)
    foot = text[end:end + 200]
    m = re.search(r"담당자\n(.+?)\n전화\n([\d-]+)", foot)
    contact = {"dept": m.group(1).strip(), "phone": m.group(2)} if m else {}
    return body, contact


def pack(title: str, text: str) -> list[str]:
    parts, current = [], [title]
    for line in text.splitlines():
        if len(current) > 1 and len("\n".join(current + [line])) > MAX_CHARS:
            parts.append("\n".join(current))
            current = [f"{title} (계속)"]
        current.append(line)
    parts.append("\n".join(current))
    return parts


def chunk(doc_id, title, url, snap, fetched, text, kind, section, part, total, source_sha):
    return dict(
        doc_id=doc_id, document_version=source_sha, source_snapshot=snap, extraction_version="html-text-v2",
        text_sha256=sha(text), title=title, source_url=url, parent_source_url=url, publisher="여수광양항만공사",
        fetched_at=fetched, published_at="", updated_at="", date_status="not_displayed",
        date_evidence="페이지에 발행일 표시 없음. 수집 시각으로 대체하지 않음.",
        chunk_id=f"{doc_id}-" + sha(f"{VERSION}|{doc_id}|{part}")[:24], chunking_version=VERSION,
        section_titles=[section], text=text, chunk_text_sha256=sha(text), chunk_kind=kind,
        source_locator={"kind": "processed_text"}, review_status="draft_pending_chunk_review",
        index_approved=False, review_flags=["currentness_not_verified"],
    )


def save(doc_id, snap, raw_name, raw: bytes, meta: dict, document: str, chunks: list[dict]):
    raw_dir = ROOT / "data/raw" / doc_id / snap
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / raw_name).write_bytes(raw)
    (raw_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    proc = ROOT / "data/processed" / doc_id / snap
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "document.txt").write_text(document + "\n", encoding="utf-8")
    out = ROOT / "data/chunks" / doc_id / snap / VERSION
    out.mkdir(parents=True, exist_ok=True)
    (out / "chunks.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
    (out / "review.md").write_text(f"# {doc_id} {meta['title']} 청크 검토\n\n" + "\n\n".join(
        f"## {c['section_titles'][0]}\n\n{c['text']}" for c in chunks) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(dict(
        doc_id=doc_id, source_snapshot=snap, chunking_version=VERSION, chunk_count=len(chunks),
        input_hashes={raw_name: sha(raw)}, index_approved=False, created_at=datetime.now(timezone.utc).isoformat(),
    ), ensure_ascii=False, indent=2), encoding="utf-8")


def collect_pages(snap: str, fetched: str) -> list[dict]:
    contacts = []
    for doc_id, title, path in PAGES:
        raw = fetch(path)
        body, contact = page_body(raw.decode("utf-8"))
        url = HOST + path
        if contact:
            body += f"\n담당 부서: {contact['dept']} (전화 {contact['phone']})"
            contacts.append({"key": f"page-{doc_id}", "label": f"{contact['dept']} (배후단지 담당)", "phone": contact["phone"],
                             "note": "광양항 배후단지 입주·임대", "doc_ids": [doc_id], "source": f"{title} 페이지 담당자 안내",
                             "source_url": url, "fetched_on": fetched[:10]})
        texts = pack(title, body)
        chunks = [chunk(doc_id, title, url, snap, fetched, t, "web_page", title, i, len(texts), sha(raw))
                  for i, t in enumerate(texts, 1)]
        save(doc_id, snap, "source.html", raw, dict(doc_id=doc_id, title=title, source_url=url, fetched_at=fetched,
                                                    source_sha256=sha(raw), contact=contact), body, chunks)
        print(f"{doc_id} {title} | {len(body)}자 → 청크 {len(chunks)} | 담당 {contact.get('dept', '-')}")
    return contacts


def org_structure(chart_html: str) -> list[tuple[str, str]]:
    """조직도 순서대로 (본부 또는 '사장 직속', 부서명)"""
    names = re.findall(r"data-dept_nm='([^']+)'", chart_html)
    out, group = [], "사장 직속"
    for name in names:
        if name == "여수광양항만공사":
            continue
        if name in HEADQUARTERS:
            group = name
            if name == "여수엑스포해양복합사업단":
                out.append(("사장 직속", name))
            continue
        out.append((group, name))
    return out


def duties(dept: str) -> list[tuple[str, str]]:
    raw = fetch(ORG_LIST, {"list_yn": "Y", "searchkey3": "dept_nm", "searchtxt3": dept}).decode("utf-8")
    rows = []
    for body in re.findall(r"(?s)<tbody>(.*?)</tbody>", raw):
        for tr in re.findall(r"(?s)<tr>(.*?)</tr>", body):
            cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()
                     for c in re.findall(r"(?s)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
            if len(cells) == 3 and cells[0] == dept and re.fullmatch(r"[\d-]+", cells[2]):
                rows.append((cells[1], cells[2]))
    return rows


def collect_org(snap: str, fetched: str) -> list[dict]:
    chart = fetch(ORG_CHART).decode("utf-8")
    structure = org_structure(chart)
    url = HOST + ORG_CHART
    all_rows, contacts, overview = {}, [], ["여수광양항만공사 조직 (본부·부서와 대표 담당업무)"]
    for i, (group, dept) in enumerate(structure, 1):
        rows = duties(dept)
        all_rows[dept] = rows
        if not rows:
            continue
        doc_id = f"ORG-{i:03d}"
        by_task: dict[str, list[str]] = {}
        for task, phone in rows:
            by_task.setdefault(task, []).append(phone)
        lines = [f"{dept} 담당업무와 전화 ({group} 소속)"] + [f"- {task}: {', '.join(p)}" for task, p in by_task.items()]
        text = "\n".join(lines)
        lead = next((p[0] for t, p in by_task.items() if "총괄" in t), rows[0][1])
        contacts.append({"key": f"dept-{doc_id}", "label": dept, "phone": lead, "note": "부서 업무 총괄" if any("총괄" in t for t in by_task) else "부서 대표",
                         "doc_ids": [doc_id], "source": "조직 및 직원검색 (부서명·담당업무·전화)", "source_url": url,
                         "fetched_on": fetched[:10]})
        title = f"여수광양항만공사 {dept}"
        save(doc_id, snap, "source.json", json.dumps(rows, ensure_ascii=False).encode("utf-8"),
             dict(doc_id=doc_id, title=title, source_url=url, fetched_at=fetched, group=group), text,
             [chunk(doc_id, title, url, snap, fetched, text, "department", dept, 1, 1, sha(json.dumps(rows)))])
        tasks = [t for t in by_task if "총괄" not in t]
        overview.append(f"- {group} {dept}: {', '.join(tasks[:6]) or '업무 총괄'}")
        print(f"{doc_id} {dept} ({group}) | 업무 {len(by_task)}개 | 대표 {lead}")
    missing = [d for d, r in all_rows.items() if not r]
    text = "\n".join(overview)
    save("ORG-000", snap, "source.json", json.dumps(all_rows, ensure_ascii=False).encode("utf-8"),
         dict(doc_id="ORG-000", title="여수광양항만공사 조직도", source_url=url, fetched_at=fetched, empty_departments=missing),
         text, [chunk("ORG-000", "여수광양항만공사 조직도", url, snap, fetched, t, "department", "조직도", i, 1, sha(text))
                for i, t in enumerate(pack("여수광양항만공사 조직도", text), 1)])
    print(f"ORG-000 조직도 | 부서 {len(structure)}개, 업무 목록 없는 부서 {missing}")
    return contacts


def update_contacts(new: list[dict]):
    data = json.loads(CONTACTS.read_text(encoding="utf-8"))
    kept = [c for c in data["contacts"] if not c["key"].startswith(("page-", "dept-"))]
    data["contacts"] = kept + new
    data["generated_by"] = "scripts/21_extract_contacts.py, scripts/25_collect_ygpa_org_hinterland.py (page-·dept- 항목)"
    CONTACTS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main():
    now = datetime.now(timezone.utc)
    snap, fetched = now.strftime("%Y%m%dT%H%M%S%fZ"), now.isoformat()
    contacts = collect_pages(snap, fetched) + collect_org(snap, fetched)
    update_contacts(contacts)
    print(f"contacts.json: page-·dept- 항목 {len(contacts)}개")


if __name__ == "__main__":
    main()
