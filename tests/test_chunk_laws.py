"""23_chunk_laws.py 오프라인 확인: 합성 API 응답만 쓴다 (네트워크·인증값 불필요)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts/23_chunk_laws.py"
spec = importlib.util.spec_from_file_location("chunk_laws", MODULE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

META = dict(doc_id="LAW-900", title="시험법", target="law", serial="111", source_url="https://www.law.go.kr/법령/x",
            fetched_at="2026-10-03T00:00:00+00:00", source_snapshot="20261003T000000000000Z")
LAW = {"법령": {
    "기본정보": {"소관부처": {"content": "해양수산부"}, "공포일자": "20260101", "시행일자": "20260227"},
    "부칙": {"부칙단위": [{"부칙내용": "부칙 1"}, {"부칙내용": "부칙 2"}]},
    "별표": {"별표단위": [
        {"별표구분": "별표", "별표번호": "0001", "별표가지번호": "00", "별표키": "000100E", "별표제목": "사용료(제7조 관련)",
         "별표서식PDF파일링크": "/LSW/flDownload.do?flSeq=1",
         "별표내용": [["[별표 1]", "사용료(제7조 관련)", "┏━━━┳━━━┓", "┃종류  ┃요율    ┃", "┣━━━╋━━━┫",
                      "┃선박료┃135원   ┃", "┃      ┃(1톤당) ┃", "┃      ┃        ┃", "┗━━━┻━━━┛"]]},
        {"별표구분": "별표", "별표번호": "0002", "별표가지번호": "00", "별표키": "000200E", "별표제목": "좌표", "별표내용": [["x"]]},
        {"별표구분": "서식", "별표번호": "0001", "별표가지번호": "00", "별표키": "000100F", "별표제목": "신청서", "별표내용": [["신청서"]]},
    ]},
    "조문": {"조문단위": [
        {"조문여부": "전문", "조문번호": "1", "조문키": "0001000", "조문내용": "  제1장 총칙 <개정 2010.2.4>"},
        {"조문여부": "조문", "조문번호": "1", "조문키": "0001001", "조문제목": "목적",
         "조문내용": "제1조(목적) 이 법은 시험을 목적으로 한다."},
        {"조문여부": "조문", "조문번호": "2", "조문키": "0002001", "조문제목": "정의",
         "조문내용": "제2조(정의) 뜻은 다음과 같다.",
         "항": {"호": [{"호내용": "1. \"항만\"이란 곳을 말한다."},
                      {"호내용": "2. \"시설\"이란 다음과 같다.",
                       "목": [{"목내용": [["가. 기본시설", "    1) 항로"]]}, {"목내용": "나. 기능시설"}]}]}},
        {"조문여부": "조문", "조문번호": "3", "조문키": "0003001", "조문내용": "제3조 삭제 <2020.1.1>"},
        {"조문여부": "전문", "조문번호": "3", "조문키": "0003000", "조문내용": "제1절 사용"},
        {"조문여부": "조문", "조문번호": "3", "조문가지번호": "2", "조문키": "0003002", "조문제목": "사용",
         "조문내용": "제3조의2(사용)",
         "항": [{"항번호": "①", "항내용": "① " + "가" * 1500}, {"항번호": "②", "항내용": "② " + "나" * 1500}]},
    ]},
}}
ADMRUL = {"AdmRulService": {
    "행정규칙기본정보": {"소관부처명": "해양수산부", "발령일자": "20260821", "시행일자": "20260821"},
    "부칙": {"부칙공포일자": ["20200101"], "부칙내용": [["부칙 <2020.1.1>"]]},
    "조문내용": ["제1조(목적) 이 고시는 시험한다.",
                 "제2조(신고) ① 다음 사항을 신고해야 한다.1. 인적사항(주소 등)2. 사용료3. 그 밖의 사항② 2026.1.1. 이후 적용한다."],
}}


class ChunkLawsTest(unittest.TestCase):
    def test_law_articles(self):
        raw = json.dumps(LAW, ensure_ascii=False).encode()
        chunks, manifest, document = c.build(META, LAW, raw, held={"000200E": "좌표"})
        labels = [x["source_locator"]["article_label"] for x in chunks]
        self.assertEqual(labels, ["제1조(목적)", "제2조(정의)", "제3조의2(사용)", "제3조의2(사용)", "[별표 1] 사용료(제7조 관련)"])
        self.assertEqual(manifest["excluded"], {"deleted_articles": ["제3조"], "addenda": 2, "forms": 1,
                                                "annexes_held": [{"label": "[별표 2]", "title": "좌표", "reason": "좌표"}]})
        self.assertEqual(manifest["split_articles"], ["제3조의2"])
        # 장·절 제목은 개정 표시를 지우고 section_titles에만 둔다
        self.assertEqual(chunks[0]["section_titles"], ["제1장 총칙", "제1조(목적)"])
        self.assertEqual(chunks[2]["section_titles"], ["제1장 총칙", "제1절 사용", "제3조의2(사용)"])
        # 항 번호 없는 호·목은 줄 단위로 펼친다
        self.assertEqual(chunks[1]["text"].splitlines(),
                         ["제2조(정의) 뜻은 다음과 같다.", "1. \"항만\"이란 곳을 말한다.", "2. \"시설\"이란 다음과 같다.",
                          "가. 기본시설", "1) 항로", "나. 기능시설"])
        # 긴 조문은 항 경계에서 나누고 뒤 조각에 머리줄을 붙인다
        self.assertTrue(chunks[3]["text"].startswith("제3조의2(사용) (계속)\n② "))
        self.assertTrue(all(len(x["text"]) <= c.MAX_CHARS for x in chunks))
        self.assertEqual(chunks[0]["source_url"], "https://www.law.go.kr/법령/%EC%8B%9C%ED%97%98%EB%B2%95/%EC%A0%9C1%EC%A1%B0")
        self.assertEqual((chunks[0]["published_at"], chunks[0]["effective_at"]), ("2026-01-01", "2026-02-27"))
        self.assertEqual(len({x["chunk_id"] for x in chunks}), 5)
        # 별표: 테두리 줄과 빈 칸 줄은 지우고 칸막이는 남긴다. 링크는 별표 PDF
        annex = chunks[4]
        self.assertEqual(annex["text"].splitlines(), ["[별표 1] 사용료(제7조 관련)", "┃종류 ┃요율 ┃", "┃선박료┃135원 ┃", "┃ ┃(1톤당) ┃"])
        self.assertEqual((annex["chunk_kind"], annex["source_url"]), ("annex", "https://www.law.go.kr/LSW/flDownload.do?flSeq=1"))
        self.assertFalse(any(x["index_approved"] for x in chunks))
        self.assertNotIn("삭제", document)

    def test_admrul_line_breaks(self):
        meta = dict(META, target="admrul", doc_id="LAW-901")
        chunks, manifest, _ = c.build(meta, ADMRUL, b"x")
        self.assertEqual(chunks[1]["text"].splitlines(),
                         ["제2조(신고)", "① 다음 사항을 신고해야 한다.", "1. 인적사항(주소 등)", "2. 사용료",
                          "3. 그 밖의 사항", "② 2026.1.1. 이후 적용한다."])
        self.assertEqual(chunks[1]["source_url"], META["source_url"])  # 고시는 조문 주소가 없어 전체 주소
        self.assertEqual(manifest["excluded"]["addenda"], 1)

    def test_save_is_idempotent(self):
        chunks, manifest, document = c.build(META, LAW, b"x")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(c.save(root, chunks, manifest, document), "생성")
            self.assertEqual(c.save(root, chunks, manifest, document), "그대로")
            chunks[0] = dict(chunks[0], text="바뀜")
            with self.assertRaises(ValueError):
                c.save(root, chunks, manifest, document)


if __name__ == "__main__":
    unittest.main()
