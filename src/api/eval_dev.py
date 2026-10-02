"""개발용 질문 묶음으로 실제 RAG(GPU 서버 + Neon)를 측정한다. 대화 로그는 남기지 않는다. FAQ(최종 평가용)는 쓰지 않는다.

실행: uv run python eval_dev.py [--label 이름] [--only a01,c01]
입력: evaluation/datasets/dev_questions_v1.jsonl   결과: evaluation/reports/dev_eval_<날짜>_<이름>.json
설정은 try_real.py와 같다 (저장소 루트 .env).

항목 (질문마다):
- 검색: 기대 문서 중 하나가 상위 5개 근거에 있는가 (unknown 기대 질문은 제외)
- 유형: answer/clarify/unknown이 허용 목록에 있는가
- 버튼: 필수 서식이 모두 있고, 허용 밖 서식이 없고, Port-MIS 여부가 맞는가 (port_mis가 null이면 상관없음)
- 언급: must_mention의 단어가 답에 모두 있는가 (예: 이용 제한 공지)
- 근거 번호 없는 줄, 규칙 위반(URL·전화·이메일, 없는 번호), 근거에 없는 숫자(환각 위험), 첫 글자·전체 시간
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import statistics
import time

import try_real  # noqa: F401  (.env를 읽고 앱 모듈을 불러온다)
from app import rag_real, search
from app.actions import PORT_MIS
from app.prompt import CONTACT, uncited_lines, violations
from app.schemas import Message

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evaluation/datasets/dev_questions_v1.jsonl"


NUMBER = re.compile(r"\d[\d,.]*")


def unsupported_numbers(text: str, evidence: str) -> list[str]:
    """답에 나온 숫자 중 근거 글에 없는 것 (환각 위험 지표). 근거 번호 [n]과 목록 번호 "1."은 뺀다"""
    body = re.sub(r"\[\d+\]", " ", text)
    body = re.sub(r"(?m)^\s*\d+\.\s", " ", body)
    plain = evidence.replace(",", "")
    found = []
    for n in NUMBER.findall(body):
        n = n.rstrip(".,")
        if n and n not in evidence and n.replace(",", "") not in plain:
            found.append(n)
    return found


async def run_one(item: dict) -> dict:
    hits = []
    original = search.search

    def recording(vector, k):  # 조립 코드가 실제로 받은 검색 결과를 기록 (unknown이면 sources가 비므로)
        hits[:] = original(vector, k)
        return hits

    search.search = recording
    try:
        messages = [Message(**m) for m in item.get("history", [])] + [Message(role="user", content=item["question"])]
        start, first, pieces = time.perf_counter(), None, []
        result = rag_real.answer(messages)
        async for piece in result.tokens:
            first = first or time.perf_counter() - start
            pieces.append(piece)
        total = time.perf_counter() - start
    finally:
        search.search = original

    text = "".join(pieces)
    docs = [h["chunk"]["doc_id"] for h in hits]
    evidence = "\n".join(h["chunk"]["text"] + " " + h["chunk"]["title"] for h in hits)
    numbers = unsupported_numbers(text, evidence) if result.answer_type == "answer" else []
    contacts = CONTACT.findall(text)
    unverified = [c for c in contacts if c.rstrip(".,") not in evidence]
    found = violations(text, len(hits)) if result.answer_type == "answer" else []
    if "url_or_phone" in found and not unverified:  # 근거에 글자 그대로 있는 연락처는 위반으로 세지 않는다
        found.remove("url_or_phone")
    downloads = [result.sources[a.source_ref - 1].doc_id for a in result.actions if a.type == "download"]
    port_mis = any(a.url == PORT_MIS.url for a in result.actions)
    contacts = [f"{a.label} {a.phone}" for a in result.actions if a.type == "contact"]

    checks = {"type": result.answer_type in item["expect_type"]}
    if item["expect_docs"]:
        checks["retrieval"] = any(d in docs for d in item["expect_docs"])
        checks["retrieval@1"] = bool(docs) and docs[0] in item["expect_docs"]  # 1위가 기대 문서인가 (순서 품질)
    if item.get("must_mention"):  # 꼭 알려야 하는 내용 (예: 이용 제한 공지)
        checks["mention"] = all(any(alt in text for alt in word.split("|")) for word in item["must_mention"])  # "a|b" = 둘 중 하나
    allowed = set(item["forms_allowed"]) | set(item["forms_required"])
    if result.answer_type == "unknown":  # 확인 불가면 대표전화 버튼으로 다음 행동을 안내해야 한다
        checks["contact"] = any("대표전화" in c for c in contacts)
    checks["buttons"] = (set(item["forms_required"]) <= set(downloads) and set(downloads) <= allowed
                         and (item["port_mis"] is None or port_mis == item["port_mis"]))
    return {"id": item["id"], "group": item["group"], "question": item["question"], "answer_type": result.answer_type,
            "top1_score": round(hits[0]["score"], 3) if hits else None, "top_docs": docs, "downloads": downloads,
            "port_mis": port_mis, "contacts": contacts, "options": [o.label for o in result.options], "uncited_lines": len(uncited_lines(text)),
            "violations": found, "contacts_from_evidence": len(contacts) - len(unverified), "unsupported_numbers": numbers,
            "first_token_s": round(first or total, 2), "total_s": round(total, 2), "checks": checks, "answer": text.strip()}


def summarize(rows: list[dict]) -> dict:
    def rate(key, rows=rows):
        vals = [r["checks"][key] for r in rows if key in r["checks"]]
        return f"{sum(vals)}/{len(vals)}"

    groups = sorted({r["group"] for r in rows})
    firsts = [r["first_token_s"] for r in rows]
    return {
        "retrieval": rate("retrieval"), "retrieval@1": rate("retrieval@1"), "type": rate("type"), "buttons": rate("buttons"), "mention": rate("mention"), "contact": rate("contact"),
        "type_by_group": {g: rate("type", [r for r in rows if r["group"] == g]) for g in groups},
        "uncited_lines_total": sum(r["uncited_lines"] for r in rows if r["answer_type"] == "answer"),
        "violations_total": sum(len(r["violations"]) for r in rows),
        "unsupported_numbers_total": sum(len(r["unsupported_numbers"]) for r in rows),
        "first_token_s": {"mean": round(statistics.mean(firsts), 2), "median": round(statistics.median(firsts), 2),
                          "max": max(firsts)},
    }


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", default="run")
    ap.add_argument("--only", help="쉼표로 구분한 id만 실행")
    ap.add_argument("--dataset", default=DATASET.name, help="evaluation/datasets 안의 파일 이름")
    args = ap.parse_args()

    dataset = DATASET.parent / args.dataset
    items = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.only:
        items = [i for i in items if i["id"] in args.only.split(",")]
    rows = []
    for item in items:
        r = await run_one(item)
        rows.append(r)
        failed = [k for k, ok in r["checks"].items() if not ok]
        print(f"{r['id']} {'OK ' if not failed else '실패'} {r['answer_type']:<7} 1위 {r['top1_score']} "
              f"첫 {r['first_token_s']}초 | {r['question']}" + (f"  ← {', '.join(failed)}" if failed else ""))

    summary = summarize(rows)
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=1))
    out = ROOT / f"evaluation/reports/dev_eval_{datetime.now():%Y%m%d}_{args.label}.json"
    out.write_text(json.dumps({"dataset": dataset.name, "index_version": os.getenv("INDEX_VERSION"),
                               "run_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "rows": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", out.relative_to(ROOT))


if __name__ == "__main__":
    asyncio.run(main())
