"""faq_answers.py 결과(V1·V2)를 평가 팀원용 엑셀 한 파일로 합친다. 정답 열은 넣지 않는다 (원본 CSV와 대조).

실행: uv run --with openpyxl python faq_to_xlsx.py --date 20261022
결과: evaluation/private/ygpa_faq/FAQ_V1_V2_답변_<날짜>.xlsx
"""
import argparse
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[2]
FAQ = ROOT / "evaluation/private/ygpa_faq"
TYPES = {"answer": "답변", "clarify": "되묻기", "unknown": "확인 불가", "error": "오류"}
NOTES = {"F22": "F23과 질문이 같음", "F23": "F22와 질문이 같음"}


def load(version: str, date: str) -> tuple[dict, dict]:
    lines = [json.loads(x) for x in (FAQ / f"answers_{version}_{date}.jsonl").read_text(encoding="utf-8").splitlines()]
    return lines[0], {r["id"]: r for r in lines[1:]}


def cell_answer(r: dict) -> str:
    extra = [f"선택지: {', '.join(r['options'])}"] if r["options"] else []
    extra += [f"버튼 {b}" for b in r["buttons"]]
    return r["answer"] + ("\n\n" + "\n".join(extra) if extra else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    (m1, v1), (m2, v2) = load("v1", args.date), load("v2", args.date)
    questions = [json.loads(x) for x in (FAQ / "faq_questions.jsonl").read_text(encoding="utf-8").splitlines()]

    wb = Workbook()
    ws = wb.active
    ws.title = "답변"
    head = ["번호", "FAQ 번호", "질문", "V1 유형", "V1 답변", "V1 근거", "V2 유형", "V2 답변", "V2 근거",
            "V1 점수", "V2 점수", "평가 메모", "비고"]
    widths = [7, 8, 36, 10, 70, 40, 10, 70, 40, 9, 9, 30, 30]
    ws.append(head)
    for q in questions:
        a, b = v1.get(q["id"]), v2.get(q["id"])
        row = [q["id"], q["faq_no"], q["question"]]
        for r in (a, b):
            row += ([TYPES.get(r["answer_type"], r["answer_type"]), cell_answer(r), "\n".join(r["sources"])]
                    if r else ["(없음)", "", ""])
        ws.append(row + ["", "", "", NOTES.get(q["id"], "")])
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for c in ws[1]:
        c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="DDEBF7")
    ws.freeze_panes = "D2"

    info = wb.create_sheet("설정")
    for line in [
        ("V1", "홈페이지 청크만 (법령 조문·법령 서식 제외, 재정렬·답변 전 판정 끔)"),
        ("V2", "현재 실서비스 설정 (홈페이지 + 법령, 재정렬·답변 전 판정 켬)"),
        ("공통", "생성 모델 Qwen3-32B-AWQ, 임베딩 BGE-M3, 색인 " + m1["index_version"]),
        ("V1 환경값", json.dumps(m1["env"], ensure_ascii=False)),
        ("V2 환경값", json.dumps(m2["env"], ensure_ascii=False)),
        ("코드 커밋", f"V1 {m1['commit']} / V2 {m2['commit']}"),
        ("실행 시각(UTC)", f"V1 {m1['run_at']} / V2 {m2['run_at']}"),
        ("유형", "답변 = 근거로 답함, 되묻기 = 선택지를 주고 다시 물음, 확인 불가 = 근거 없음 안내 + 대표전화"),
        ("근거", "답변 화면에 보이는 근거 목록 ([n]은 답변 속 인용 번호). 확인 불가면 비어 있음"),
        ("주의", "질문 열만 사용했고 정답(홈페이지 답변)은 열람하지 않음. 한 번씩 실행한 결과라 같은 질문도 다시 물으면 표현이 조금 다를 수 있음"),
        ("주의", "FAQ 원문은 오래된 내용이 있을 수 있음. 챗봇은 현재 홈페이지 기준으로 답함"),
    ]:
        info.append(line)
    info.column_dimensions["A"].width, info.column_dimensions["B"].width = 16, 110

    out = FAQ / f"FAQ_V1_V2_답변_{args.date}.xlsx"
    wb.save(out)
    print("저장:", out.relative_to(ROOT), f"(V1 {len(v1)}개, V2 {len(v2)}개, 질문 {len(questions)}개)")


if __name__ == "__main__":
    main()
