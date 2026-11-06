"""FAQ 골든셋 채점기 — 평가팀이 자기 PC에서 실행한다. 개발 담당은 골든셋을 열지 않는다(docs/contracts/evaluation_boundary.md 6번).

실행(저장소 루트):
  uv run --no-project --with openpyxl python evaluation/score_faq.py \
      --golden <FAQ_golden_작업본_v0.xlsx> --answers <answers_v1_….jsonl> [<answers_v2_….jsonl> ...]

입력
- 골든셋: 하나(V1·V2 모두 같은 파일로 채점). '골든셋' 시트. 열 이름으로 읽는다: 번호, 상태, 정답 문서 ID, 정답 청크 ID, 법령 필요, 제외 사유.
  상태 '확정'만 채점, '제외'는 따로 센다. 여러 값은 줄바꿈·쉼표로 구분.
- 답변 파일: src/api/faq_answers.py 결과(jsonl, 첫 줄 meta). 11/2 수집본처럼 청크 ID가 없는 옛 형식이면 문서 단위만 채점한다.

출력
- 화면: 버전별 요약 수치 (검색 적중률, 근거 포함률, 응답 유형, 응답시간)
- 파일: 골든셋과 같은 폴더에 FAQ_채점결과_<날짜>.xlsx (문항별 순위·포함 여부, 답변 본문은 넣지 않음)

지표
- 청크 hit@k / MRR@10: 검색 결과(재정렬 후 생성에 넣은 순서) 안에 정답 청크가 몇 위인지. 항 단위 자식(#p1)은 부모로 합친다.
- 문서 hit@k: 정답 문서 ID 기준. 청크가 바뀌어도 비교할 수 있다.
- 근거 포함률: 화면에 보여준 근거(sources)에 정답 청크(또는 문서)가 있는지. 확인 불가 답은 근거가 비므로 포함 안 됨.
- 응답 유형: 확정 문항 중 answer/unknown/clarify. '확정인데 unknown' = 답할 수 있는데 못 답함.
- 응답시간: 전체 문항. P95는 nearest-rank(⌈0.95n⌉번째 값).
환각·인용 정확도는 사람이 답변 본문을 보고 판정한다(이 스크립트 범위 밖).
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
KS = (1, 3, 5)
SPLIT = re.compile(r"[\n,;]+")
DOC_ID = re.compile(r"^([A-Z]+-\d+)")


def split_ids(value) -> list[str]:
    return [x.strip() for x in SPLIT.split(str(value or "")) if x.strip()]


def parent(chunk_id: str) -> str:
    return chunk_id.split("#", 1)[0]


def doc_of(text: str) -> str | None:
    """'YGPA-009-abc…' · 'YGPA-009 제목 (0.688)' · '[1] YGPA-009 제목' → 'YGPA-009'"""
    m = DOC_ID.match(re.sub(r"^\[\d+\]\s*", "", text.strip()))
    return m.group(1) if m else None


def first_rank(found: list[str], gold: set[str]) -> int | None:
    for i, x in enumerate(found, 1):
        if x in gold:
            return i
    return None


def dedupe(xs):
    return list(dict.fromkeys(x for x in xs if x))


def load_golden(path: Path) -> dict[str, dict]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = iter(list(wb["골든셋"].iter_rows(values_only=True)))
    finally:
        wb.close()  # 읽기 전용은 파일을 잡고 있어서 Windows에서 엑셀로 못 연다
    head = [str(h or "").strip() for h in next(rows)]
    need = ["번호", "상태", "정답 문서 ID", "정답 청크 ID"]
    missing = [h for h in need if h not in head]
    if missing:
        raise SystemExit(f"골든셋 시트에 열이 없습니다: {missing}")
    col = {h: i for i, h in enumerate(head)}
    get = lambda r, h: r[col[h]] if h in col and col[h] < len(r) else None  # noqa: E731
    out = {}
    for r in rows:
        qid = str(get(r, "번호") or "").strip()
        if not qid:
            continue
        chunks = {parent(x) for x in split_ids(get(r, "정답 청크 ID"))}
        docs = set(split_ids(get(r, "정답 문서 ID"))) | {d for d in map(doc_of, chunks) if d}
        out[qid] = {"status": str(get(r, "상태") or "").strip(), "chunks": chunks, "docs": docs,
                    "law": str(get(r, "법령 필요") or "").strip().upper() == "Y",
                    "excluded_reason": str(get(r, "제외 사유") or "").strip()}
    return out


def load_answers(path: Path) -> tuple[dict, list[dict]]:
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = lines[0] if lines and lines[0].get("meta") else {}
    return meta, [x for x in lines if not x.get("meta")]


def index_chunk_ids(version: str | None) -> set[str] | None:
    f = ROOT / "data/index" / str(version) / "chunks.jsonl"
    if not version or not f.exists():
        return None
    return {parent(json.loads(x)["chunk_id"]) for x in f.read_text(encoding="utf-8").splitlines()}


def score_one(a: dict, g: dict) -> dict:
    has_chunks = "searched_chunks" in a
    searched = dedupe(parent(x) for x in a.get("searched_chunks", [])) if has_chunks else []
    shown = dedupe(parent(x) for x in a.get("source_chunks", [])) if has_chunks else []
    s_docs = dedupe(map(doc_of, a.get("searched_chunks") or a.get("searched") or []))
    sh_docs = dedupe(map(doc_of, a.get("source_chunks") or a.get("sources") or []))
    return {
        "chunk_rank": first_rank(searched, g["chunks"]) if has_chunks and g["chunks"] else None,
        "doc_rank": first_rank(s_docs, g["docs"]) if g["docs"] else None,
        "chunk_shown": (bool(set(shown) & g["chunks"]) if has_chunks and g["chunks"] else None),
        "doc_shown": bool(set(sh_docs) & g["docs"]) if g["docs"] else None,
        "chunk_scorable": has_chunks and bool(g["chunks"]),
    }


def rate(xs) -> str:
    xs = [x for x in xs if x is not None]
    return f"{sum(xs)}/{len(xs)} ({sum(xs) / len(xs):.1%})" if xs else "-"


def hits(ranks, k):
    return [None if r is False else (r is not None and r <= k) for r in ranks]


def mrr(ranks) -> str:
    xs = [r for r in ranks if r is not False]
    return f"{sum(1 / r for r in xs if r and r <= 10) / len(xs):.3f}" if xs else "-"


def p95(xs):
    s = sorted(xs)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def summarize(label: str, meta: dict, answers: list[dict], golden: dict, valid: set[str] | None) -> tuple[list[str], list[list]]:
    lines = [f"===== {label}  (색인 {meta.get('index_version', '?')}, 설정 {meta.get('env', {})}, 커밋 {meta.get('commit', '?')})"]
    by_id = {a["id"]: a for a in answers}
    confirmed = [q for q, g in golden.items() if g["status"] == "확정"]
    excluded = [q for q, g in golden.items() if g["status"] == "제외"]
    missing = [q for q in confirmed + excluded if q not in by_id]
    if missing:
        lines.append(f"주의: 답변 파일에 없는 문항 {len(missing)}개 {missing[:10]}")
    if valid is not None:
        bad = sorted({c for q in confirmed for c in golden[q]["chunks"] if c not in valid})
        if bad:
            lines.append(f"주의: 이 색인에 없는 정답 청크 {len(bad)}개 → 해당 문항은 문서 단위로만 맞을 수 있음: {bad[:5]}")
    if answers and "searched_chunks" not in answers[0]:
        lines.append("주의: 옛 형식 답변 파일(청크 ID 없음) → 청크 지표 생략, 문서 단위만")

    rows, per = [], []
    for q in confirmed:
        if q not in by_id:
            continue
        a, g = by_id[q], golden[q]
        s = score_one(a, g)
        rows.append((q, a, g, s))
        per.append([label, q, g["status"], a.get("answer_type"), s["chunk_rank"] if s["chunk_scorable"] else "채점 불가",
                    s["doc_rank"], s["chunk_shown"], s["doc_shown"], "Y" if g["law"] else "", a.get("total_s"), a.get("error") or ""])
    for q in excluded:
        if q in by_id:
            a = by_id[q]
            per.append([label, q, "제외", a.get("answer_type"), "", "", "", "", "", a.get("total_s"), golden[q]["excluded_reason"]])

    lines.append(f"확정 {len(confirmed)}문항(채점 {len(rows)}) · 제외 {len(excluded)}문항 · 답변 파일 {len(answers)}문항")
    c_ranks = [s["chunk_rank"] if s["chunk_scorable"] else False for *_, s in rows]
    d_ranks = [s["doc_rank"] if g["docs"] else False for _, _, g, s in rows]
    if any(r is not False for r in c_ranks):
        lines.append("청크 " + " · ".join(f"hit@{k} {rate(hits(c_ranks, k))}" for k in KS) + f" · MRR@10 {mrr(c_ranks)}")
    lines.append("문서 " + " · ".join(f"hit@{k} {rate(hits(d_ranks, k))}" for k in KS) + f" · MRR@10 {mrr(d_ranks)}")
    lines.append(f"근거 포함률  청크 {rate([s['chunk_shown'] for *_, s in rows])} · 문서 {rate([s['doc_shown'] for *_, s in rows])}")
    law = [(s, g) for _, _, g, s in rows if g["law"]]
    if law:
        lines.append(f"법령 필요 {len(law)}문항  문서 hit@5 {rate(hits([s['doc_rank'] for s, _ in law], 5))}")
    types = {}
    for _, a, _, _ in rows:
        types[a.get("answer_type")] = types.get(a.get("answer_type"), 0) + 1
    lines.append(f"확정 문항 응답 유형 {types}  (unknown = 답할 수 있는데 못 답함)")
    ex_types = {}
    for q in excluded:
        if q in by_id:
            t = by_id[q].get("answer_type")
            ex_types[t] = ex_types.get(t, 0) + 1
    if ex_types:
        lines.append(f"제외 문항 응답 유형 {ex_types}")
    times = [a["total_s"] for a in answers if isinstance(a.get("total_s"), (int, float))]
    if times:
        lines.append(f"응답시간(전체 {len(times)}) 평균 {statistics.mean(times):.2f}초 · 중앙값 {statistics.median(times):.2f} · "
                     f"P95 {p95(times):.2f} · 5초 이내 {rate([t <= 5 for t in times])}")
        for t in ("answer", "unknown", "clarify"):
            xs = [a["total_s"] for a in answers if a.get("answer_type") == t and isinstance(a.get("total_s"), (int, float))]
            if xs:
                lines.append(f"  {t} {len(xs)}개 평균 {statistics.mean(xs):.2f}초")
    errors = [a["id"] for a in answers if a.get("error")]
    if errors:
        lines.append(f"오류 {len(errors)}개 {errors[:10]}")
    return lines, per


def write_xlsx(path: Path, per: list[list], summary: list[str]):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "문항별"
    ws.append(["버전", "번호", "상태", "응답 유형", "정답 청크 순위", "정답 문서 순위", "근거에 정답 청크", "근거에 정답 문서",
               "법령 필요", "응답시간(초)", "오류·제외 사유"])
    for r in per:
        ws.append(["" if x is None else x for x in r])
    ws.freeze_panes = "C2"
    s = wb.create_sheet("요약")
    for line in summary:
        s.append([line])
    s.column_dimensions["A"].width = 160
    wb.save(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--golden", type=Path, required=True)
    ap.add_argument("--answers", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, help="문항별 결과 xlsx (기본: 골든셋 폴더/FAQ_채점결과_<날짜>.xlsx)")
    args = ap.parse_args(argv)

    golden = load_golden(args.golden)
    summary, per = [f"골든셋 {args.golden.name}: 확정 {sum(g['status'] == '확정' for g in golden.values())} · "
                    f"제외 {sum(g['status'] == '제외' for g in golden.values())} · 전체 {len(golden)}"], []
    for path in args.answers:
        meta, answers = load_answers(path)
        label = f"{meta.get('version', '?')} ({path.name})"
        lines, rows = summarize(label, meta, answers, golden, index_chunk_ids(meta.get("index_version")))
        summary += lines
        per += rows
    out = args.out or args.golden.with_name(f"FAQ_채점결과_{datetime.now():%Y%m%d}.xlsx")
    write_xlsx(out, per, summary)
    print("\n".join(summary))
    print("저장:", out)
    return summary


if __name__ == "__main__":
    main()
