"""작게 찾고 크게 넘기기 (small-to-big): 긴 조문을 항(①②…) 단위 자식 청크로 나눠 검색에만 쓴다.

벡터 하나는 청크 전체의 평균이라, 항이 여럿인 긴 조문은 한 항만 묻는 질문과 점수가 낮다.
예: LAW-010 제9조(1,507자)의 ⑤ "감면율이 가장 높은 한 가지 사유만 적용" (h12, docs/handoff/31_answer_gate.md).
자식은 색인에만 들어가고, 검색에서 자식이 걸리면 부모 조문 전체를 근거로 넘긴다 (src/api/app/search.py).
자식은 부모에서 만들어지므로 부모의 승인 상태를 그대로 따른다 (승인된 부모에서만 만든다).

- 자식 머리는 조문 제목 "제○조(…)"만 붙인다. PDF에서 온 YGPA 규정은 ①이 제목과 같은 줄에 있어, 줄 머리 기준으로
  자르면 ①항 전체가 모든 자식 머리에 들어가 아무 질문에나 걸리는 청크가 됐다 (YGPA-032 제3조).
- MIN_PART자보다 짧은 항은 앞 항에 붙인다. "⑦ 제5항에 따른 증표에 관한 사항은 …으로 정한다" 같은 한 줄 항이
  낱말 몇 개("출입", "증표")만으로 출입증 질문에 걸렸다.
docs/handoff/32_small_to_big.md
"""
import hashlib
import re

MIN_CHARS = 800  # 이보다 긴 조문만 나눈다
MIN_PARTS = 2
MIN_PART = 0  # 이보다 짧은 항은 앞 항에 붙인다 (150은 h12 ⑤항 같은 짧은 정답 항을 묻어 버려 쓰지 않음)
KINDS = {"article"}  # 조문만. 표·서식·웹 페이지는 항 표시가 있어도 나누지 않는다
DOC_PREFIXES = ("LAW-",)  # 법령만. YGPA 규정(PDF) 제3조 "사용하려면 사장에게 신청" 같은 일반 신청 문장 항이 질문 10여 개에 끼어들었다
PART_KIND = "article_part"
MARK = re.compile(r"(?:^|(?<=\s))[①-⑳]", re.M)  # 줄 머리나 공백 뒤의 항 번호
TITLE = re.compile(r"^\s*제\s*\d+\s*조(?:의\s*\d+)?\s*\([^)\n]*\)")


def split(chunk: dict) -> list[dict]:
    """나눌 대상이면 자식 청크 목록, 아니면 빈 목록. 자식 본문 = 조문 제목 + 항 하나(짧은 항은 앞 항과 함께)"""
    text = chunk["text"]
    if chunk.get("chunk_kind") not in KINDS or not chunk["doc_id"].startswith(DOC_PREFIXES) or len(text) <= MIN_CHARS:
        return []
    starts = [m.start() for m in MARK.finditer(text)]
    if len(starts) < MIN_PARTS:
        return []
    title = TITLE.match(text)
    head = " ".join(title.group(0).split()) if title else ""
    pieces = [text[a:b].strip() for a, b in zip(starts, starts[1:] + [len(text)])]
    merged = []
    for p in pieces:
        if merged and len(p) < MIN_PART:
            merged[-1] += "\n" + p
        else:
            merged.append(p)
    if len(merged) < MIN_PARTS:
        return []
    parts = []
    for n, body in enumerate(merged, 1):
        body = f"{head}\n{body}" if head else body
        parts.append({**chunk, "chunk_id": f"{chunk['chunk_id']}#p{n}", "parent_chunk_id": chunk["chunk_id"],
                      "chunk_kind": PART_KIND, "text": body,
                      "chunk_text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()})
    return parts


def add(chunks: list[dict]) -> list[dict]:
    """부모 청크 + 자식 청크 (부모는 그대로 남겨 넓은 질문은 부모가 잡게 한다)"""
    return chunks + [p for c in chunks for p in split(c)]
