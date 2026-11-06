"""score_faq.py 시험 — 가짜 골든셋·답변만 쓴다(실제 FAQ 없음).
실행: uv run --no-project --with openpyxl python evaluation/test_score_faq.py
"""
import json
from pathlib import Path
import sys
import tempfile

from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_faq as sf  # noqa: E402


def make_golden(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "골든셋"
    ws.append(["번호", "FAQ 번호", "상태", "정답 문서 ID", "정답 청크 ID", "법령 필요", "제외 사유"])
    ws.append(["F01", 1, "확정", "", "YGPA-001-aaa", "", ""])                    # 문서 ID는 청크에서 채움
    ws.append(["F02", 2, "확정", "LAW-001", "LAW-001-bbb#p2\nYGPA-002-ccc", "Y", ""])  # 자식→부모, 두 개
    ws.append(["F03", 3, "확정", "YGPA-003", "", "", ""])                        # 문서만
    ws.append(["F04", 4, "제외", "", "", "", "현재 자료 없음"])
    ws.append(["F05", 5, "검토 필요", "YGPA-005", "", "", ""])                   # 채점 안 함
    wb.save(path)


def write_answers(path: Path, rows, meta=None):
    meta = meta or {"meta": True, "version": "vT", "index_version": "none"}
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [meta, *rows]), encoding="utf-8")


NEW = [
    {"id": "F01", "answer_type": "answer", "total_s": 4.0, "error": None,
     "searched_chunks": ["YGPA-009-x", "YGPA-001-aaa", "YGPA-001-zzz"], "source_chunks": ["YGPA-009-x", "YGPA-001-aaa"]},
    {"id": "F02", "answer_type": "unknown", "total_s": 2.0, "error": None,
     "searched_chunks": ["YGPA-007-q", "YGPA-008-q", "ORG-001-q", "YGPA-010-q", "LAW-001-bbb#p1", "YGPA-002-ccc"],
     "source_chunks": []},
    {"id": "F03", "answer_type": "answer", "total_s": 10.0, "error": None,
     "searched_chunks": ["YGPA-003-k"], "source_chunks": ["YGPA-003-k"]},
    {"id": "F04", "answer_type": "unknown", "total_s": 1.0, "error": None, "searched_chunks": [], "source_chunks": []},
    {"id": "F05", "answer_type": "answer", "total_s": 6.0, "error": None, "searched_chunks": [], "source_chunks": []},
]
OLD = [  # 11/2 형식: 청크 ID 없이 문자열
    {"id": "F01", "answer_type": "answer", "total_s": 4.0, "error": None,
     "searched": ["YGPA-001 제목 (0.700)"], "sources": ["[1] YGPA-001 제목 · 위치"]},
    {"id": "F02", "answer_type": "answer", "total_s": 3.0, "error": None,
     "searched": ["YGPA-009 제목 (0.6)", "LAW-001 항만법 (0.5)"], "sources": ["[1] YGPA-009 제목"]},
]


def test_helpers():
    assert sf.parent("LAW-001-bbb#p2") == "LAW-001-bbb"
    assert sf.doc_of("YGPA-009-753d") == "YGPA-009"
    assert sf.doc_of("YGPA-009 여수연안여객선터미널 (0.688)") == "YGPA-009"
    assert sf.doc_of("[2] ORG-014 부서 · 위치") == "ORG-014"
    assert sf.split_ids("A-1-x\nB-2-y, C-3-z") == ["A-1-x", "B-2-y", "C-3-z"]
    assert sf.p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]) == 19
    assert sf.mrr([1, 2, None, False]) == f"{(1 + 0.5) / 3:.3f}"


def test_golden_and_scores(tmp: Path):
    make_golden(tmp / "g.xlsx")
    g = sf.load_golden(tmp / "g.xlsx")
    assert g["F01"]["docs"] == {"YGPA-001"} and g["F02"]["chunks"] == {"LAW-001-bbb", "YGPA-002-ccc"}
    assert g["F02"]["law"] and g["F05"]["status"] == "검토 필요"

    s = sf.score_one(NEW[0], g["F01"])
    assert s == {"chunk_rank": 2, "doc_rank": 2, "chunk_shown": True, "doc_shown": True, "chunk_scorable": True}, s
    s = sf.score_one(NEW[1], g["F02"])  # 자식 #p1도 부모로 맞음, unknown이라 근거 없음
    assert s["chunk_rank"] == 5 and s["doc_rank"] == 5 and s["chunk_shown"] is False and s["doc_shown"] is False, s
    s = sf.score_one(NEW[2], g["F03"])  # 정답 청크 없음 → 청크 채점 불가, 문서는 1위
    assert not s["chunk_scorable"] and s["doc_rank"] == 1 and s["doc_shown"] is True, s
    s = sf.score_one(OLD[1], g["F02"])  # 옛 형식은 문서만
    assert not s["chunk_scorable"] and s["doc_rank"] == 2 and s["doc_shown"] is False, s


def test_main(tmp: Path):
    make_golden(tmp / "g.xlsx")
    write_answers(tmp / "new.jsonl", NEW)
    write_answers(tmp / "old.jsonl", OLD, {"meta": True, "version": "v1"})
    out = tmp / "r.xlsx"
    summary = "\n".join(sf.main(["--golden", str(tmp / "g.xlsx"), "--answers", str(tmp / "new.jsonl"),
                                 str(tmp / "old.jsonl"), "--out", str(out)]))
    assert "확정 3 · 제외 1 · 전체 5" in summary
    # 새 형식: 청크는 F01(2위)·F02(5위)만 채점 → hit@1 0/2, hit@3 1/2, hit@5 2/2
    assert "청크 hit@1 0/2 (0.0%) · hit@3 1/2 (50.0%) · hit@5 2/2 (100.0%)" in summary, summary
    assert "문서 hit@1 1/3 (33.3%) · hit@3 2/3 (66.7%) · hit@5 3/3 (100.0%)" in summary, summary
    assert "{'answer': 2, 'unknown': 1}" in summary and "제외 문항 응답 유형 {'unknown': 1}" in summary
    assert "평균 4.60초" in summary and "5초 이내 3/5" in summary   # 시간은 전체 문항(검토 필요 포함)
    # 옛 형식: F03 답변 없음 경고, 청크 지표 줄 없음
    old = summary.split("===== v1")[1]
    assert "옛 형식" in old and "답변 파일에 없는 문항 2개" in old and "청크 hit@" not in old, old
    ws = load_workbook(out)["문항별"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(rows) == 4 + 2 and rows[2][4] == "채점 불가" and rows[3][2] == "제외", rows


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        test_helpers()
        test_golden_and_scores(Path(d))
        test_main(Path(d))
    print("OK")
