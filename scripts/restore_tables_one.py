"""YGPA-021 HWP table pilot. Preview by default; --restore saves a sidecar."""
import argparse
import copy
from datetime import datetime, timezone
import html
import io
import json
import re
from pathlib import Path
import struct
import sys

from collect_attachments import select_targets
from extract_attachments import validate_source, decompress_section, records, paragraph_text, sha

ROOT = Path(__file__).resolve().parents[1]
DOC_ID = "YGPA-021"
VERSION = "hwp-tables-v1"
HWP_IDS = tuple(f"YGPA-{i:03}" for i in [*range(21, 31), 33])


def validate_grid(table):
    rows, cols = table["rows"], table["columns"]
    if rows < 1 or cols < 1 or rows * cols > 100000:
        raise ValueError("지원 범위를 벗어난 표 크기")
    occupied = {}
    for cell in table["cells"]:
        r, c, rs, cs = (cell[k] for k in ("row", "column", "rowspan", "colspan"))
        if min(r, c) < 0 or min(rs, cs) < 1 or r + rs > rows or c + cs > cols:
            raise ValueError("표 범위를 벗어난 셀 또는 병합 크기")
        for y in range(r, r + rs):
            for x in range(c, c + cs):
                if (y, x) in occupied:
                    raise ValueError("표의 셀 영역이 겹칩니다.")
                occupied[y, x] = cell["cell_id"]
    if len(occupied) != rows * cols:
        raise ValueError("표 격자에 어떤 셀에도 속하지 않는 위치가 있습니다.")


def parse_overlapping(payload, locator):
    """Hancom HWP5 rev1.2, table 144; preserve glyphs separately from paragraph text."""
    if len(payload) < 10 or payload[:4] != b"spct":
        raise ValueError("잘못된 글자 겹침 컨트롤")
    length = struct.unpack_from("<H", payload, 4)[0]
    end = 6 + length * 2
    if end + 4 > len(payload):
        raise ValueError("글자 겹침 문자열이 잘렸습니다.")
    text = payload[6:end].decode("utf-16le", errors="strict")
    count = payload[end + 3]
    if end + 4 + count * 4 != len(payload):
        raise ValueError("글자 겹침 속성 배열 길이 불일치")
    return {"kind": "overlapping_text", "locator": locator, "text": text,
            "border_type": payload[end], "internal_size": struct.unpack_from("<b", payload, end + 1)[0],
            "spread": payload[end + 2],
            "charshape_ids": list(struct.unpack_from(f"<{count}I", payload, end + 4)),
            "raw_payload_hex": payload.hex(), "rendering": "plain_glyphs_not_original_style"}


def parse_section(stream, section, first_table=1, doc_id=DOC_ID, preserve_graphics=False):
    """Follow nested table control levels, retaining the owning parent cell."""
    tables, contexts = [], []
    overlap_level = None
    graphic = None

    def finish_cell(context):
        current_cell = context["cell"]
        if current_cell is not None and current_cell["paragraphs_seen"] != current_cell["paragraph_count"]:
            raise ValueError("셀의 문단 수가 선언한 값과 다릅니다.")

    def finish_table(context):
        finish_cell(context)
        active = context["table"]
        if not active["dimensions_seen"]:
            raise ValueError("표 속성 레코드가 없습니다.")
        validate_grid(active)

    def keep_graphic_record(obj, loc, tag, payload):
        header_size = 8 if struct.unpack_from("<I", stream, loc["record_offset"])[0] >> 20 == 0xFFF else 4
        raw_record = stream[loc["record_offset"]:loc["record_offset"] + header_size + len(payload)]
        ancestors = [v for v in obj["records"] if v["locator"]["level"] < loc["level"]]
        parent = ancestors[-1]["locator"]["record_number"] if ancestors else None
        obj["records"].append({"locator": loc, "tag": tag, "level_parent_record": parent,
                               "raw_record_hex": raw_record.hex(), "payload_hex": payload.hex()})
        if tag == 67:
            text, _ = paragraph_text(payload)
            if text:
                obj["text_records"].append({"locator": loc, "text": text})

    for number, offset, tag, level, payload in records(stream):
        loc = {"kind": "hwp_record", "section": section, "record_number": number,
               "record_offset": offset, "level": level}
        if graphic is not None:
            if level > graphic["locator"]["level"]:
                keep_graphic_record(graphic, loc, tag, payload)
                continue
            graphic = None
        if overlap_level is not None:
            if level > overlap_level:
                raise ValueError("글자 겹침에 예상하지 않은 하위 레코드가 있습니다.")
            overlap_level = None
        while contexts and level <= contexts[-1]["table"]["control_level"]:
            finish_table(contexts.pop())
        if tag == 71 and payload[:4] == b" lbt":
            table_id = f"{doc_id}-T{first_table + len(tables):03}"
            parent_cell = contexts[-1]["cell"] if contexts else None
            if contexts and (parent_cell is None or contexts[-1]["paragraph"] is None):
                raise ValueError("중첩 표의 부모 셀/문단이 없습니다.")
            active = {"table_id": table_id, "locator": loc, "control_level": level,
                      "parent_cell_id": parent_cell["cell_id"] if parent_cell else None,
                      "dimensions_seen": False, "cells": []}
            if parent_cell is not None:
                parent_cell["nested_table_ids"].append(table_id)
            tables.append(active)
            contexts.append({"table": active, "cell": None, "paragraph": None})
            continue
        if not contexts:
            if tag == 77:
                raise ValueError("표 컨트롤 밖에서 표 속성을 발견했습니다.")
            continue
        context = contexts[-1]
        active, current_cell, paragraph_context = context["table"], context["cell"], context["paragraph"]
        base = active["control_level"]
        if tag == 77:
            if level != base + 1 or active["dimensions_seen"] or len(payload) < 8:
                raise ValueError("예상과 다른 표 속성 구조")
            active["rows"], active["columns"] = struct.unpack_from("<HH", payload, 4)
            active["dimensions_seen"] = True
        elif tag == 72:
            finish_cell(context)
            if not active["dimensions_seen"] or level != base + 1 or len(payload) < 34:
                raise ValueError("지원하지 않는 캡션 또는 셀 리스트 구조")
            # This HWP 5.x layout uses an 8-byte list header before cell attributes.
            count = struct.unpack_from("<I", payload, 0)[0]
            col, row, colspan, rowspan = struct.unpack_from("<HHHH", payload, 8)
            current_cell = {"cell_id": f"{active['table_id']}-R{row:03}C{col:03}",
                            "row": row, "column": col, "rowspan": rowspan, "colspan": colspan,
                            "locator": loc, "paragraph_count": count, "paragraphs_seen": 0,
                            "paragraphs": [], "text": "", "nested_table_ids": []}
            active["cells"].append(current_cell)
            context["cell"], context["paragraph"] = current_cell, None
        elif tag == 66:
            if current_cell is None or level != base + 1:
                raise ValueError("예상과 다른 셀 문단 구조")
            current_cell["paragraphs_seen"] += 1
            paragraph_context = {"locator": loc, "text_records": [], "text": ""}
            current_cell["paragraphs"].append(paragraph_context)
            context["paragraph"] = paragraph_context
        elif tag == 67:
            if paragraph_context is None or level != base + 2:
                raise ValueError("셀과 연결되지 않는 문단 텍스트")
            text, _ = paragraph_text(payload)
            paragraph_context["text_records"].append({"locator": loc, "text": text})
            paragraph_context["text"] += text
        elif tag == 71 and payload[:4] == b" osg" and doc_id == "YGPA-030" and preserve_graphics:
            if current_cell is None or paragraph_context is None or level != base + 2:
                raise ValueError("그리기 개체의 부모 셀/문단 위치 불일치")
            objects = current_cell.setdefault("graphic_objects", [])
            graphic = {"object_id": f"{current_cell['cell_id']}-G{len(objects)+1:03}",
                       "locator": loc, "paragraph_locator": paragraph_context["locator"],
                       "records": [], "text_records": [], "visual_layout_status": "not_rendered_pending_review"}
            keep_graphic_record(graphic, loc, tag, payload)
            objects.append(graphic)
        elif tag == 71 and payload[:4] == b"spct" and doc_id == "YGPA-033":
            if current_cell is None or paragraph_context is None or level != base + 2:
                raise ValueError("글자 겹침의 부모 셀/문단 위치 불일치")
            control = parse_overlapping(payload, loc)
            control["paragraph_locator"] = paragraph_context["locator"]
            current_cell.setdefault("inline_controls", []).append(control)
            overlap_level = level
        elif tag == 71:
            raise ValueError(f"셀 안의 별도 컨트롤은 추가 검토가 필요합니다: {section}, 레코드 {number}, control={payload[:4].hex()}")
    while contexts:
        finish_table(contexts.pop())
    for table in tables:
        for cell in table["cells"]:
            cell["text"] = "\n".join(p["text"] for p in cell["paragraphs"] if p["text"])
            cell["is_text_blank"] = not bool(cell["text"].strip())
            cell["is_blank"] = cell["is_text_blank"] and not cell["nested_table_ids"] and not cell.get("inline_controls") and not cell.get("graphic_objects")
            del cell["paragraphs_seen"]
        del table["control_level"], table["dimensions_seen"]
    return tables


def read_tables(raw, doc_id=DOC_ID, preserve_graphics=False):
    import olefile
    result = []
    with olefile.OleFileIO(io.BytesIO(raw)) as ole:
        header = ole.openstream("FileHeader").read()
        if len(header) != 256 or header[:32].rstrip(b"\0") != b"HWP Document File" or header[35] != 5:
            raise ValueError("HWP 5 파일이 아닙니다.")
        flags = struct.unpack_from("<I", header, 36)[0]
        if flags != 1:
            raise ValueError("이번 복원기는 확인한 일반 압축 HWP 형식만 지원합니다.")
        paths = [p for p in ole.listdir() if len(p) == 2 and p[0] == "BodyText"]
        if not paths or any(not re.fullmatch(r"Section\d+", p[1]) for p in paths):
            raise ValueError("지원하지 않는 HWP 구역 이름")
        paths.sort(key=lambda p: int(p[1][7:]))
        if [int(p[1][7:]) for p in paths] != list(range(len(paths))):
            raise ValueError("HWP 구역 번호가 연속적이지 않습니다.")
        for path in paths:
            stream = ole.openstream(path).read(32 * 1024 * 1024 + 1)
            if len(stream) > 32 * 1024 * 1024:
                raise ValueError("HWP 구역 크기 제한 초과")
            result.extend(parse_section(decompress_section(stream), path[1], len(result) + 1, doc_id, preserve_graphics))
    if not result:
        raise ValueError("복원할 표가 없습니다.")
    return result


def link_blocks(tables, blocks):
    key = lambda loc: (loc["section"], loc["record_number"])
    lookup = {}
    for table in tables:
        for cell in table["cells"]:
            for paragraph in cell["paragraphs"]:
                for record in paragraph["text_records"]:
                    if not record["text"]:
                        continue
                    k = key(record["locator"])
                    if k in lookup:
                        raise ValueError("문단이 여러 셀에 중복 연결됩니다.")
                    lookup[k] = (table["table_id"], cell["cell_id"], record["text"])
    object_lookup = {}
    for table in tables:
        for cell in table["cells"]:
            for obj in cell.get("graphic_objects", []):
                for record in obj["text_records"]:
                    k = key(record["locator"])
                    if k in lookup:
                        raise ValueError("개체 문단이 다른 셀/개체와 중복됩니다.")
                    lookup[k] = (table["table_id"], cell["cell_id"], record["text"])
                    object_lookup[k] = obj["object_id"]
    linked, seen = copy.deepcopy(blocks), set()
    for block in linked:
        k = key(block["locator"])
        if k in seen:
            raise ValueError("기존 blocks 위치가 중복됩니다.")
        seen.add(k)
        if object_lookup:
            block["graphic_object_id"] = object_lookup.get(k)
        match = lookup.get(k)
        if match:
            if match[2] != block["text"]:
                raise ValueError("원본 셀 텍스트와 기존 추출 문단이 다릅니다.")
            block["table_id"], block["cell_id"] = match[:2]
        else:
            block["table_id"], block["cell_id"] = None, None
    if set(lookup) - seen:
        raise ValueError("셀 문단 일부가 기존 blocks에서 누락됐습니다.")
    return linked


def render_tables(tables, doc_id=DOC_ID):
    label = html.escape(doc_id)
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8">',
             f'<title>{label} 표 구조 검토</title>' + '<style>body{font-family:Arial,"Malgun Gothic",sans-serif;margin:28px;color:#172536}table{border-collapse:collapse;width:100%;margin-bottom:32px;table-layout:fixed}td{border:1px solid #8395a5;padding:8px;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}h1{font-size:24px}h2{font-size:19px}.note{padding:14px;background:#fff1d5}td.blank{background:#f2f5f8;min-height:20px}small{color:#526679}</style>',
             f'<h1>{label} 표 구조 검토</h1><p class="note">원본 지면을 재현한 화면이 아닌 구조 검토용입니다. 빈 칸을 보존했습니다. 행·열 번호는 0부터 시작합니다. 검색 승인 전 자료입니다.</p>']
    for table in tables:
        parts.append(f'<h2 id="{table["table_id"]}">{table["table_id"]} · {table["rows"]}행 × {table["columns"]}열</h2><table>')
        cells = {(c["row"], c["column"]): c for c in table["cells"]}
        for row in range(table["rows"]):
            parts.append('<tr>')
            for col in range(table["columns"]):
                cell = cells.get((row, col))
                if cell is None:
                    continue  # A covered position belongs to an earlier merged cell.
                blank = ' class="blank"' if cell['is_blank'] else ''
                title = html.escape(cell['cell_id'], quote=True)
                nested = ''.join(f'<p><a href="#{html.escape(t)}">포함 표: {html.escape(t)}</a></p>' for t in cell['nested_table_ids'])
                controls = ''.join('<p class="note">글자 겹침: ' + html.escape(c['text']) + ' (글자 보존; 배치·서식은 원문 확인)</p>' for c in cell.get('inline_controls', []))
                graphics = ''.join('<p class="note"><a href="graphics.html#' + html.escape(g['object_id'], quote=True) + '">그림·도형·글상자 보기</a> — 원본 배치 미재현, 검토 필요</p>' for g in cell.get('graphic_objects', []))
                parts.append(f'<td{blank} rowspan="{cell["rowspan"]}" colspan="{cell["colspan"]}" title="{title}">{html.escape(cell["text"]) or "&nbsp;"}{nested}{controls}{graphics}</td>')
            parts.append('</tr>')
        parts.append('</table>')
    return ''.join(parts) + '</html>'


def restore(root, row, policy):
    doc_id = row["doc_id"]
    if doc_id not in HWP_IDS:
        raise ValueError("확인된 HWP 후보 문서만 처리합니다.")
    snapshot, meta, raw = validate_source(root, row, policy)
    processed = root / "data/processed" / doc_id / snapshot.name
    doc = json.loads((processed / "document.json").read_text(encoding="utf-8"))
    block_bytes = (processed / "blocks.json").read_bytes()
    if doc["doc_id"] != doc_id or doc["source_url"] != row["source_url"] or doc["document_version"] != sha(raw):
        raise ValueError("기존 추출 결과와 원본 식별 정보가 다릅니다.")
    if sha(block_bytes) != doc["blocks_sha256"] or sha((processed / "document.txt").read_bytes()) != doc["text_sha256"]:
        raise ValueError("기존 추출 결과 해시 불일치")
    version = "hwp-tables-v2" if doc_id == "YGPA-033" else VERSION
    out = processed / version
    if out.exists():
        try:
            old = json.loads((out / "validation.json").read_text(encoding="utf-8"))
            expected_names = {"tables.json", "blocks_with_tables.json", "tables.html"}
            if (old["version"] == version and old["source_sha256"] == sha(raw)
                    and old["input_blocks_sha256"] == sha(block_bytes)
                    and set(old["output_hashes"]) == expected_names
                    and all(sha((out / name).read_bytes()) == value for name, value in old["output_hashes"].items())):
                return "existing", out, old
        except (OSError, ValueError, KeyError):
            pass
        raise ValueError("기존 표 결과가 손상됐거나 버전이 다릅니다. 덮어쓰지 않습니다.")
    blocks = json.loads(block_bytes)
    tables = read_tables(raw, doc_id)
    linked = link_blocks(tables, blocks)
    if len(tables) != doc["extraction_details"]["table_count"]:
        raise ValueError("기존 추출기의 표 개수와 일치하지 않습니다.")
    payload = {"doc_id": doc_id, "version": version, "source_url": row["source_url"],
               "source_snapshot": snapshot.name, "source_sha256": sha(raw),
               "coordinate_base": 0, "tables": tables, "index_approved": False,
               "review_status": "structure_restored_pending_manual_review"}
    inline_count = sum(len(c.get("inline_controls", [])) for t in tables for c in t["cells"])
    if version == "hwp-tables-v2":
        payload["inline_control_count"] = inline_count
        payload["inline_control_note"] = "겹칠 글자는 셀의 inline_controls에 별도 보존. 기존 문단에 삽입하지 않음. 서식·배치는 원문 대조 필요."
    encode = lambda value: json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    outputs = {"tables.json": encode(payload), "blocks_with_tables.json": encode(linked),
               "tables.html": render_tables(tables, doc_id).encode("utf-8")}
    validation = {"version": version, "doc_id": doc_id, "source_sha256": sha(raw),
                  "input_blocks_sha256": sha(block_bytes), "created_at": datetime.now(timezone.utc).isoformat(),
                  "table_count": len(tables), "cell_count": sum(len(t["cells"]) for t in tables),
                  "blank_cell_count": sum(c["is_blank"] for t in tables for c in t["cells"]),
                  "merged_cell_count": sum(c["rowspan"] > 1 or c["colspan"] > 1 for t in tables for c in t["cells"]),
                  "nested_table_count": sum(t["parent_cell_id"] is not None for t in tables),
                  "mapped_text_blocks": sum(b["cell_id"] is not None for b in linked),
                  "outside_table_blocks": sum(b["cell_id"] is None for b in linked),
                  "grid_coverage": "complete_no_overlap", "paragraph_links": "exact_text_match",
                  "index_approved": False, "output_hashes": {k: sha(v) for k, v in outputs.items()}}
    if version == "hwp-tables-v2":
        validation["inline_control_count"] = inline_count
        validation["inline_control_rendering"] = "plain_glyphs_pending_visual_review"
    outputs["validation.json"] = encode(validation)
    out.mkdir(exist_ok=False)
    try:
        for name, data in outputs.items():
            (out / name).write_bytes(data)
    except OSError:
        for name in outputs:
            (out / name).unlink(missing_ok=True)
        out.rmdir()
        raise
    return "saved", out, validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true", help="표 구조 복원 결과 저장")
    args = parser.parse_args()
    policy, targets = select_targets(ROOT, doc_ids=[DOC_ID])
    if not args.restore:
        print("YGPA-021 표 복원 준비. 실행하려면 --restore를 추가하세요. 파일 저장·네트워크 요청 없음.")
        return
    state, output, validation = restore(ROOT, targets[0], policy)
    print(f"[{'표 복원 완료' if state == 'saved' else '기존 표 결과 유지'}] {DOC_ID}: {output}")
    print(f"표 {validation['table_count']}개, 셀 {validation['cell_count']}개, 연결 문단 {validation['mapped_text_blocks']}개")
    print("기존 본문은 보존했습니다. 청크화·검색 등록은 수행하지 않았습니다.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, ImportError) as error:
        sys.exit(f"표 복원 보류: {error}")
