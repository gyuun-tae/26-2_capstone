import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SKIP_DOC_ID = "YGPA-001"


class BodyParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.skip_depth += 1
            return

        if self.skip_depth:
            return

        attrs_map = dict(attrs)

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div"}:
            self.parts.append("\n")

        if tag == "li":
            self.parts.append("\n- ")

        if tag in {"td", "th"}:
            self.parts.append(" | ")

        if tag == "tr":
            self.parts.append("\n")

        if tag == "br":
            self.parts.append("\n")

        if tag == "img":
            alt = (attrs_map.get("alt") or "").strip()
            if len(alt) > 1:
                self.parts.append(f"\n[이미지 설명: {alt}]\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return

        if self.skip_depth:
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li", "tr"}:
            self.parts.append("\n")

        if tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def load_policy():
    path = ROOT / "docs" / "contracts" / "data_separation_policy.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_candidates(policy):
    path = ROOT / policy["catalog_path"]

    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    return rows


def check_url(url, policy, candidate_urls):
    parts = urlsplit(unquote(url))
    query = parse_qs(parts.query, keep_blank_values=True)

    if parts.scheme != "https":
        raise ValueError("HTTPS 주소가 아닙니다.")

    if parts.hostname not in policy["allowed_hosts"]:
        raise ValueError("허용된 공식 호스트가 아닙니다.")

    for blocked_prefix in policy["blocked_path_prefixes"]:
        if parts.path.lower().startswith(blocked_prefix.lower()):
            raise ValueError("FAQ 평가 전용 경로입니다.")

    for key, blocked_values in policy["blocked_query_values"].items():
        if any(value in blocked_values for value in query.get(key, [])):
            raise ValueError("FAQ 평가 전용 게시판입니다.")

    if url not in candidate_urls:
        raise ValueError("후보 CSV에 없는 URL입니다.")


def latest_snapshot(doc_id):
    raw_root = ROOT / "data" / "raw" / doc_id

    snapshots = [
        path for path in raw_root.iterdir()
        if path.is_dir()
    ]

    if not snapshots:
        raise ValueError("원본 스냅샷이 없습니다.")

    return sorted(
        snapshots,
        key=lambda path: path.name,
        reverse=True,
    )[0]


def decode_html(raw):
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise ValueError("UTF-8과 CP949로 HTML을 읽을 수 없습니다.")


def extract_body(html):
    blocks = re.findall(
        r"<!--\s*내용 시작\s*-->(.*?)<!--\s*내용 끝\s*-->",
        html,
        flags=re.DOTALL,
    )

    if len(blocks) != 1:
        raise ValueError("본문 시작·끝 경계를 하나 찾지 못했습니다.")

    body = blocks[0]

    detected_dates = sorted(
        set(
            re.findall(
                r"""\$\(["']#cont_last_mdfcn_dt["']\)\.html\(["'](\d{4}-\d{2}-\d{2})["']\)""",
                body,
            )
        )
    )

    parser = BodyParser()
    parser.feed(body)
    parser.close()

    lines = []

    for raw_line in "".join(parser.parts).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        line = re.sub(r"\|\s*\|+", "|", line)

        if line and line != "|":
            lines.append(line)

    text = "\n".join(lines).strip() + "\n"

    if len(text.strip()) < 20:
        raise ValueError("추출된 본문이 너무 짧습니다.")

    return text, detected_dates


def save_failure(failure_dir, row, error):
    failure = {
        "doc_id": row["doc_id"],
        "title": row["title"],
        "source_url": row["source_url"],
        "error": str(error),
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "index_approved": False,
    }

    (failure_dir / f"{row['doc_id']}.json").write_text(
        json.dumps(failure, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    policy = load_policy()
    rows = load_candidates(policy)

    targets = [
        row for row in rows
        if row["doc_id"] != SKIP_DOC_ID
    ]

    if len(targets) != 19:
        raise ValueError(
            f"처리 대상이 19건이 아닙니다: {len(targets)}건"
        )

    candidate_urls = {
        row["source_url"]
        for row in rows
    }

    batch_id = datetime.now(timezone.utc).strftime(
        "extract-%Y%m%dT%H%M%SZ"
    )

    failure_dir = (
        ROOT
        / "data"
        / "processed"
        / "_extraction_failures"
        / batch_id
    )
    failure_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    failure_count = 0
    skip_count = 0

    for row in targets:
        doc_id = row["doc_id"]

        try:
            check_url(
                row["source_url"],
                policy,
                candidate_urls,
            )

            source_dir = latest_snapshot(doc_id)
            source_html_path = source_dir / "source.html"
            source_metadata_path = source_dir / "metadata.json"

            metadata = json.loads(
                source_metadata_path.read_text(
                    encoding="utf-8"
                )
            )

            raw = source_html_path.read_bytes()
            raw_hash = hashlib.sha256(raw).hexdigest()

            if raw_hash != metadata["content_sha256"]:
                raise ValueError("원본 HTML 해시가 메타데이터와 다릅니다.")

            html, encoding = decode_html(raw)
            text, detected_dates = extract_body(html)

            output_dir = (
                ROOT
                / "data"
                / "processed"
                / doc_id
                / source_dir.name
            )

            if output_dir.exists():
                skip_count += 1
                print(f"[기존 결과] {doc_id}")
                continue

            processed = {
                **metadata,
                "document_version": raw_hash,
                "source_snapshot": source_dir.name,
                "source_metadata_path": (
                    source_metadata_path
                    .relative_to(ROOT)
                    .as_posix()
                ),
                "processed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "extraction_version": "ygpa-general-v1",
                "text_encoding": encoding,
                "text": text,
                "text_sha256": hashlib.sha256(
                    text.encode("utf-8")
                ).hexdigest(),
                "detected_page_update_dates": detected_dates,
                "date_detection_status": (
                    "one_value"
                    if len(detected_dates) == 1
                    else "none_or_conflicting"
                ),
                "ingestion_status": (
                    "text_extracted_pending_review"
                ),
                "index_approved": False,
            }

            output_dir.mkdir(parents=True)

            (output_dir / "document.txt").write_text(
                text,
                encoding="utf-8",
            )

            (output_dir / "document.json").write_text(
                json.dumps(
                    processed,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            success_count += 1
            print(f"[추출 완료] {doc_id}")

        except Exception as error:
            failure_count += 1
            save_failure(
                failure_dir,
                row,
                error,
            )
            print(f"[보류] {doc_id}: {error}")

    print()
    print(
        f"본문 추출 완료: 성공 {success_count}건, "
        f"기존 결과 {skip_count}건, "
        f"보류 {failure_count}건"
    )
    print(f"실패 기록: {failure_dir}")
    print("청크화와 검색 등록은 아직 하지 않았습니다.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"본문 추출 중단: {error}")