"""연락처 버튼 (v0.2 actions의 contact). 번호는 contacts.json에서만 가져온다 — LLM이 만들지 않는다.

contacts.json은 scripts/21_extract_contacts.py가 수집한 공식 페이지에서 뽑는다 (대표전화, 서식 담당, 시설 문의).
"""
import json
from pathlib import Path

from app.schemas import Action

_DATA = json.loads((Path(__file__).with_name("contacts.json")).read_text(encoding="utf-8"))["contacts"]


def _action(c: dict) -> Action:
    return Action(type="contact", label=c["label"], phone=c["phone"], note=c.get("note"))


MAIN = _action(next(c for c in _DATA if c["key"] == "main"))


def for_docs(doc_ids: list[str]) -> list[Action]:
    """문서들의 담당 연락처 (문서 순서대로, 같은 이름·번호는 한 번만)"""
    out, seen = [], set()
    for doc_id in doc_ids:
        for c in _DATA:
            if doc_id in c["doc_ids"] and (c["label"], c["phone"]) not in seen:
                seen.add((c["label"], c["phone"]))
                out.append(_action(c))
    return out
