"""긴 조문 → 항 단위 자식 청크 규칙 시험 (src/rag/parts.py)"""
from pathlib import Path
import sys, unittest, unittest.mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag import parts  # noqa: E402

TAIL = "⑤ 둘 이상의 감면사유에 해당하는 때에는 감면율이 가장 높은 한 가지 사유만을 적용하여 감면한다." + "다" * 120
LONG = ("제9조(사용료의 면제범위 등)\n① " + "가" * 400 + "\n② " + "나" * 350 + "\n1. 호 목록도 그 항에 붙는다\n" + TAIL)


def chunk(text, kind="article", cid="LAW-010-x"):
    return {"chunk_id": cid, "doc_id": "LAW-010", "title": "규정", "section_titles": ["제9조"], "text": text,
            "chunk_text_sha256": "parent", "chunk_kind": kind}


class PartsTest(unittest.TestCase):
    def test_split_long_article_by_paragraph(self):
        got = parts.split(chunk(LONG))
        self.assertEqual([p["chunk_id"] for p in got], ["LAW-010-x#p1", "LAW-010-x#p2", "LAW-010-x#p3"])
        self.assertTrue(all(p["parent_chunk_id"] == "LAW-010-x" and p["chunk_kind"] == parts.PART_KIND for p in got))
        # 자식마다 조문 제목만 머리로 붙인다
        self.assertTrue(all(p["text"].startswith("제9조(사용료의 면제범위 등)\n") for p in got))
        self.assertIn("1. 호 목록도 그 항에 붙는다", got[1]["text"])
        self.assertIn("가장 높은 한 가지 사유만을 적용", got[2]["text"])
        self.assertNotIn("가" * 10, got[2]["text"])
        self.assertEqual(len({p["chunk_text_sha256"] for p in got}), 3)
        self.assertEqual(got[0]["title"], "규정")  # 나머지 필드는 부모 그대로

    def test_short_paragraph_joins_previous_when_enabled(self):
        text = "제87조(타인 토지에의 출입 등)\n① " + "가" * 500 + "\n② " + "나" * 300 + "\n③ 증표에 관한 사항은 부령으로 정한다."
        with unittest.mock.patch.object(parts, "MIN_PART", 150):
            got = parts.split(chunk(text))
        self.assertEqual(len(got), 2)
        self.assertTrue(got[1]["text"].endswith("③ 증표에 관한 사항은 부령으로 정한다."))

    def test_pdf_layout_marker_on_title_line(self):
        """PDF 규정: ①이 제목과 같은 줄. ①항 본문이 다른 자식 머리에 들어가면 안 된다 (YGPA-032 제3조)"""
        text = ("제3조(항만시설의 사용승낙 등)     ①  법 제29조에 따라 " + "가" * 300 + "\n" + "가" * 100 +
                "\n  ②  사장은 " + "나" * 300 + "\n  ③  " + "다" * 200)
        got = parts.split(chunk(text, cid="LAW-x"))
        self.assertEqual(len(got), 3)
        self.assertTrue(all(p["text"].startswith("제3조(항만시설의 사용승낙 등)\n") for p in got))
        self.assertNotIn("법 제29조", got[1]["text"])
        self.assertNotIn("법 제29조", got[2]["text"])

    def test_skip_short_other_kinds_and_single_paragraph(self):
        self.assertEqual(parts.split(chunk("제1조(목적)\n① 짧음\n② 짧음")), [])
        self.assertEqual(parts.split(chunk(LONG, kind="annex")), [])
        self.assertEqual(parts.split(chunk(LONG, kind="whole_form")), [])
        self.assertEqual(parts.split(chunk("제2조(정의)\n① " + "가" * 900)), [])
        # YGPA 규정은 나누지 않는다 (법령만)
        self.assertEqual(parts.split({**chunk(LONG), "doc_id": "YGPA-032"}), [])

    def test_add_keeps_parents(self):
        short = chunk("제1조(목적)\n① 짧음", cid="s")
        got = parts.add([chunk(LONG), short])
        self.assertEqual([c["chunk_id"] for c in got[:2]], ["LAW-010-x", "s"])
        self.assertEqual(len(got), 5)


if __name__ == "__main__":
    unittest.main()
