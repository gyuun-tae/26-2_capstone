"""27_chunk_law_forms.py 오프라인 확인: 합성 API 응답만 쓴다 (네트워크·인증값 불필요)."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts/27_chunk_law_forms.py"
spec = importlib.util.spec_from_file_location("chunk_law_forms", MODULE)
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)

META = dict(doc_id="LAW-900", title="시험법 시행규칙", target="law", serial="111", source_url="https://www.law.go.kr/법령/x",
            fetched_at="2026-10-07T00:00:00+00:00", source_snapshot="20261007T000000000000Z")


def form(number, branch, title, lines, link="/LSW/flDownload.do?flSeq=9"):
    return {"별표구분": "서식", "별표번호": number, "별표가지번호": branch, "별표키": f"{number}{branch}F",
            "별표제목": title, "별표서식파일링크": link, "별표시행일자": "20241113", "별표내용": [lines]}


SOURCE = {"법령": {
    "기본정보": {"소관부처": {"content": "해양수산부"}, "공포일자": "20240101", "시행일자": "20241113"},
    "별표": {"별표단위": [
        {"별표구분": "별표", "별표번호": "0001", "별표가지번호": "00", "별표키": "000100E", "별표제목": "수수료", "별표내용": [["x"]]},
        form("0001", "00", "내항선 출입 신고서", [
            "■ 시험법 시행규칙 [별지 제1호서식] <개정 2020.   항만운영정보시스템(www.portmis.go.kr)에서도",
            "  5. 7.>                                    신청할 수 있습니다.",
            "┏━━━━━━━━┓", "  내항선 출입 신고서", "┃ 1. 선박 제원 ┃ 선박명: ┃"]),
        form("0001", "02", "승객 명부", ["■ 시험법 시행규칙 [별지 제1호의2서식]", "승객 명부", "성명 국적"]),
        form("0010", "00", "위험물 반입신고서", ["위험물 반입신고서", "신고인"]),
        form("0007", "00", "예선업 등록증", ["등록증"]),
        form("0016", "00", "선용품공급업 신고확인증", ["확인증"]),
        form("0022", "00", "선박 출항 중지 통지서Notice of Departure Suspension", ["통지서"]),
        form("0005", "00", "위험물적재검사증(신청서)", ["신청서"]),
        form("0006", "00", "삭제 &lt;1999.1.9&gt;", []),
    ]},
    "조문": {"조문단위": [
        {"조문여부": "조문", "조문번호": "3", "조문키": "0003001", "조문제목": "선박 출입 신고서 등",
         "조문내용": "제3조(선박 출입 신고서 등)",
         "항": [{"항내용": "① 내항선의 선장은 별지 제1호서식에 따른 내항선 출입신고서에 별지 제1호의2서식에 따른 승객 명부를 첨부하여 제출하여야 한다."}]},
        {"조문여부": "조문", "조문번호": "14", "조문키": "0014001", "조문제목": "위험물 반입의 신고",
         "조문내용": "제14조(위험물 반입의 신고) 별지 제10호서식의 위험물 반입신고서를 제출하여야 한다."},
    ]},
}}


class ChunkLawFormsTest(unittest.TestCase):
    def setUp(self):
        self.chunks, self.manifest, _ = f.build(META, SOURCE, b"source")
        self.by_title = {c["form_title"]: c for c in self.chunks}

    def test_only_submitted_forms(self):
        self.assertEqual(sorted(self.by_title), sorted(["내항선 출입 신고서", "승객 명부", "위험물 반입신고서", "위험물적재검사증(신청서)"]))
        ex = self.manifest["excluded"]
        self.assertEqual(len(ex["issued_documents"]), 3)  # 등록증·신고확인증·통지서(영문 병기)
        self.assertEqual(ex["deleted"], ["별지 제6호서식"])

    def test_form_chunk(self):
        c = self.by_title["내항선 출입 신고서"]
        self.assertEqual(c["chunk_kind"], "whole_form")
        self.assertEqual(c["source_url"], "https://www.law.go.kr/LSW/flDownload.do?flSeq=9")
        self.assertEqual(c["source_locator"]["article_label"], "[별지 제1호서식] 내항선 출입 신고서")
        lines = c["text"].splitlines()
        self.assertEqual(lines[0], "[별지 제1호서식] 내항선 출입 신고서")
        self.assertIn("근거 조문: 제3조(선박 출입 신고서 등)", lines)
        self.assertIn("온라인 신청: 항만운영정보시스템(Port-MIS)에서도 신청할 수 있습니다.", lines)
        self.assertNotIn("┃", c["text"])

    def test_article_reference_does_not_match_neighbours(self):
        # 제1호서식이 제1호의2서식·제10호서식 조문에 잘못 걸리지 않는다
        self.assertEqual(f.citing_articles(f.laws.articles(SOURCE)[0], "별지 제10호서식"), ["제14조(위험물 반입의 신고)"])
        self.assertEqual(f.citing_articles(f.laws.articles(SOURCE)[0], "별지 제1호서식"), ["제3조(선박 출입 신고서 등)"])
        self.assertEqual(f.citing_articles(f.laws.articles(SOURCE)[0], "별지 제1호의2서식"), ["제3조(선박 출입 신고서 등)"])

    def test_no_online_note_without_system(self):
        self.assertFalse(any(line.startswith("온라인") for line in self.by_title["승객 명부"]["text"].splitlines()))


if __name__ == "__main__":
    unittest.main()
