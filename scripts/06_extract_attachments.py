"""Offline HWP 5 / PDF extraction. Preview by default; use --extract to save."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import zlib

select_targets = __import__("05_collect_attachments", fromlist=["select_targets"]).select_targets
verify_parent = __import__("05_collect_attachments", fromlist=["verify_parent"]).verify_parent
check_url = __import__("05_collect_attachments", fromlist=["check_url"]).check_url

ROOT = Path(__file__).resolve().parents[1]
VERSION = "attachments-text-v1"
MAX_STREAM = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
LONG_CONTROLS = set(range(1, 10)) | {11, 12} | set(range(14, 24))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def decompress_section(data):
    decoder = zlib.decompressobj(-15)
    out = decoder.decompress(data, MAX_STREAM + 1)
    if len(out) > MAX_STREAM or decoder.unconsumed_tail:
        raise ValueError("HWP 구역의 압축 해제 크기 제한 초과")
    if not decoder.eof:
        raise ValueError("손상되거나 불완전한 HWP 압축 스트림")
    # The collected HWP streams have a CRC32 + uncompressed-size trailer.
    # Accept a bare deflate stream too; reject arbitrary trailing bytes.
    trailer = decoder.unused_data
    if trailer:
        if len(trailer) != 8:
            raise ValueError("알 수 없는 HWP 압축 후행 데이터")
        crc, size = struct.unpack("<II", trailer)
        if crc != zlib.crc32(out) or size != len(out):
            raise ValueError("HWP 압축 스트림 CRC 또는 길이 불일치")
    return out


def records(data):
    """HWP 5 record header: 10-bit tag, 10-bit level, 12-bit size."""
    offset, number = 0, 0
    while offset < len(data):
        start = offset
        if len(data) - offset < 4:
            raise ValueError("HWP 레코드 헤더가 잘렸습니다.")
        header = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        size = header >> 20
        if size == 0xFFF:
            if len(data) - offset < 4:
                raise ValueError("HWP 확장 길이가 잘렸습니다.")
            size = struct.unpack_from("<I", data, offset)[0]
            offset += 4
        if size > len(data) - offset:
            raise ValueError("HWP 레코드 내용이 선언한 길이보다 짧습니다.")
        number += 1
        yield number, start, header & 0x3FF, (header >> 10) & 0x3FF, data[offset:offset + size]
        offset += size


def paragraph_text(data):
    if len(data) % 2:
        raise ValueError("HWP UTF-16 문단 길이가 홀수입니다.")
    result, control_counts = bytearray(), Counter()
    offset = 0
    while offset < len(data):
        code = struct.unpack_from("<H", data, offset)[0]
        if code >= 32:
            result.extend(data[offset:offset + 2])
            offset += 2
            continue
        control_counts[str(code)] += 1
        width = 16 if code in LONG_CONTROLS else 2
        if offset + width > len(data):
            raise ValueError("HWP 제어문자가 잘렸습니다.")
        if width == 16 and struct.unpack_from("<H", data, offset + 14)[0] != code:
            raise ValueError("HWP 제어문자의 종료 코드가 일치하지 않습니다.")
        replacement = {9: "\t", 10: "\n", 13: "\n", 24: "-", 30: " ", 31: " "}.get(code, "")
        result.extend(replacement.encode("utf-16le"))
        offset += width
    text = result.decode("utf-16le")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip(), control_counts


def extract_hwp(data):
    import olefile
    blocks, tables, counts = [], [], Counter()
    total = 0
    with olefile.OleFileIO(io.BytesIO(data)) as ole:
        if not ole.exists("FileHeader"):
            raise ValueError("HWP FileHeader가 없는 OLE 파일입니다.")
        header = ole.openstream("FileHeader").read(257)
        if len(header) != 256 or header[:32].rstrip(b"\0") != b"HWP Document File" or header[35] != 5:
            raise ValueError("지원하는 HWP 5 파일 헤더가 아닙니다.")
        flags = struct.unpack_from("<I", header, 36)[0]
        if flags & 2:
            raise ValueError("암호화 HWP는 자동 추출하지 않습니다.")
        if flags & 4:
            raise ValueError("배포용 HWP는 이 추출기에서 지원하지 않습니다.")
        if flags & ((1 << 8) | (1 << 9)):
            raise ValueError("DRM HWP는 자동 추출하지 않습니다.")
        section_paths = [p for p in ole.listdir() if len(p) == 2 and p[0] == "BodyText" and re.fullmatch(r"Section\d+", p[1])]
        section_paths.sort(key=lambda p: int(p[1][7:]))
        if not section_paths or len(section_paths) > 100:
            raise ValueError("HWP 본문 구역 수를 확인할 수 없습니다.")
        if [int(p[1][7:]) for p in section_paths] != list(range(len(section_paths))):
            raise ValueError("HWP 본문 구역 번호가 연속되지 않습니다.")
        for path in section_paths:
            raw = ole.openstream(path).read(MAX_STREAM + 1)
            if len(raw) > MAX_STREAM:
                raise ValueError("HWP 스트림 크기 제한 초과")
            section = decompress_section(raw) if flags & 1 else raw
            total += len(section)
            if total > MAX_TOTAL:
                raise ValueError("HWP 전체 크기 제한 초과")
            for number, offset, tag, level, payload in records(section):
                locator = {"kind": "hwp_record", "section": path[1], "record_number": number,
                           "record_offset": offset, "level": level}
                if tag == 67:  # HWPTAG_PARA_TEXT = 16 + 51
                    text, controls = paragraph_text(payload)
                    counts.update(controls)
                    if text:
                        blocks.append({"locator": locator, "text": text})
                elif tag == 77:  # HWPTAG_TABLE = 16 + 61
                    if len(payload) < 8:
                        raise ValueError("HWP 표 속성이 잘렸습니다.")
                    rows, columns = struct.unpack_from("<HH", payload, 4)
                    tables.append({"locator": locator, "rows": rows, "columns": columns,
                                   "cell_mapping_restored": False})
        details = {"hwp_version": ".".join(map(str, reversed(header[32:36]))),
                   "section_count": len(section_paths), "compressed": bool(flags & 1),
                   "table_count": len(tables), "tables": tables, "control_counts": dict(counts),
                   "ole_parse_issue_count": len(ole.parsing_issues)}
    review_flags = ["hwp_layout_and_automatic_numbering_not_restored", "images_and_equations_not_extracted"]
    if tables:
        review_flags.append("table_cells_flattened_manual_comparison_required")
    if details["ole_parse_issue_count"]:
        review_flags.append("ole_parser_reported_issues")
    return {"extracted_format": "hwp5", "blocks": blocks, "details": details, "review_flags": review_flags}


def extract_pdf(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted:
        raise ValueError("암호화 PDF는 자동 추출하지 않습니다.")
    if not 0 < len(reader.pages) <= 500:
        raise ValueError("PDF 페이지 수 제한 초과")
    blocks, blank_pages, sparse_pages = [], [], []
    for number, page in enumerate(reader.pages, 1):
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > MAX_STREAM:
            raise ValueError(f"PDF {number}쪽 콘텐츠 크기 제한 초과")
        text = "" if contents is None else (page.extract_text(extraction_mode="layout", layout_mode_strip_rotated=False) or "").strip()
        # Preserve layout spaces; never join table columns or hyphenated lines heuristically.
        text = "\n".join(line.rstrip() for line in text.splitlines())
        count = len(re.sub(r"\s", "", text))
        if count == 0:
            blank_pages.append(number)
        elif count < 20:
            sparse_pages.append(number)
        blocks.append({"locator": {"kind": "pdf_page", "page_number": number}, "text": text})
    flags = ["pdf_table_reading_order_requires_visual_review", "images_not_ocr_processed"]
    if blank_pages or sparse_pages:
        flags.append("blank_or_sparse_pages_need_visual_review_or_ocr")
    return {"extracted_format": "pdf", "blocks": blocks,
            "details": {"page_count": len(reader.pages), "blank_pages": blank_pages,
                        "sparse_pages": sparse_pages}, "review_flags": flags}


def extract_bytes(data):
    if data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        result = extract_hwp(data)
    elif data.startswith(b"%PDF-"):
        result = extract_pdf(data)
    else:
        raise ValueError("이번 단계는 HWP 5와 PDF만 지원합니다.")
    if not any(block["text"].strip() for block in result["blocks"]):
        raise ValueError("추출할 텍스트가 없습니다. 원본 대조 또는 OCR이 필요합니다.")
    body = "\n".join(b["text"] for b in result["blocks"])
    if "\ufffd" in body or any("\ue000" <= ch <= "\uf8ff" for ch in body):
        result["review_flags"].append("replacement_or_private_use_characters")
    return result


def validate_source(root, row, policy):
    folder = root / "data/raw" / row["doc_id"]
    snapshots = sorted(p for p in folder.iterdir() if p.is_dir()) if folder.exists() else []
    if not snapshots:
        raise ValueError("수집한 원본 폴더가 없습니다.")
    snapshot = snapshots[-1]
    if not snapshot.resolve().is_relative_to(folder.resolve()):
        raise ValueError("원본 스냅샷 경로가 문서 폴더 밖입니다.")
    meta = json.loads((snapshot / "metadata.json").read_text(encoding="utf-8"))
    for key in ("doc_id", "source_url", "parent_source_url"):
        if meta[key] != row[key]:
            raise ValueError(f"후보와 원본 메타데이터의 {key} 불일치")
    check_url(meta["source_url"], policy)
    check_url(meta["parent_source_url"], policy, "parent")
    if meta["final_url"] != row["source_url"]:
        raise ValueError("원본 최종 URL 불일치")
    raw = (root / meta["raw_path"]).resolve()
    parent = (root / meta["provenance"]["parent_raw_path"]).resolve()
    if not raw.is_relative_to(snapshot.resolve()) or not parent.is_relative_to(snapshot.resolve()):
        raise ValueError("원본 파일이 스냅샷 경로 밖입니다.")
    if raw.stat().st_size > 25 * 1024 * 1024 or parent.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("원본 크기 제한 초과")
    data, parent_data = raw.read_bytes(), parent.read_bytes()
    if sha(data) != meta["content_sha256"] or sha(parent_data) != meta["provenance"]["parent_sha256"]:
        raise ValueError("원본 또는 출처 HTML의 해시 불일치")
    if meta["provenance"]["matched_url"] != row["source_url"]:
        raise ValueError("첨부 출처 대응 불일치")
    verify_parent(parent_data, row)  # Link check only; this HTML is NEVER body input.
    return snapshot, meta, data


def build_text(result):
    sections = []
    current = None
    for block in result["blocks"]:
        loc = block["locator"]
        label = f"PDF 파일 페이지 {loc['page_number']}" if loc["kind"] == "pdf_page" else f"HWP 구역 {loc['section']}"
        if label != current:
            sections.append(f"[{label}]")
            current = label
        sections.append(block["text"])
    return "\n\n".join(sections).rstrip() + "\n"


def extract_one(root, row, policy):
    snapshot, meta, data = validate_source(root, row, policy)
    output = root / "data/processed" / row["doc_id"] / snapshot.name
    if output.exists():
        try:
            old = json.loads((output / "document.json").read_text(encoding="utf-8"))
            if (old["extraction_version"] == VERSION and old["document_version"] == sha(data)
                    and old["doc_id"] == row["doc_id"] and old["source_url"] == row["source_url"]
                    and old["text_sha256"] == sha((output / "document.txt").read_bytes())
                    and old["blocks_sha256"] == sha((output / "blocks.json").read_bytes())
                    and (output / "review.md").is_file()):
                return "existing", output, old["extraction_details"]
        except (OSError, ValueError, KeyError):
            pass
        raise ValueError("기존 추출 결과가 불완전하거나 버전이 다릅니다. 덮어쓰지 않고 보류합니다.")
    result = extract_bytes(data)
    text = build_text(result)
    block_bytes = json.dumps(result["blocks"], ensure_ascii=False, indent=2).encode("utf-8")
    import olefile, pypdf
    doc = {**meta, "document_version": sha(data), "source_snapshot": snapshot.name,
           "source_metadata_path": (snapshot / "metadata.json").relative_to(root).as_posix(),
           "processed_at": datetime.now(timezone.utc).isoformat(), "extraction_version": VERSION,
           "extractor_dependencies": {"olefile": olefile.__version__, "pypdf": pypdf.__version__},
           "extracted_format": result["extracted_format"], "extraction_details": result["details"],
           "text": text, "text_sha256": sha(text.encode("utf-8")),
           "blocks_path": (output / "blocks.json").relative_to(root).as_posix(), "blocks_sha256": sha(block_bytes),
           "review_flags": result["review_flags"], "review_status": "pending_manual_comparison",
           "ingestion_status": "text_extracted_pending_review", "index_approved": False}
    review = (f"# {row['doc_id']} 추출 검토\n\n원본: [{row['title']}]({row['source_url']})\n\n"
              f"- 형식: {result['extracted_format']}\n- 원본 SHA-256: {sha(data)}\n"
              "- 본문 추출은 검색 승인이 아니다. 아직 색인 승인되지 않았다.\n"
              "- 날짜는 원본 메타데이터를 유지했으며 시행일·갱신일을 추정하지 않았다.\n"
              "- TXT의 대괄호 구역·페이지 표시는 대조용 생성 표식이다. HWP 구역은 페이지가 아니다.\n\n"
              "## 원문 대조 항목\n\n- 제목·구비서류·조건·단위·숫자·조문번호가 원문과 일치하는지 확인\n"
              "- 표의 행·열·병합 셀과 주석을 확인. HWP 표의 셀 대응은 아직 복원하지 않음\n"
              "- 자동번호, 수식, 이미지 안의 글자, 빈 페이지·짧은 페이지의 누락 여부 확인\n"
              "- FAQ 원문·복사본 발견 시 개발 데이터에서 제외\n\n## 자동 표시 사항\n\n"
              + "\n".join(f"- `{flag}`" for flag in result["review_flags"]) + "\n")
    output.mkdir(parents=True, exist_ok=False)
    paths = [output / n for n in ("document.txt", "blocks.json", "review.md", "document.json")]
    try:
        paths[0].write_bytes(text.encode("utf-8"))
        paths[1].write_bytes(block_bytes)
        paths[2].write_text(review, encoding="utf-8")
        write_json(paths[3], doc)
    except OSError:
        for path in paths:
            path.unlink(missing_ok=True)
        output.rmdir()
        raise
    return "saved", output, result["details"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--doc-ids", nargs="+")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--extract", action="store_true", help="본문 추출 결과를 저장")
    args = parser.parse_args(argv)
    policy, targets = select_targets(ROOT, "all", None if args.all else (args.doc_ids or ["YGPA-021"]))
    if not args.extract:
        for row in targets:
            print(f"{row['doc_id']} | {row['title']}")
        print(f"대상 {len(targets)}건. 저장하려면 --extract 옵션을 추가하세요. 네트워크 요청 없음.")
        return 0
    try:
        import olefile, pypdf
    except ImportError as error:
        raise ValueError("먼저 python -m pip install -r requirements-extraction.txt를 실행하세요.") from error
    batch = datetime.now(timezone.utc).strftime("extract-attachments-%Y%m%dT%H%M%S%fZ")
    logs = ROOT / "data/processed/_extraction_failures" / batch
    logs.mkdir(parents=True, exist_ok=False)
    counts, results = Counter(saved=0, existing=0, held=0), []
    for row in targets:
        try:
            status, output, details = extract_one(ROOT, row, policy)
            counts[status] += 1
            results.append({"doc_id": row["doc_id"], "status": status,
                            "path": output.relative_to(ROOT).as_posix(), "details": details})
            print(f"[{'추출 완료' if status == 'saved' else '기존 결과 유지'}] {row['doc_id']}: {output}")
        except Exception as error:
            # A malformed attachment must not stop independent documents in a batch.
            counts["held"] += 1
            failure = {"doc_id": row["doc_id"], "error": str(error), "error_type": type(error).__name__,
                       "failed_at": datetime.now(timezone.utc).isoformat(), "index_approved": False}
            write_json(logs / (row["doc_id"] + ".json"), failure)
            results.append({**failure, "status": "held"})
            print(f"[보류] {row['doc_id']}: {error}")
    write_json(logs / "summary.json", {"batch_id": batch, **counts, "results": results})
    print(f"본문 추출: 성공 {counts['saved']}건, 기존 {counts['existing']}건, 보류 {counts['held']}건")
    print(f"실행 기록: {logs}")
    print("다음은 원문 대조입니다. 청크화·검색 등록은 수행하지 않았습니다.")
    return 1 if counts["held"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"추출 중단: {error}")
