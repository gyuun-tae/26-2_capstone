"""Synthetic fixtures only: no real documents, FAQ answers, or network."""
from contextlib import contextmanager
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_attachments as e

URL = "https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=TEST"
PARENT = "https://www.ygpa.or.kr/hmpg/test.do?bbs_no=211"
ROW = {"doc_id": "YGPA-021", "title": "Synthetic document", "source_url": URL, "parent_source_url": PARENT}
POLICY = {"allowed_hosts": ["www.ygpa.or.kr"], "allowed_urls": [URL], "allowed_parent_urls": [PARENT],
          "blocked_path_prefixes": ["/hmpg/ygpa/comu/faqs/"], "blocked_query_values": {"bbs_no": ["230"]}}
RESULT = {"extracted_format": "pdf", "blocks": [{"locator": {"kind": "pdf_page", "page_number": 1}, "text": "Synthetic text"}],
          "details": {"page_count": 1}, "review_flags": ["manual_review"]}


def compressed(data):
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(data) + compressor.flush()


class ExtractionTests(unittest.TestCase):
    def test_extended_record_and_truncation(self):
        header = struct.pack("<I", 67 | (3 << 10) | (4095 << 20))
        record = header + struct.pack("<I", 6) + b"abcdef"
        self.assertEqual(list(e.records(record))[0][2:], (67, 3, b"abcdef"))
        for bad in (b"a", header, record[:-1]):
            with self.assertRaises(ValueError):
                list(e.records(bad))

    def test_control_payload_is_not_text(self):
        tab = struct.pack("<H", 9) + b"ABCDEFGHIJKL" + struct.pack("<H", 9)
        source = "앞😀".encode("utf-16le") + tab + "뒤\r".encode("utf-16le")
        text, counts = e.paragraph_text(source)
        self.assertEqual(text, "앞😀\t뒤")
        self.assertEqual(counts["9"], 1)
        self.assertNotIn("ABC", text)

    def test_bad_control_is_held(self):
        for bad in (b"a", struct.pack("<H", 11), struct.pack("<H", 9) + b"\0" * 14):
            with self.assertRaises(ValueError):
                e.paragraph_text(bad)

    def test_deflate_trailer_and_limits(self):
        data = b"synthetic" * 10
        raw = compressed(data)
        self.assertEqual(e.decompress_section(raw), data)
        self.assertEqual(e.decompress_section(raw + struct.pack("<II", zlib.crc32(data), len(data))), data)
        for bad in (raw[:-1], raw + b"garbage", raw + struct.pack("<II", 0, len(data))):
            with self.assertRaises(ValueError):
                e.decompress_section(bad)
        with patch.object(e, "MAX_STREAM", 16), self.assertRaises(ValueError):
            e.decompress_section(raw)

    def test_hwp_header_protection_and_non_hwp(self):
        import olefile
        class FakeOle:
            def __init__(self, header): self.header = header
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def exists(self, name): return True
            def openstream(self, name): return io.BytesIO(self.header)
        for flags in (2, 4, 256, 512):
            header = bytearray(256)
            header[:17] = b"HWP Document File"
            header[35] = 5
            struct.pack_into("<I", header, 36, flags)
            with patch.object(olefile, "OleFileIO", return_value=FakeOle(header)), self.assertRaises(ValueError):
                e.extract_hwp(b"unused")
        with patch.object(olefile, "OleFileIO", return_value=FakeOle(b"\0" * 256)), self.assertRaises(ValueError):
            e.extract_hwp(b"unused")

    def test_numeric_hwp_section_order_and_table_flag(self):
        import olefile
        header = bytearray(256)
        header[:17] = b"HWP Document File"
        header[35] = 5
        def record(tag, payload):
            return struct.pack("<I", tag | (len(payload) << 20)) + payload
        class FakeOle:
            parsing_issues = []
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def exists(self, name): return True
            def listdir(self): return [["BodyText", f"Section{i}"] for i in reversed(range(12))]
            def openstream(self, name):
                if name == "FileHeader": return io.BytesIO(header)
                payload = (name[1] + "\r").encode("utf-16le")
                return io.BytesIO(record(67, payload) + record(77, struct.pack("<IHH", 0, 2, 3)))
        with patch.object(olefile, "OleFileIO", return_value=FakeOle()):
            result = e.extract_hwp(b"unused")
        self.assertEqual([b["text"] for b in result["blocks"]], [f"Section{i}" for i in range(12)])
        self.assertEqual(result["details"]["table_count"], 12)
        self.assertIn("table_cells_flattened_manual_comparison_required", result["review_flags"])

    def test_pdf_blank_pages_and_encryption(self):
        from pypdf import PdfWriter
        for password in (None, "test-only"):
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            if password: writer.encrypt(password)
            data = io.BytesIO()
            writer.write(data)
            if password:
                with self.assertRaises(ValueError): e.extract_pdf(data.getvalue())
            else:
                result = e.extract_pdf(data.getvalue())
                self.assertEqual(result["details"]["blank_pages"], [1])
                with self.assertRaises(ValueError): e.extract_bytes(data.getvalue())

    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "data/raw/YGPA-021/20260101T000000Z"
            snapshot.mkdir(parents=True)
            data = b"%PDF-synthetic"
            parent = f'<a href="{URL}">Download</a>'.encode()
            raw_path, parent_path = snapshot / "source.pdf", snapshot / "parent_source.html"
            raw_path.write_bytes(data)
            parent_path.write_bytes(parent)
            meta = {**ROW, "final_url": URL, "raw_path": raw_path.relative_to(root).as_posix(),
                    "content_sha256": e.sha(data), "provenance": {"parent_raw_path": parent_path.relative_to(root).as_posix(),
                    "parent_sha256": e.sha(parent), "matched_url": URL}}
            e.write_json(snapshot / "metadata.json", meta)
            yield root, snapshot, meta

    def test_source_hash_tampering_and_path_escape(self):
        with self.fixture() as (root, snapshot, meta):
            e.validate_source(root, ROW, POLICY)
            (snapshot / "source.pdf").write_bytes(b"modified")
            with self.assertRaises(ValueError): e.validate_source(root, ROW, POLICY)
            meta["raw_path"] = "README.md"
            e.write_json(snapshot / "metadata.json", meta)
            with self.assertRaises(ValueError): e.validate_source(root, ROW, POLICY)

    def test_save_skip_and_no_overwrite_of_corruption(self):
        with self.fixture() as (root, snapshot, meta), patch.object(e, "extract_bytes", return_value=RESULT):
            status, output, _ = e.extract_one(root, ROW, POLICY)
            self.assertEqual(status, "saved")
            doc = json.loads((output / "document.json").read_text(encoding="utf-8"))
            self.assertFalse(doc["index_approved"])
            self.assertEqual(doc["review_status"], "pending_manual_comparison")
            self.assertEqual(e.extract_one(root, ROW, POLICY)[0], "existing")
            (output / "blocks.json").write_text("broken", encoding="utf-8")
            with self.assertRaises(ValueError): e.extract_one(root, ROW, POLICY)

    def test_default_does_not_extract_or_write(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(e, "ROOT", Path(directory)), \
             patch.object(e, "select_targets", return_value=(POLICY, [ROW])), \
             patch.object(e, "extract_one", side_effect=AssertionError("Must not extract")), \
             patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(e.main([]), 0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_unknown_format_is_held(self):
        with self.assertRaises(ValueError): e.extract_bytes(b"<html>error</html>")


if __name__ == "__main__":
    unittest.main()
