"""YGPA 공식 사이트의 공개 메뉴를 같은 규칙으로 수집한다 (원본만 저장, 청크는 29번).

왜: 지금 색인은 사이트 일부(문서 76건)뿐이다. FAQ를 보고 문서를 고르면 분리 규칙(evaluation_boundary 2번) 위반이므로,
특정 질문이 아니라 '공개 메뉴 전체 + 아래 제외 규칙'으로 대상을 정한다. 대상과 제외 사유는 site_collection_v1.json에 남긴다.

- 안내 페이지: 사이트 메뉴(goSubMenu)와 페이지 안 링크에서 찾은 contPageDetail 페이지 (한·영·일·중)
- 게시판: BOARDS 표의 게시판만, 최신 글부터 limit개. 첨부는 files=True인 게시판만
- 본문 이미지·alt 글자, 페이지 첨부도 저장
- FAQ 경로·bbs_no=230 차단. 리다이렉트는 대상이 차단 목록이 아닐 때만 한 번 따라간다
- 받은 첨부의 SHA-256이 FAQ 첨부와 같으면 저장하지 않는다 (FAQ 첨부는 복사본 포함 평가 전용)
- 403을 주는 곳은 우회하지 않고 건너뛴다. 요청 간격 0.7초

  python scripts/28_collect_site.py plan      # 대상 목록 만들기 (docs/contracts/site_collection_v1.json)
  python scripts/28_collect_site.py collect   # 원본 수집 (data/raw). 이미 받은 문서는 건너뛴다
"""
import hashlib
import html
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag import dense  # noqa: E402

HOST = "https://www.ygpa.or.kr"
USER_AGENT = "YGPA-Capstone/0.3"
PLAN = ROOT / "docs/contracts/site_collection_v1.json"
POLICY = json.loads((ROOT / "docs/contracts/data_separation_policy.json").read_text(encoding="utf-8"))
FAQ_DIR = ROOT / "evaluation/private/ygpa_faq"

# 게시판: (이름, 경로, 최신 글 수, 첨부 저장 여부). 없는 게시판 제외 사유는 BOARD_EXCLUDED
BOARDS = {
    198: ("용어사전", "/hmpg/ygpa/port/know/dict", 290, False),
    184: ("월별 물동량 처리실적", "/hmpg/ygpa/info/puda/mopr", 13, True),
    426: ("화물 주요 통계", "/hmpg/ygpa/port/gymg/stat", 3, True),
    340: ("컨테이너 서비스 현황", "/hmpg/ygpa/port/gymg/ctsr", 2, True),
    186: ("여천 선석 운영 방침", "/hmpg/ygpa/port/gymg/ber2", 3, True),
    396: ("주요 규제 개선 사례", "/hmpg/ygpa/mwse/regu/reim", 8, False),
    397: ("기업 애로 처리 실적", "/hmpg/ygpa/mwse/regu/erpr", 20, False),
    386: ("적극행정 우수사례", "/hmpg/ygpa/mwse/actv/atev", 9, False),
    195: ("보도해명", "/hmpg/ygpa/comu/news/prss", 19, False),
    373: ("중소기업 지원 프로그램", "/hmpg/ygpa/esgm/bspg", 20, False),
    536: ("공공기술나눔", "/hmpg/ygpa/comu/publ", 5, False),
    515: ("안전경영책임보고서", "/hmpg/ygpa/esgm/safe/plan", 1, True),
    378: ("인권경영 이행지침", "/hmpg/ygpa/esgm/humn/hufu", 1, True),
    516: ("재난위기 대응매뉴얼", "/hmpg/ygpa/esgm/disa/dipl", 1, True),
    189: ("재난 안전 자료실", "/hmpg/ygpa/esgm/disa/dida", 10, True),
    180: ("CEO와의 대화", "/hmpg/ygpa/ygpa/yceo/ceod", 7, False),
    511: ("발간물", "/hmpg/ygpa/ygpa/prom/publ", 1, True),
    512: ("지속가능경영보고서", "/hmpg/ygpa/esgm/esgb", 2, True),
    416: ("카드뉴스", "/hmpg/ygpa/comu/news/card", 35, False),
    191: ("공지사항", "/hmpg/ygpa/comu/noti", 30, False),
    213: ("공사뉴스", "/hmpg/ygpa/comu/news/anuc", 40, False),
    182: ("부서별 주요계획", "/hmpg/ygpa/info/inop/depl", 3, True),
}
BOARD_EXCLUDED = {
    "230": "FAQ, 최종평가 전용",
    "177·356·520": "사용자 글 게시판",
    "409": "403 응답, 우회하지 않음",
    "사전정보공표·경영공시 세부": "업무추진비·계약·재무 등 행정 공시. 항만 이용 안내와 무관하고 양이 많아 검색을 흐림",
    "535·188 선석·정박지": "매일 바뀌는 현황. 색인하면 곧 틀린 정보가 됨",
    "275·391 공고·채용": "기한이 짧은 공고",
}
PAGE_SKIP = re.compile(r"/memb/|/faqs/|bbs_no=230\b|srchListPage|RegistForm|rsvtCalendar|rsvtListPage|fileDownLoad|/info/bein/in\d\d/|"
                       r"/orga/|/addi/copy|/comu/wbpp|/comu/ctpp|ListPage|List\.do|Page\.do|\.(pdf|hwp|zip|jpg|png)$", re.I)
CONT = re.compile(r"/hmpg/(ygpa|engl|japn|chin|cplx|clst)/.*contPageDetail\.do\?conts_no=([0-9A-F]{32})")
LANG = {"ygpa": "ko", "cplx": "ko", "clst": "ko", "engl": "en", "japn": "ja", "chin": "zh"}
FIRST_ID = {"ko": 100, "en": 300, "ja": 400, "zh": 500}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = build_opener(NoRedirect)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blocked(path: str) -> bool:
    return dense.is_blocked(urljoin(HOST, path), POLICY) or "/faqs/" in path


def fetch(path: str, data: dict | None = None) -> tuple[bytes, str, str]:
    """(본문, 최종 경로, Content-Disposition). 리다이렉트는 차단 대상이 아니면 한 번 따라간다"""
    if blocked(path):
        raise PermissionError(f"차단 경로: {path}")
    body = urlencode(data).encode() if data is not None else None
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["X-Requested-With"] = "XMLHttpRequest"
    for _ in range(2):
        try:
            for attempt in range(3):  # 2026-11-02 이 PC에서 DNS 조회가 잠깐씩 실패함(getaddrinfo) → 잠시 뒤 다시
                try:
                    r = OPENER.open(Request(urljoin(HOST, path), data=body, headers=headers), timeout=60)
                    break
                except URLError as e:
                    if isinstance(e, HTTPError) or attempt == 2:
                        raise
                    time.sleep(10 * (attempt + 1))
            with r:
                raw = r.read()
                time.sleep(0.7)
                return raw, path, r.headers.get("Content-Disposition", "")
        except HTTPError as e:
            if e.code in (301, 302, 303) and e.headers.get("Location"):
                target = e.headers["Location"]
                u = urlparse(urljoin(HOST, target))
                if u.hostname != "www.ygpa.or.kr" or blocked(target):
                    raise PermissionError(f"리다이렉트 차단: {target}")
                path = u.path + ("?" + u.query if u.query else "")
                continue
            raise
    raise RuntimeError(f"리다이렉트가 계속됨: {path}")


def existing_conts() -> set[str]:
    text = json.dumps(POLICY) + (ROOT / "scripts/25_collect_ygpa_org_hinterland.py").read_text(encoding="utf-8")
    return set(re.findall(r"conts_no=([0-9A-F]{32})", text))


def menu_links(raw: str) -> set[str]:
    found = {html.unescape(m) for m in re.findall(r"""goSubMenu\('(/hmpg/[^']+)'""", raw)}
    return found | {html.unescape(m) for m in re.findall(r'href="(/hmpg/[^"#]+)"', raw)}


def page_title(raw: str) -> str:
    m = re.search(r"(?s)<title>(.*?)</title>", raw)
    parts = [p.strip() for p in html.unescape(m.group(1)).split("<")] if m else []
    parts = [p for p in parts if p and "항만공사" not in p and "Port Authority" not in p and "港湾公社" not in p and "港务公社" not in p]
    return " — ".join(reversed(parts[:3])) if parts else ""


def plan():
    have, seen, targets, skipped = existing_conts(), set(), {}, []
    roots = ["/hmpg/ygpa/main.do", "/hmpg/engl/main.do", "/hmpg/japn/main.do", "/hmpg/chin/main.do", "/hmpg/cplx/main.do"]
    todo = list(roots)
    while todo:
        path = todo.pop(0)
        if path in seen:
            continue
        seen.add(path)
        try:
            raw = fetch(path)[0].decode("utf-8", "replace")
        except Exception as e:
            skipped.append({"url": path, "reason": f"조회 실패 {type(e).__name__}: {str(e)[:60]}"})
            continue
        m = CONT.search(path)
        if m and m.group(2) not in have:
            targets[m.group(2)] = {"path": path, "lang": LANG[m.group(1)], "title": page_title(raw)}
        for link in sorted(menu_links(raw)):
            if link not in seen and not blocked(link) and CONT.search(link) and not PAGE_SKIP.search(link.split("?")[0]) and "/info/bein/in" not in link:
                todo.append(link)
    next_id, docs = dict(FIRST_ID), []
    for t in sorted(targets.values(), key=lambda x: (FIRST_ID[x["lang"]], x["path"])):
        doc_id = f"YGPA-{next_id[t['lang']]}"
        next_id[t["lang"]] += 1
        docs.append({"doc_id": doc_id, "kind": "page", **t})
    PLAN.write_text(json.dumps({
        "version": "1.0", "created_at": datetime.now(timezone.utc).isoformat(),
        "rule": "공개 메뉴 전체에서 아래 제외 규칙만 뺀다. FAQ 내용을 보고 고르지 않는다.",
        "page_skip_pattern": PAGE_SKIP.pattern, "boards": {str(k): {"name": v[0], "limit": v[2], "files": v[3]} for k, v in BOARDS.items()},
        "boards_excluded": BOARD_EXCLUDED, "pages": docs, "page_failures": skipped,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"안내 페이지 {len(docs)}개, 조회 실패 {len(skipped)}개 → {PLAN.relative_to(ROOT)}")


def save_raw(doc_id: str, snap: str, name: str, raw: bytes, meta: dict):
    out = ROOT / "data/raw" / doc_id / snap
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_bytes(raw)
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def done(doc_id: str) -> bool:
    return (ROOT / "data/raw" / doc_id).exists()


def main_html(raw: str) -> str:
    """본문 영역만 (이미지·첨부 찾기용). 메뉴의 이미지·링크를 줍지 않게"""
    m = re.search(r'(?s)<div class="contents">(.*?)(?:담당자 만족도 평가|<footer|class="footer-contents)', raw)
    return m.group(1) if m else ""


def images_of(fragment: str) -> list[dict]:
    out = []
    for tag in re.findall(r"(?is)<img\b[^>]*>", fragment):
        src = re.search(r'(?i)\bsrc="([^"]+)"', tag)
        alt = re.search(r'(?i)\balt="([^"]*)"', tag)
        if src and not re.search(r"(?i)(icon|ico_|btn|bullet|arrow|sns|/common/)", src.group(1)):
            out.append({"src": html.unescape(src.group(1)), "alt": html.unescape(alt.group(1)).strip() if alt else ""})
    return out


def faq_hashes() -> set[str]:
    hashes = set()
    for f in FAQ_DIR.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".pdf", ".hwp", ".hwpx", ".xlsx"):
            hashes.add(sha(f.read_bytes()))
    for z in FAQ_DIR.glob("*.zip"):
        with zipfile.ZipFile(z) as a:
            hashes |= {sha(a.read(n)) for n in a.namelist() if n.lower().endswith((".pdf", ".hwp"))}
    return hashes


def filename(disposition: str, fallback: str) -> str:
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition)
    if not m:
        return fallback
    name = m.group(1)
    try:
        from urllib.parse import unquote
        name = unquote(name)
        name = name.encode("latin-1").decode("utf-8")
    except (UnicodeError, ValueError):
        pass
    return name


def collect_attachment(file_no: str, label: str, parent: str, snap: str, faq: set[str], log: dict) -> dict | None:
    doc_id = "YGPA-F" + sha(file_no.encode())[:10].upper()
    if done(doc_id):
        return {"doc_id": doc_id, "label": label}
    try:
        raw, _, disp = fetch(f"/hmpg/comm/file/fileDownLoad.do?file_no={file_no}")
    except Exception as e:
        log["file_errors"].append(f"{file_no}: {e}")
        return None
    digest = sha(raw)
    if digest in faq:
        log["faq_duplicates"] += 1
        return None
    name = filename(disp, label)
    head = raw[:8]
    suffix = Path(name).suffix.lower() or (".pdf" if head[:4] == b"%PDF" else ".bin")
    if suffix not in (".pdf", ".hwp", ".hwpx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".docx", ".pptx"):
        log["file_skipped"].append(name)
        return None
    url = f"{HOST}/hmpg/comm/file/fileDownLoad.do?file_no={file_no}"
    save_raw(doc_id, snap, f"source{suffix}", raw, dict(
        doc_id=doc_id, title=Path(name).stem or label, file_name=name, source_url=url, parent_source_url=urljoin(HOST, parent),
        fetched_at=datetime.now(timezone.utc).isoformat(), source_sha256=digest, size=len(raw)))
    return {"doc_id": doc_id, "label": name}


def collect_document(doc: dict, snap: str, faq: set[str], log: dict, files: bool = True):
    doc_id, path = doc["doc_id"], doc["path"]
    if done(doc_id):
        return
    try:
        raw, final, _ = fetch(path)
    except Exception as e:
        log["page_errors"].append(f"{doc_id} {path[:70]}: {e}")
        return
    text = raw.decode("utf-8", "replace")
    frag = main_html(text)
    images = images_of(frag)
    attachments = []
    if files:
        seen = set()
        for no, label in re.findall(r'(?s)fileDownLoad\.do\?file_no=([\w-]+)[^>]*>(.*?)</a>', frag):
            if no not in seen:
                seen.add(no)
                item = collect_attachment(no, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", label)).strip(), final, snap, faq, log)
                if item:
                    attachments.append(item)
    meta = dict(doc_id=doc_id, title=doc.get("title") or page_title(text), lang=doc["lang"], kind=doc["kind"], board=doc.get("board"),
                source_url=urljoin(HOST, path), final_url=urljoin(HOST, final), fetched_at=datetime.now(timezone.utc).isoformat(),
                source_sha256=sha(raw), images=images, attachments=attachments, date=doc.get("date", ""))
    out = save_raw(doc_id, snap, "source.html", raw, meta)
    for i, im in enumerate(images):
        src = im["src"]
        if src.startswith("data:"):
            continue
        try:
            if not src.startswith("http"):
                src = urljoin(HOST + final, src)
            if urlparse(src).hostname != "www.ygpa.or.kr":
                continue
            blob, _, _ = fetch(urlparse(src).path + ("?" + urlparse(src).query if urlparse(src).query else ""))
        except Exception as e:
            log["image_errors"] += 1
            continue
        folder = out / "images"
        folder.mkdir(exist_ok=True)
        ext = Path(urlparse(src).path).suffix.lower() or ".jpg"
        (folder / f"{i:03d}{ext}").write_bytes(blob)
        im["file"] = f"images/{i:03d}{ext}"
        im["sha256"] = sha(blob)
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def board_posts(no: int, base: str, limit: int) -> list[dict]:
    posts, page = [], 1
    while len(posts) < limit:
        r = fetch(f"{base}/bordContListPgng.do", {"bbs_no": str(no), "miv_pageNo": str(page), "miv_pageSize": "10", "listType": "list"})[0].decode("utf-8", "replace")
        ids = re.findall(r"contDetail\('([^']+)'\)", r)
        if not ids:
            break
        fresh = [i for i in dict.fromkeys(ids) if i not in {p["pst"] for p in posts}]
        if not fresh:
            break
        posts += [{"pst": i} for i in fresh]
        page += 1
    return posts[:limit]


def collect():
    plan_data = json.loads(PLAN.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    snap = now.strftime("%Y%m%dT%H%M%S%fZ")
    faq = faq_hashes()
    print("FAQ 첨부 해시", len(faq), flush=True)
    log = dict(page_errors=[], file_errors=[], file_skipped=[], image_errors=0, faq_duplicates=0, boards={})
    for i, doc in enumerate(plan_data["pages"], 1):
        collect_document(doc, snap, faq, log)
        if i % 25 == 0:
            print(f"페이지 {i}/{len(plan_data['pages'])}", flush=True)
    serial = 1000
    for no, (name, base, limit, files) in BOARDS.items():
        try:
            posts = board_posts(no, base, limit)
        except Exception as e:
            log["page_errors"].append(f"게시판 {no}: {e}")
            continue
        log["boards"][name] = len(posts)
        for p in posts:
            doc_id = f"YGPA-B{no}-{sha(p['pst'].encode())[:8].upper()}"
            collect_document({"doc_id": doc_id, "kind": "board_post", "board": name, "lang": "ko",
                              "path": f"{base}/bordContDetail.do?bbs_no={no}&pst_no={p['pst']}"}, snap, faq, log, files)
        print(f"게시판 {name} {len(posts)}건", flush=True)
    (ROOT / "data/catalog/site_collection_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in log.items()})


# ---------- 여수지방해양수산청: 입출항·항만 이용의 실제 소관 기관 ----------
MOF_HOST = "https://yeosu.mof.go.kr"
# 항만시설현황·항만통계·항만이용안내·항행안전·해운/안전·행동요령·광양항컨테이너부두·해운항만 업체. 어업·등대체험·정보공개는 제외
MOF_RANGES = [(3834, 3843), (3853, 3884), (3905, 3925), (3930, 3933), (3984, 3991), (4157, 4157), (4890, 4890)]


def in_mof_scope(idx: int) -> bool:
    return any(a <= idx <= b for a, b in MOF_RANGES)


def mof_slice(raw: str) -> str:
    """본문 영역만 (전체 페이지는 4MB). 메뉴 글자가 섞이지 않게"""
    m = re.search(r'(?s)class="sub-content".*?(?=class="satis-cont")', raw)
    return m.group(0) if m else ""


def mof_get(url: str) -> bytes:
    with build_opener().open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as r:
        data = r.read()
    time.sleep(0.7)
    return data


def collect_mof():
    menu = mof_get(f"{MOF_HOST}/ko/page.do?menuIdx=3853").decode("utf-8", "replace")
    # 하위 탭은 메뉴에 없고 번호만 이어진다 → 범위 안 번호를 모두 조회한다. 이미 받은 문서는 건너뜀
    todo = sorted({*(i for a, b in MOF_RANGES for i in range(a, b + 1)),
                   *(int(i) for i in re.findall(r"page\.do\?menuIdx=(\d+)", menu) if in_mof_scope(int(i)))})
    todo = [i for i in todo if not done(f"MOF-{i}")]
    now = datetime.now(timezone.utc)
    snap, done_ids, empty = now.strftime("%Y%m%dT%H%M%S%fZ"), set(), []
    while todo:
        idx = todo.pop(0)
        if idx in done_ids:
            continue
        done_ids.add(idx)
        url = f"{MOF_HOST}/ko/page.do?menuIdx={idx}"
        try:
            raw = mof_get(url).decode("utf-8", "replace")
        except Exception as e:
            print("실패", idx, e)
            continue
        part = mof_slice(raw)
        crumbs = re.search(r"(?s)<title>(.*?)</title>", raw)
        title = html.unescape(crumbs.group(1)).strip() if crumbs else str(idx)
        title = " — ".join(p.strip() for p in title.split(" - ")[1:] or [title])
        if len(re.sub(r"<[^>]+>|\s", "", part)) < 40 and "<img" not in part:
            empty.append(idx)
            continue
        doc_id = f"MOF-{idx}"
        images = images_of(part)
        for i, im in enumerate(images):
            if im["src"].startswith("data:"):
                continue
            try:
                blob = mof_get(urljoin(MOF_HOST, im["src"]))
            except Exception:
                continue
            folder = ROOT / "data/raw" / doc_id / snap / "images"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{i:03d}.png").write_bytes(blob)
            im["file"], im["sha256"] = f"images/{i:03d}.png", sha(blob)
        save_raw(doc_id, snap, "source.html", part.encode("utf-8"), dict(
            doc_id=doc_id, title=f"여수지방해양수산청 {title}", lang="ko", kind="page", publisher="여수지방해양수산청", source_url=url, final_url=url,
            fetched_at=datetime.now(timezone.utc).isoformat(), source_sha256=sha(part.encode()), images=images, attachments=[]))
        print(doc_id, title[:40], len(part), "이미지", len(images), flush=True)
    print("수집", len(done_ids) - len(empty), "빈 페이지", empty)


if __name__ == "__main__":
    {"plan": plan, "collect": collect, "mof": collect_mof}[sys.argv[1]]()
