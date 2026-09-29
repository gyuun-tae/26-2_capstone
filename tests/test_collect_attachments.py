"""Offline tests: synthetic responses only; no FAQ content or network requests."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import requests

# Works in the repository and in the preparation directory.
MODULE = Path(__file__).resolve().parents[1] / "scripts/collect_attachments.py"
if not MODULE.exists():
    MODULE = Path(__file__).with_name("collect_attachments.py")
spec = importlib.util.spec_from_file_location("collect_attachments", MODULE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

HOST = "https://www.ygpa.or.kr"
SOURCE = HOST + "/hmpg/comm/file/fileDownLoad.do?file_no=TEST_ATTACHMENT"
PARENT = HOST + "/hmpg/test/document.do?bbs_no=211"
ROW = {"doc_id": "YGPA-021", "title": "Synthetic form", "source_url": SOURCE,
       "parent_source_url": PARENT, "priority": "extension_first_batch"}
POLICY = {"allowed_hosts": ["www.ygpa.or.kr"], "allowed_urls": [SOURCE],
          "allowed_parent_urls": [PARENT], "blocked_path_prefixes": ["/hmpg/ygpa/comu/faqs/"],
          "blocked_query_values": {"bbs_no": ["230"]}, "policy_version": "1.1",
          "follow_links": False, "follow_redirects": False, "require_attachment_provenance": True,
          "catalog_path": "data/catalog/candidates.csv", "attachment_sources": [
              {k: ROW[k] for k in ("doc_id", "source_url", "parent_source_url")}]}
PDF = b"%PDF-1.7\nsynthetic signature fixture\n%%EOF"
HTML = ('<html><a href="' + SOURCE + '">Download</a></html>').encode()


class Response:
    def __init__(self, url, body=b"", status=200, headers=None):
        self.url, self.body, self.status_code = url, body, status
        self.headers = requests.structures.CaseInsensitiveDict(headers or {})
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def iter_content(self, size):
        yield self.body


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if response.url != url:
            raise AssertionError("Unexpected HTTP request")
        return response


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch.object(c.time, "sleep")
        self.sleep.start()
        # Fail tests if any real network call accidentally escapes the fake session.
        self.network = patch.object(requests.Session, "get", side_effect=AssertionError("Network prohibited"))
        self.network.start()
    def tearDown(self):
        self.network.stop()
        self.sleep.stop()

    def test_faq_denied_even_if_allowlisted(self):
        for suffix in ("/hmpg/ygpa/comu/faqs/test.do", "/test?bbs_no=230",
                       "/test?%2562bs_no=%2532%2533%2530"):
            policy = copy.deepcopy(POLICY)
            url = HOST + suffix
            policy["allowed_urls"].append(url)
            with self.assertRaises(ValueError):
                c.check_url(url, policy)

    def test_exact_allowlist_and_mapping(self):
        with self.assertRaises(ValueError):
            c.check_url(SOURCE + "&other=1", POLICY)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root)
            policy, targets = c.select_targets(root)
            self.assertEqual([r["doc_id"] for r in targets], ["YGPA-021"])
            with self.assertRaises(ValueError):
                c.select_targets(root, doc_ids=["YGPA-001"])
            policy["attachment_sources"][0]["source_url"] += "other"
            c.write_json(root / "docs/contracts/data_separation_policy.json", policy)
            with self.assertRaises(ValueError):
                c.select_targets(root)

    def make_project(self, root):
        (root / "docs/contracts").mkdir(parents=True)
        (root / "data/catalog").mkdir(parents=True)
        c.write_json(root / "docs/contracts/data_separation_policy.json", POLICY)
        with (root / POLICY["catalog_path"]).open("w", newline="", encoding="utf-8-sig") as f:
            writer = c.csv.DictWriter(f, fieldnames=list(ROW))
            writer.writeheader()
            writer.writerow(ROW)

    def test_default_preview_no_network_no_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root)
            before = set(root.rglob("*"))
            with patch.object(c, "ROOT", root), patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(c.main([]), 0)
            self.assertEqual(before, set(root.rglob("*")))

    def test_parent_literal_and_button_links(self):
        self.assertEqual(c.verify_parent(HTML, ROW)["matched_url"], SOURCE)
        button = f'''<button onclick="location.href='{SOURCE}';">Download</button>'''.encode()
        self.assertEqual(c.verify_parent(button, ROW)["matched_url"], SOURCE)
        with self.assertRaises(ValueError):
            c.verify_parent(b"<html>Login</html>", ROW)
        with self.assertRaises(ValueError):
            c.verify_parent(("<script>const unused='" + SOURCE + "';</script>").encode(), ROW)

    def test_robots_rechecks_each_url(self):
        robots = HOST + "/robots.txt"
        body = b"User-agent: *\nDisallow: /hmpg/comm/file/\nCrawl-delay: 2\n"
        session = Session([Response(robots, body)])
        client = c.Client(POLICY, session)
        self.assertEqual(client.robots(PARENT), ("allowed", 2))
        with self.assertRaises(ValueError):
            client.robots(SOURCE)
        self.assertEqual(len(session.calls), 1)

    def test_redirect_is_not_followed(self):
        session = Session([Response(SOURCE, status=302)])
        with self.assertRaises(ValueError):
            c.Client(POLICY, session).fetch(SOURCE, "attachment")
        self.assertFalse(session.calls[0][1]["allow_redirects"])

    def test_retry_and_response_size_limit(self):
        session = Session([Response(SOURCE, status=503), Response(SOURCE, PDF)])
        self.assertEqual(c.Client(POLICY, session).fetch(SOURCE, "attachment")[0], PDF)
        self.assertEqual(len(session.calls), 2)
        for headers in ({}, {"Content-Length": "100"}):
            session = Session([Response(SOURCE, b"12345", headers=headers)])
            with self.assertRaises(ValueError):
                c.Client(POLICY, session).fetch(SOURCE, "attachment", limit=4)

    def test_timeout_retries_are_bounded(self):
        session = Session([requests.Timeout("test")] * 3)
        with self.assertRaises(requests.Timeout):
            c.Client(POLICY, session).fetch(SOURCE, "attachment")
        self.assertEqual(len(session.calls), 3)

    def test_html_empty_and_corrupt_files_are_held(self):
        for data in (b"", b"<html>HTTP error</html>", b"PK\x03\x04broken", b"%PDF-1.7 truncated"):
            with self.assertRaises(ValueError):
                c.detect_format(data)

    def test_format_containers(self):
        self.assertEqual(c.detect_format(PDF), ("pdf", ".pdf"))
        self.assertEqual(c.detect_format(bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 504), ("ole_compound", ".ole"))
        for files, expected in (({"mimetype": "application/hwp+zip", "Contents/content.hpf": ""}, "hwpx"),
                                ({"[Content_Types].xml": "", "word/document.xml": ""}, "docx")):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, text in files.items():
                    archive.writestr(name, text)
            self.assertEqual(c.detect_format(buffer.getvalue())[0], expected)

    def test_collect_metadata_skip_and_tamper(self):
        robots = HOST + "/robots.txt"
        session = Session([Response(robots, status=404),
                           Response(PARENT, HTML, headers={"content-type": "text/html"}),
                           Response(SOURCE, PDF, headers={"content-type": "application/pdf"})])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved = c.collect(root, ROW, POLICY, c.Client(POLICY, session), "test-batch", {})
            metadata = json.loads((saved / "metadata.json").read_text(encoding="utf-8"))
            self.assertFalse(metadata["index_approved"])
            self.assertEqual(metadata["actual_format"], "pdf")
            self.assertEqual(metadata["provenance"]["purpose"], "provenance_only_do_not_index")
            self.assertEqual(c.existing_snapshot(root, ROW), saved)
            (saved / "source.pdf").write_bytes(b"changed")
            self.assertIsNone(c.existing_snapshot(root, ROW))

    def test_missing_link_prevents_attachment_request(self):
        class FakeClient:
            def get(self, url, role, **kwargs):
                if role != "parent":
                    raise AssertionError("Attachment must not be requested")
                return b"<html>No link</html>", {"Content-Type": "text/html"}, "allowed"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                c.collect(root, ROW, POLICY, FakeClient(), "test", {})
            self.assertFalse((root / "data/raw").exists())


if __name__ == "__main__":
    unittest.main()
