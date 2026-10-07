"""청크(chunks.jsonl 한 줄) → 화면용 근거(Source)·서식 다운로드(Action) 변환. 4단계 제안 초안.

검색 담당은 청크를 가공하지 않고 그대로 넘기고, 화면용 문구는 여기 한 곳에서 만든다.
규칙 설명: docs/contracts/rag_interface_proposal.md
"""
import re

from app.schemas import Action, Source

SNIPPET_LEN = 150

# 처리 과정에서 붙인 설명 줄 (사용자에게 보여줄 내용이 아님)
META_LINE = re.compile(r"^(행·열 번호는|표 좌표는|표 YGPA-\S+ \(|표 밖 안내:)")
_HTML_CELL = re.compile(r"^- 행 \d+, 열 \d+ \[([^\]]+)\]: ")  # "- 행 2, 열 1 [구분]: 축구장" → "구분: 축구장"
_HWP_CELL = re.compile(r"^행 \d+~\d+, 열 \d+~\d+: ")  # "행 1~1, 열 1~2: 접수번호" → "접수번호"
_ARTICLE = re.compile(r"\s*(제\s*\d+\s*조(?:의\s*\d+)?\s*(?:\([^)]{0,40}\))?)")
_ANNEX = re.compile(r"[〔\[【]\s*(별지\s*\d+)")


def _pdf_pages(chunk: dict) -> list[int]:
    refs = chunk["source_locator"].get("source_refs", [])
    return sorted({r["locator"]["page_number"] for r in refs if r["locator"]["kind"] == "pdf_page"})


def locator_text(chunk: dict) -> str:
    """화면에 보여줄 근거 위치 문구. 원래 위치 객체(source_locator)는 청크에 그대로 남는다."""
    loc, titles = chunk["source_locator"], chunk.get("section_titles") or []
    if loc["kind"] == "processed_text":
        return " · ".join(titles) or "본문"
    if loc["kind"] == "html_table":
        return f"{titles[0]} 표" if titles else "표"
    if loc["kind"] == "law_api":  # 법령·고시 조문 (scripts/23_chunk_laws.py)·서식 (27)
        return loc["article_label"] + (" · 서식 전체" if chunk.get("chunk_kind") == "whole_form" else "")

    kind = chunk.get("chunk_kind")
    if kind == "whole_form":
        return "서식 전체"
    if kind == "article" and (m := _ARTICLE.match(chunk["text"])):
        label = re.sub(r"\s+", "", m.group(1))  # "제 5 조 (사용허가)" → "제5조(사용허가)"
    elif kind == "table" and (m := _ANNEX.search(chunk["text"])):
        label = re.sub(r"\s+", "", m.group(1))  # "별지1"
    else:
        label = re.sub(r"\s+", " ", titles[0]).replace("부 칙", "부칙") if titles else "첨부 본문"

    pages = _pdf_pages(chunk)
    if not pages:
        return label
    span = f"{pages[0]}쪽" if len(pages) == 1 else f"{pages[0]}~{pages[-1]}쪽"
    return f"{label} · {span}"


def snippet_text(chunk: dict) -> str:
    """근거 발췌문: 설명 줄을 빼고 표 셀은 '머리글: 값'만 남겨 앞부분을 자른다."""
    lines = []
    for i, line in enumerate(chunk["text"].splitlines()):
        line = line.strip()
        if not line or META_LINE.match(line) or (i == 0 and line == chunk.get("title")):
            continue
        line = _HWP_CELL.sub("", _HTML_CELL.sub(r"\1: ", line))
        lines.append(line)
    text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    return text if len(text) <= SNIPPET_LEN else text[:SNIPPET_LEN].rstrip() + "…"


def chunk_to_source(chunk: dict) -> Source:
    return Source(
        doc_id=chunk["doc_id"],
        chunk_id=chunk["chunk_id"],
        title=chunk["title"],
        source_url=chunk["source_url"],
        locator=locator_text(chunk),
        published_at=chunk.get("published_at") or None,  # 빈 문자열 → null. 수집일로 채우지 않는다
        updated_at=chunk.get("updated_at") or None,
        date_status=chunk["date_status"],
        effective_at=chunk.get("effective_at") or None,
        fetched_at=chunk.get("fetched_at") or None,
        snippet=snippet_text(chunk),
    )


def form_download(chunk: dict, source_ref: int) -> Action | None:
    """서식 청크면 원문 다운로드 버튼을 만든다. URL은 청크 메타데이터에서만 가져온다 (LLM이 만들지 않음)."""
    if chunk.get("chunk_kind") != "whole_form":
        return None
    fmt = "PDF" if _pdf_pages(chunk) else "HWP"
    name = chunk.get("form_title") or chunk["title"]  # 법령 서식은 title이 법령 이름이라 서식 이름을 따로 둔다
    return Action(type="download", label=f"{name}({fmt})", url=chunk["source_url"], source_ref=source_ref)
