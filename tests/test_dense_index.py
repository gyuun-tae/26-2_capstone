"""개발용 dense 색인·검색 규칙 시험. 합성 청크와 가짜 임베딩만 쓰며 모델을 내려받지 않는다."""
from pathlib import Path
import sys, tempfile, unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from rag import dense  # noqa: E402

ev = __import__("17_search_eval")
POLICY = {"blocked_path_prefixes": ["/hmpg/ygpa/comu/faqs/"], "blocked_query_values": {"bbs_no": ["230"]}}
WORDS = ["입항", "체육", "출입증", "부칙"]


def chunk(cid, doc, text, kind=None, url="https://www.ygpa.or.kr/a"):
    return {"chunk_id": cid, "doc_id": doc, "title": doc, "section_titles": ["절"], "text": text,
            "chunk_text_sha256": f"h-{text}", "source_url": url, "chunk_kind": kind}


def fake_encode(texts):
    """단어가 들어 있으면 그 칸이 1인 벡터 (뜻이 같으면 같은 방향)"""
    return [[float(w in t) + 0.01 for w in WORDS] for t in texts]


CHUNKS = [chunk("a", "D1", "입항 신고 절차"), chunk("b", "D2", "체육시설 예약"),
          chunk("c", "D3", "출입증 분실"), chunk("d", "D4", "부칙 시행일", kind="historical_addendum")]


class DenseIndexTest(unittest.TestCase):
    def test_select_excludes_addendum(self):
        kept, excluded = dense.select(CHUNKS, POLICY)
        self.assertEqual([c["chunk_id"] for c in kept], ["a", "b", "c"])
        self.assertEqual(excluded, {"historical_addendum": 1})

    def test_select_stops_on_evaluation_source(self):
        for url in ["https://www.ygpa.or.kr/hmpg/ygpa/comu/faqs/x", "https://www.ygpa.or.kr/b?bbs_no=230"]:
            with self.assertRaises(ValueError):
                dense.select([chunk("f", "F", "x", url=url)], POLICY)

    def test_build_stops_over_token_limit(self):
        with self.assertRaises(ValueError):
            dense.build(CHUNKS[:1], fake_encode, count_tokens=lambda t: dense.MAX_TOKENS + 1)

    def test_search_returns_closest_chunk_unchanged(self):
        kept, _ = dense.select(CHUNKS, POLICY)
        vectors, tokens = dense.build(kept, fake_encode, count_tokens=len)
        hits = dense.search(fake_encode(["체육 이용"])[0], vectors, kept, k=2)
        self.assertIs(hits[0]["chunk"], kept[1])  # 가공하지 않은 같은 객체
        self.assertGreaterEqual(hits[0]["score"], hits[1]["score"])
        self.assertEqual(len(tokens), 3)

    def test_index_version_tracks_model_and_text(self):
        v = dense.index_version("rev1", CHUNKS)
        self.assertNotEqual(v, dense.index_version("rev2", CHUNKS))
        self.assertNotEqual(v, dense.index_version("rev1", [chunk("a", "D1", "바뀐 본문")] + CHUNKS[1:]))

    def test_save_load_detects_tampering(self):
        kept, _ = dense.select(CHUNKS, POLICY)
        vectors, _ = dense.build(kept, fake_encode, count_tokens=len)
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            dense.save(folder, vectors, kept, {"index_version": "t"})
            loaded, chunks, _ = dense.load(folder)
            self.assertEqual([c["chunk_id"] for c in chunks], ["a", "b", "c"])
            dense.np.save(folder / "vectors.npy", loaded * 2)
            with self.assertRaises(ValueError):
                dense.load(folder)

    def test_evaluate_ranks_by_document(self):
        kept, _ = dense.select(CHUNKS, POLICY)
        vectors, _ = dense.build(kept, fake_encode, count_tokens=len)
        questions = [{"doc_id": "D1", "question": "입항"}, {"doc_id": "D3", "question": "체육"}]
        summary, rows = ev.evaluate(questions, lambda q: fake_encode([q])[0], vectors, kept, k=2)
        self.assertEqual([r["rank"] for r in rows], [1, None])
        self.assertEqual(summary["hit@1"], 0.5)
        self.assertEqual(summary["mrr@5"], 0.5)


if __name__ == "__main__":
    unittest.main()
