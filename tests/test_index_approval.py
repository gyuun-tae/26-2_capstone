"""26번 승인 판정과 dense.apply_approvals 오프라인 확인 (네트워크 없음)."""
import hashlib
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag import dense  # noqa: E402

spec = importlib.util.spec_from_file_location("review", ROOT / "scripts/26_review_index_approval.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

POLICY = {"blocked_path_prefixes": ["/hmpg/ygpa/comu/faqs/"], "blocked_query_values": {"bbs_no": ["230"]}}
OK = (True, "오늘 원문과 같음")


def chunk(**kw):
    text = kw.pop("text", "제1조(목적) 이 규정은")
    base = dict(chunk_id="YGPA-031-x", doc_id="YGPA-031", source_url="https://www.ygpa.or.kr/hmpg/comm/file/a",
                text=text, chunk_text_sha256=hashlib.sha256(text.encode()).hexdigest(), source_snapshot="S2",
                chunk_kind="article", review_flags=["currentness_not_verified"], date_status="unverified_attachment")
    return base | kw


class DecideTest(unittest.TestCase):
    def test_approved_when_current(self):
        self.assertEqual(r.decide(chunk(), OK, "S2", POLICY), ("approved", []))

    def test_held_when_source_changed_or_unchecked(self):
        self.assertEqual(r.decide(chunk(), (False, "첨부 파일이 바뀜"), "S2", POLICY), ("held", ["첨부 파일이 바뀜"]))
        self.assertEqual(r.decide(chunk(), None, "S2", POLICY)[0], "held")

    def test_held_when_not_latest_snapshot_or_hash_mismatch(self):
        self.assertEqual(r.decide(chunk(), OK, "S3", POLICY)[0], "held")
        self.assertEqual(r.decide(chunk(chunk_text_sha256="0" * 64), OK, "S2", POLICY)[0], "held")

    def test_excluded(self):
        faq = chunk(source_url="https://www.ygpa.or.kr/hmpg/ygpa/comu/faqs/bordContDetail.do?bbs_no=230")
        self.assertEqual(r.decide(faq, OK, "S2", POLICY)[0], "excluded")
        self.assertEqual(r.decide(chunk(chunk_kind="historical_addendum"), OK, "S2", POLICY)[0], "excluded")
        self.assertEqual(r.decide(chunk(doc_id="YGPA-019"), OK, "S2", POLICY)[0], "excluded")

    def test_notes_and_unknown_flags(self):
        status, notes = r.decide(chunk(review_flags=["time_limited_items"], date_status="conflicting"), OK, "S2", POLICY)
        self.assertEqual(status, "approved_with_notes")
        self.assertEqual(len(notes), 2)
        self.assertEqual(r.decide(chunk(review_flags=["new_flag"]), OK, "S2", POLICY)[0], "held")
        self.assertEqual(r.decide(chunk(source_url="https://example.com/x"), OK, "S2", POLICY)[0], "held")


class ApplyApprovalsTest(unittest.TestCase):
    def ledger(self, status="approved", sha=None, days=1):
        c = chunk()
        checked = datetime.now(timezone.utc) - timedelta(days=days)
        return c, {"policy_version": "1.0", "checked_at": checked.isoformat(),
                   "chunks": {c["chunk_id"]: {"status": status, "chunk_text_sha256": sha or c["chunk_text_sha256"], "notes": []}}}

    def test_approved_and_stale(self):
        c, led = self.ledger()
        self.assertTrue(dense.apply_approvals([c], led)[0]["index_approved"])
        c, led = self.ledger(sha="0" * 64)  # 다시 청킹돼 본문이 바뀜
        self.assertEqual(dense.apply_approvals([c], led)[0]["review_status"], "stale_approval")
        c, led = self.ledger(status="held")
        self.assertFalse(dense.apply_approvals([c], led)[0]["index_approved"])
        self.assertEqual(dense.apply_approvals([chunk(chunk_id="other")], led)[0]["review_status"], "not_reviewed")

    def test_expired_ledger_stops(self):
        c, led = self.ledger(days=31)
        with self.assertRaises(ValueError):
            dense.apply_approvals([c], led)


if __name__ == "__main__":
    unittest.main()
