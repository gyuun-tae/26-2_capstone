"""법령·고시의 서식(별지) 중 민원인이 작성·제출하는 서식을 서식 하나 = 청크 하나로 만든다. 네트워크를 쓰지 않는다.

23번은 서식을 뺐다(빈 신청서 양식은 본문 검색에 도움이 안 됨). 그런데 "출입 신고서는 어디서 받아요?"처럼 서식 자체를 묻는
질문에는 서식 이름·근거 조문·내려받을 주소가 있어야 답할 수 있다. 그래서 서식 전문(상자 문자 표 수천 자) 대신
이름·근거 조문·온라인 신청 안내·작성 항목 앞부분만 짧게 넣는다. 다운로드 버튼은 서식 HWP 파일(국가법령정보센터).

입력: data/raw/LAW-xxx/<최신 스냅샷>/source.json, metadata.json (22번)
출력: data/chunks/LAW-xxx/<스냅샷>/law-forms-v1/chunks.jsonl, manifest.json, review.md (서식이 있는 문서만)
넣는 서식: 민원인이 작성·제출하는 서식. 이름이 증·증명서·통지서·지정서 등으로 끝나는 기관 발급 문서와
          삭제된 서식은 뺀다(manifest에 기록).

  python scripts/27_chunk_law_forms.py
"""
import html
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "law-forms-v1"
spec = importlib.util.spec_from_file_location("chunk_laws", ROOT / "scripts/23_chunk_laws.py")
laws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(laws)

ISSUED = re.compile(r"(증|증명서|지정서|통지서|독촉장|승인서|수첩|대장)$")  # 이것으로 끝나면 기관이 내주는 문서
BOX = re.compile(r"[┏┓┗┛┣┫┠┨┳┻╋╂━─┯┷┼├┤┬┴│┃┌┐└┘┝┥┿■□▣◆◇※]")
# 서식 머리에 있는 온라인 신청 안내: "항만운영정보시스템(www.portmis.go.kr)에서도 신청할 수 있습니다"
ONLINE = re.compile(r"([가-힣]*(?:시스템|민원|포털))\s*\(((?:https?://)?[\w.-]+\.(?:go|or)\.kr[^)]*)\)\s*에서도")
URL_PIECE = re.compile(r"\S*\.(?:go|or)\.kr[^\s가-힣]*(?:\s*에서도\s*신청할\s*수\s*있습니다\.?)?")
HEADER = re.compile(r"^.{0,80}?\[별지[^\]]*\]\s*(?:<[^>]*>)?\s*")
FIELDS_CHARS = 700  # 작성 항목 앞부분만. 서식 전문은 다운로드로 본다


def form_label(b: dict) -> str:
    """'별지 제1호서식', '별지 제1호의2서식' (번호·가지번호에서 만든다)"""
    number, branch = int(b["별표번호"]), int(b.get("별표가지번호") or 0)
    return f"별지 제{number}호" + (f"의{branch}" if branch else "") + "서식"


def is_submitted(title: str) -> bool:
    """제출 서식인가. 이름이 증·통지서 등으로 끝나면(영문 병기는 떼고) 기관이 내주는 문서다 — '신고확인증'처럼
    신고라는 말이 있어도. 다만 '위험물적재검사증(신청서)'처럼 괄호로 신청서임을 밝히면 제출 서식"""
    korean = re.sub(r"[A-Za-z\s]+$", "", title)
    return not ISSUED.search(korean)


def flat(text: str) -> str:
    """상자 문자를 지우고 공백을 하나로 (두 단 배치가 섞여도 단어는 남는다)"""
    return re.sub(r"\s+", " ", BOX.sub(" ", text)).strip()


def online_note(text: str) -> str:
    """서식 머리의 온라인 신청 안내. 서식에 적힌 주소(www.portmis.go.kr)는 이미 닫힌 옛 주소라(410) 답변에 새지 않게
    주소 대신 시스템 이름만 남긴다. 항만운영정보시스템 = Port-MIS (Port-MIS 버튼은 근거에 'Port-MIS'가 있어야 붙는다)"""
    m = ONLINE.search(text)
    if not (m and "수 있습니다" in text):
        return ""
    name, address = m.groups()
    system = f"{name}(Port-MIS)" if "portmis" in address else name
    return f"{system}에서도 신청할 수 있습니다."


def citing_articles(found: list[dict], label: str) -> list[str]:
    """이 서식을 정한 조문 ('별지 제1호서식에 따른 …'). 제1호서식이 제1호의2서식·제10호서식에 걸리지 않게 앞뒤를 막는다"""
    number = re.escape(label.removeprefix("별지 ").removesuffix("서식"))
    pattern = re.compile(rf"별지\s*{number.replace('제', '제\\s*')}\s*서식")
    out = []
    for a in found:
        text = "\n".join([a["head"]] + [line for u in a["units"] for line in u])
        if pattern.search(text):
            out.append(f"{a['label']}({a['title']})" if a["title"] else a["label"])
    return out


def forms(source: dict) -> tuple[list[dict], dict]:
    body = source.get("법령") or source["AdmRulService"]
    found, excluded = [], {"issued_documents": [], "deleted": [], "not_form": 0}
    for b in laws.as_list((body.get("별표") or {}).get("별표단위")):
        if b.get("별표구분") not in ("서식", "별지"):
            excluded["not_form"] += b.get("별표구분") != "별표"  # 도식(표찰 그림) 등
            continue
        title = re.sub(r"\s+", " ", html.unescape(b.get("별표제목", ""))).strip()
        label = form_label(b)
        if laws.DELETED_ANNEX.match(title):
            excluded["deleted"].append(label)
            continue
        if not is_submitted(title):
            excluded["issued_documents"].append(f"{label} {title}")
            continue
        link = b.get("별표서식파일링크") or ""
        if not link.startswith("/"):
            raise ValueError(f"{label} {title}: 서식 파일 주소가 없습니다")
        text = "\n".join(line for group in laws.as_list(b.get("별표내용")) for line in laws.as_list(group))
        found.append(dict(key=f"form-{b['별표키']}", label=label, title=title, text=text,
                          url=f"https://www.law.go.kr{link}", effective=b.get("별표시행일자", "")))
    return found, excluded


def form_text(meta: dict, f: dict, cited: list[str]) -> str:
    body = flat(f["text"])
    # 머리 줄("■ 법령명 [별지 제1호서식] <개정 …>")과 제목은 위에 따로 쓰므로 작성 항목은 그 뒤부터.
    # 두 단 배치라 제목 글자 사이에 공백이 끼거나 빠질 수 있다
    fields = HEADER.sub("", body, count=1)
    title = re.compile(r"\s*".join(map(re.escape, f["title"].replace(" ", ""))))
    if m := title.search(fields[:400]):
        fields = fields[m.end():].strip()
    # 두 단 배치로 잘린 주소 조각("ortmis.go.kr)에서도 신청할 수 있습니다.")은 뺀다 — 온라인 안내는 위 줄에서만
    fields = URL_PIECE.sub("", fields).strip()
    fields = fields if len(fields) <= FIELDS_CHARS else fields[:FIELDS_CHARS].rstrip() + " …"
    lines = [f"[{f['label']}] {f['title']}",
             f"「{meta['title']}」 {f['label']}. 서식 파일(HWP)은 국가법령정보센터에서 내려받을 수 있습니다."]
    if cited:
        lines.append(f"근거 조문: {', '.join(cited)}")
    if note := online_note(body):
        lines.append(f"온라인 신청: {note}")
    lines.append(f"작성 항목(앞부분): {fields}")
    return "\n".join(lines)


def build(meta: dict, source: dict, source_bytes: bytes) -> tuple[list[dict], dict, str]:
    info = laws.basic_info(source)
    articles, _ = laws.articles(source)
    found, excluded = forms(source)
    base = dict(
        doc_id=meta["doc_id"], document_version=laws.sha(source_bytes), source_snapshot=meta["source_snapshot"],
        extraction_version=laws.EXTRACTION, title=meta["title"], parent_source_url=meta["source_url"],
        publisher=info["publisher"], fetched_at=meta["fetched_at"], published_at=laws.iso(info["published"]),
        updated_at="", effective_at=laws.iso(info["effective"]), date_status="official_api_current",
        date_evidence="국가법령정보 Open API 현행 본문의 공포(발령)일자·시행일자",
    )
    chunks = []
    for f in found:
        text = form_text(meta, f, citing_articles(articles, f["label"]))
        name = f"[{f['label']}] {f['title']}"
        chunks.append(dict(
            base,
            chunk_id=f"{meta['doc_id']}-" + laws.sha(f"{meta['serial']}|{f['key']}|form")[:24],
            chunking_version=VERSION, source_url=f["url"], section_titles=[name], text=text,
            chunk_text_sha256=laws.sha(text), chunk_kind="whole_form", form_title=f["title"],
            source_locator=dict(kind="law_api", law_name=meta["title"], serial=meta["serial"], article_key=f["key"],
                                article_label=name, part=1, part_count=1),
            review_status="draft_pending_chunk_review", index_approved=False, review_flags=[],
        ))
    document = "\n\n".join(c["text"] for c in chunks)
    base.update(text_sha256=laws.sha(document))
    for c in chunks:
        c["text_sha256"] = base["text_sha256"]
    manifest = dict(
        doc_id=meta["doc_id"], title=meta["title"], source_snapshot=meta["source_snapshot"],
        document_version=laws.sha(source_bytes), chunking_version=VERSION, serial=meta["serial"],
        effective_at=laws.iso(info["effective"]), form_count=len(found), chunk_count=len(chunks),
        excluded=excluded, index_approved=False,
    )
    return chunks, manifest, document


def save(chunks: list[dict], manifest: dict) -> str:
    lines = [f"# {manifest['doc_id']} {manifest['title']} 서식 청크 검토",
             f"검색 승인 전 초안. 서식 {manifest['form_count']}개 → 청크 {manifest['chunk_count']}개. "
             f"제외: 기관 발급 문서 {len(manifest['excluded']['issued_documents'])}개, 삭제 {len(manifest['excluded']['deleted'])}개."]
    lines += [f"## {c['section_titles'][0]}\n{c['source_url']}\n\n{c['text']}" for c in chunks]
    outputs = {"chunks.jsonl": "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks),
               "review.md": "\n\n".join(lines) + "\n"}
    expected = {**manifest, "output_hashes": {k: laws.sha(v) for k, v in outputs.items()}}
    out = ROOT / "data/chunks" / manifest["doc_id"] / manifest["source_snapshot"] / VERSION
    if (out / "manifest.json").exists():
        old = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        if all(old.get(k) == v for k, v in expected.items()):
            return "그대로"
        raise ValueError(f"{out}의 기존 청크와 다릅니다. 덮어쓰지 않습니다 (규칙을 바꿨다면 VERSION을 올리세요)")
    out.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        (out / name).write_text(text, encoding="utf-8")
    created = {**expected, "created_at": laws.datetime.now(laws.timezone.utc).isoformat()}
    (out / "manifest.json").write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
    return "생성"


def main():
    for doc in sorted((ROOT / "data/raw").glob("LAW-*")):
        snap = sorted(p for p in doc.iterdir() if (p / "source.json").exists())[-1]  # 23번과 같은 최신 스냅샷
        meta = json.loads((snap / "metadata.json").read_text(encoding="utf-8"))
        source_bytes = (snap / "source.json").read_bytes()
        chunks, manifest, _ = build(meta, json.loads(source_bytes), source_bytes)
        if not chunks:
            continue
        ex = manifest["excluded"]
        print(f"{meta['doc_id']} {meta['title']} | 서식 → 청크 {manifest['chunk_count']} | 제외 발급문서 "
              f"{len(ex['issued_documents'])}·삭제 {len(ex['deleted'])} | {save(chunks, manifest)}")


if __name__ == "__main__":
    main()
