"""Collect explicitly registered attachments; no extraction or indexing.

Default: offline target preview. Add --download to make HTTP requests.
Only requests is required (already used by collect_one.py).
"""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "YGPA-Capstone/0.2"
TIMEOUT = (10, 30)
MAX_BYTES = 25 * 1024 * 1024
RETRY_CODES = {429, 500, 502, 503, 504}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def check_url(url, policy, role="attachment"):
    # Decode repeatedly for the deny check, but require exact original allowlist match.
    decoded = url
    for _ in range(5):
        newer = unquote(decoded)
        if newer == decoded:
            break
        decoded = newer
    parts = urlsplit(decoded)
    query = parse_qs(parts.query, keep_blank_values=True)
    if parts.scheme != "https" or parts.hostname not in policy["allowed_hosts"]:
        raise ValueError("공식 HTTPS 호스트가 아닙니다.")
    if parts.username or parts.password or parts.port not in (None, 443) or parts.fragment:
        raise ValueError("허용하지 않는 URL 구성입니다.")
    prefixes = set(policy["blocked_path_prefixes"]) | {"/hmpg/ygpa/comu/faqs/"}
    if any(parts.path.lower().startswith(p.lower()) for p in prefixes):
        raise ValueError("FAQ 평가 전용 경로입니다.")
    blocked = {k.lower(): set(v) for k, v in policy["blocked_query_values"].items()}
    blocked.setdefault("bbs_no", set()).add("230")
    if any(v in blocked.get(k.lower(), set()) for k, values in query.items() for v in values):
        raise ValueError("FAQ 평가 전용 게시판입니다.")
    if role == "robots":
        if url != f"https://{parts.hostname}/robots.txt":
            raise ValueError("robots.txt 주소가 아닙니다.")
    else:
        key = "allowed_parent_urls" if role == "parent" else "allowed_urls"
        if url not in policy[key]:
            raise ValueError(f"정책에 등록되지 않은 {role} URL입니다.")


def select_targets(root, priority="first", doc_ids=None):
    policy = json.loads((root / "docs/contracts/data_separation_policy.json").read_text(encoding="utf-8"))
    if policy.get("follow_links") is not False or policy.get("follow_redirects") is not False:
        raise ValueError("자동 순회·리다이렉트 금지 정책이 필요합니다.")
    if policy.get("require_attachment_provenance") is not True:
        raise ValueError("첨부 출처 검증 정책이 필요합니다.")
    catalog = (root / policy["catalog_path"]).resolve()
    if not catalog.is_relative_to(root.resolve()):
        raise ValueError("후보 CSV가 프로젝트 밖을 가리킵니다.")
    with catalog.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len({r["doc_id"] for r in rows}) != len(rows) or len({r["source_url"] for r in rows}) != len(rows):
        raise ValueError("후보 ID 또는 출처 URL이 중복됩니다.")
    mappings = policy["attachment_sources"]
    if len({m["doc_id"] for m in mappings}) != len(mappings):
        raise ValueError("첨부 정책의 ID가 중복됩니다.")
    by_id = {r["doc_id"]: r for r in rows}
    eligible = []
    for mapping in mappings:
        row = by_id.get(mapping["doc_id"])
        if not row or not re.fullmatch(r"YGPA-\d{3}", row["doc_id"]):
            raise ValueError("첨부 정책과 후보 ID가 일치하지 않습니다.")
        for key in ("source_url", "parent_source_url"):
            if row[key] != mapping[key]:
                raise ValueError(f"{row['doc_id']} CSV와 정책의 {key} 불일치")
        check_url(row["source_url"], policy)
        check_url(row["parent_source_url"], policy, "parent")
        eligible.append(row)
    if doc_ids:
        requested = set(doc_ids)
        if len(requested) != len(doc_ids) or requested - {r["doc_id"] for r in eligible}:
            raise ValueError("중복되거나 첨부 목록에 없는 문서 ID입니다.")
        targets = [r for r in eligible if r["doc_id"] in requested]
    else:
        targets = [r for r in eligible if priority == "all" or r["priority"] == "extension_first_batch"]
    if not targets:
        raise ValueError("선택된 첨부가 없습니다.")
    return policy, targets


class LinkParser(HTMLParser):
    """Read literal href/location links only; never execute JavaScript."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if attrs.get("onclick"):
            self.links.extend(re.findall(
                r"(?:window\.)?location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
                attrs["onclick"], re.I,
            ))


def verify_parent(data, row):
    text = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    if text is None:
        raise ValueError("부모 페이지의 문자 인코딩을 확인할 수 없습니다.")
    parser = LinkParser()
    parser.feed(text)
    for literal in parser.links:
        if urljoin(row["parent_source_url"], literal.strip()) == row["source_url"]:
            return {"method": "literal_html_link", "matched_url": row["source_url"],
                    "parent_source_url": row["parent_source_url"], "parent_sha256": digest(data)}
    raise ValueError("부모 화면에 등록된 첨부의 직접 링크가 없습니다. 다운로드를 보류합니다.")


def detect_format(data):
    # Signatures identify containers, not document correctness or currentness.
    if data.startswith(b"%PDF-") and b"%%EOF" in data[-4096:]:
        return "pdf", ".pdf"
    if data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")) and len(data) >= 512:
        # HWP 5 and legacy Office share this signature; do not call every OLE file HWP.
        return "ole_compound", ".ole"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "mimetype" in names:
                    info = archive.getinfo("mimetype")
                    if info.file_size > 200 or info.flag_bits & 1:
                        raise ValueError("ZIP 형식 식별 항목이 비정상입니다.")
                    mime = archive.read("mimetype").strip()
                    if mime == b"application/hwp+zip" and "Contents/content.hpf" in names:
                        return "hwpx", ".hwpx"
                if "[Content_Types].xml" in names and "word/document.xml" in names:
                    return "docx", ".docx"
        except (zipfile.BadZipFile, RuntimeError) as error:
            raise ValueError("손상되었거나 암호화된 ZIP 문서입니다.") from error
    raise ValueError("지원하는 문서 시그니처가 아닙니다. HTML 오류·로그인 응답 또는 다른 형식을 확인하세요.")


def server_filename(headers):
    message = Message()
    message["Content-Disposition"] = headers.get("Content-Disposition", "")
    return message.get_filename() or ""  # Metadata only; never used as a filesystem path.


class Client:
    def __init__(self, policy, session):
        self.policy, self.session = policy, session
        self.robots_cache = {}
        self.last_request = None

    def fetch(self, url, role, limit=MAX_BYTES, delay=1):
        check_url(url, self.policy, role)
        for attempt in range(3):
            if self.last_request is not None:
                time.sleep(max(0, delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.session.get(url, timeout=TIMEOUT, allow_redirects=False, stream=True) as response:
                    if response.status_code in RETRY_CODES and attempt < 2:
                        retry_after = response.headers.get("Retry-After", "")
                        if retry_after and (not retry_after.isdigit() or int(retry_after) > 60):
                            raise ValueError("서버가 긴 대기를 요청했습니다. 나중에 다시 실행하세요.")
                        time.sleep(max(2 ** (attempt + 1), int(retry_after or 0)))
                        continue
                    if 300 <= response.status_code < 400:
                        raise ValueError(f"리다이렉트 차단: HTTP {response.status_code}")
                    if response.url != url:
                        raise ValueError("요청 URL과 응답 URL이 다릅니다.")
                    check_url(response.url, self.policy, role)
                    if role == "robots" and response.status_code == 404:
                        return b"", requests.structures.CaseInsensitiveDict(response.headers), 404
                    if response.status_code != 200:
                        raise ValueError(f"HTTP {response.status_code}")
                    declared = response.headers.get("Content-Length", "")
                    if declared.isdigit() and int(declared) > limit:
                        raise ValueError("허용 파일 크기를 초과합니다.")
                    body = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_content(64 * 1024):
                        body.extend(chunk)
                        if len(body) > limit or time.monotonic() - started > 120:
                            raise ValueError("응답 크기 또는 다운로드 시간 제한을 초과했습니다.")
                    if not body:
                        raise ValueError("빈 응답입니다.")
                    return bytes(body), requests.structures.CaseInsensitiveDict(response.headers), 200
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError("재시도 횟수를 초과했습니다.")

    def robots(self, url):
        parts = urlsplit(url)
        robots_url = f"https://{parts.hostname}/robots.txt"
        if robots_url not in self.robots_cache:
            data, headers, status = self.fetch(robots_url, "robots", limit=1024 * 1024)
            if status == 404:
                self.robots_cache[robots_url] = None
            else:
                text = data.decode("utf-8-sig")
                if "html" in headers.get("Content-Type", "").lower() or re.search(r"<\s*(?:!doctype|html|body)", text, re.I):
                    raise ValueError("robots.txt 대신 HTML이 반환되었습니다.")
                parser = RobotFileParser()
                parser.parse(text.splitlines())
                self.robots_cache[robots_url] = parser
        rules = self.robots_cache[robots_url]
        if rules is None:
            return "not_found_404", 1
        # Re-evaluate EACH URL even though the parser is cached per host.
        if not rules.can_fetch(USER_AGENT, url):
            raise ValueError("robots.txt가 이 URL 수집을 금지합니다.")
        rate = rules.request_rate(USER_AGENT)
        delay = max(1, rules.crawl_delay(USER_AGENT) or 0,
                    rate.seconds / rate.requests if rate and rate.requests else 0)
        if delay > 60:
            raise ValueError("서버 수집 간격이 60초를 초과하여 자동 수집을 보류합니다.")
        return "allowed", delay

    def get(self, url, role, limit=MAX_BYTES):
        check_url(url, self.policy, role)
        status, delay = self.robots(url)
        data, headers, _ = self.fetch(url, role, limit, delay)
        return data, headers, status


def existing_snapshot(root, row):
    folder = root / "data/raw" / row["doc_id"]
    if not folder.exists():
        return None
    for snapshot in sorted(folder.iterdir(), reverse=True):
        if not snapshot.is_dir():
            continue
        try:
            meta = json.loads((snapshot / "metadata.json").read_text(encoding="utf-8"))
            raw = (root / meta["raw_path"]).resolve()
            if not raw.is_relative_to(snapshot.resolve()):
                continue
            if (meta["doc_id"] == row["doc_id"] and meta["source_url"] == row["source_url"]
                    and meta["parent_source_url"] == row["parent_source_url"]
                    and meta["ingestion_status"] == "raw_saved_pending_review"
                    and meta["provenance"]["matched_url"] == row["source_url"]
                    and meta["content_sha256"] == digest(raw.read_bytes())
                    and meta["provenance"]["parent_sha256"] == digest((snapshot / "parent_source.html").read_bytes())):
                return snapshot
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def collect(root, row, policy, client, batch_id, parent_cache):
    parent_url = row["parent_source_url"]
    if parent_url not in parent_cache:
        data, headers, robots = client.get(parent_url, "parent", limit=5 * 1024 * 1024)
        if "html" not in headers.get("Content-Type", "").lower():
            raise ValueError("부모 페이지가 HTML이 아닙니다.")
        parent_cache[parent_url] = (data, robots, datetime.now(timezone.utc).isoformat())
    parent, parent_robots, parent_time = parent_cache[parent_url]
    provenance = verify_parent(parent, row)
    data, headers, robots = client.get(row["source_url"], "attachment")
    content_type = headers.get("Content-Type", "")
    if "html" in content_type.lower() or "json" in content_type.lower():
        raise ValueError("첨부 대신 HTML/JSON 응답이 반환되었습니다.")
    actual_format, extension = detect_format(data)
    now = datetime.now(timezone.utc)
    output = root / "data/raw" / row["doc_id"] / now.strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    raw_path = output / ("source" + extension)
    metadata = {
        **row, "requested_url": row["source_url"], "final_url": row["source_url"],
        "fetched_at": now.isoformat(), "http_status": 200,
        "content_type": content_type, "server_filename": server_filename(headers),
        "actual_format": actual_format, "format_validation": "container_signature_only",
        "format_review_note": "OLE 컨테이너는 HWP 여부를 추출 단계에서 추가 확인" if actual_format == "ole_compound" else "본문·표·현행성 검증 전",
        "raw_path": raw_path.relative_to(root).as_posix(),
        "content_sha256": digest(data), "bytes": len(data),
        "robots_status": robots, "collection_batch": batch_id,
        "policy_version": policy["policy_version"],
        "ingestion_status": "raw_saved_pending_review", "index_approved": False,
        "provenance": {**provenance, "parent_fetched_at": parent_time,
                       "parent_robots_status": parent_robots,
                       "parent_raw_path": (output / "parent_source.html").relative_to(root).as_posix(),
                       "purpose": "provenance_only_do_not_index"},
    }
    try:
        raw_path.write_bytes(data)
        (output / "parent_source.html").write_bytes(parent)
        write_json(output / "metadata.json", metadata)  # Completion marker is written last.
    except OSError:
        for created in (raw_path, output / "parent_source.html", output / "metadata.json"):
            created.unlink(missing_ok=True)
        output.rmdir()
        raise
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--priority", choices=("first", "all"), default="first")
    selection.add_argument("--doc-ids", nargs="+")
    parser.add_argument("--download", action="store_true", help="실제 HTTP 수집 실행")
    parser.add_argument("--refresh", action="store_true", help="기존 원본을 보존하고 새 스냅샷 수집")
    args = parser.parse_args(argv)
    policy, targets = select_targets(ROOT, args.priority, args.doc_ids)
    for row in targets:
        print(f"{row['doc_id']} | {row['title']}")
    print(f"선택: {len(targets)}건")
    if not args.download:
        print("대상 확인만 완료. 네트워크 요청·파일 저장 없음. 실제 수집은 --download 옵션을 사용하세요.")
        return 0
    batch_id = datetime.now(timezone.utc).strftime("attachments-%Y%m%dT%H%M%S%fZ")
    failure_dir = ROOT / "data/raw/_collection_failures" / batch_id
    failure_dir.mkdir(parents=True, exist_ok=False)
    counts = {"saved": 0, "skipped": 0, "held": 0}
    results, parent_cache = [], {}
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})
        client = Client(policy, session)
        for row in targets:
            old = None if args.refresh else existing_snapshot(ROOT, row)
            if old:
                counts["skipped"] += 1
                results.append({"doc_id": row["doc_id"], "status": "skipped", "path": old.relative_to(ROOT).as_posix()})
                print(f"[기존 원본 유지] {row['doc_id']}")
                continue
            try:
                output = collect(ROOT, row, policy, client, batch_id, parent_cache)
                counts["saved"] += 1
                results.append({"doc_id": row["doc_id"], "status": "saved", "path": output.relative_to(ROOT).as_posix()})
                print(f"[저장 완료] {row['doc_id']}: {output}")
            except (OSError, ValueError, RuntimeError, requests.RequestException) as error:
                counts["held"] += 1
                failure = {"doc_id": row["doc_id"], "source_url": row["source_url"],
                           "parent_source_url": row["parent_source_url"], "error": str(error),
                           "failed_at": datetime.now(timezone.utc).isoformat(), "index_approved": False}
                write_json(failure_dir / (row["doc_id"] + ".json"), failure)
                results.append({"doc_id": row["doc_id"], "status": "held", "error": str(error)})
                print(f"[보류] {row['doc_id']}: {error}")
    write_json(failure_dir / "summary.json", {"batch_id": batch_id, **counts, "results": results})
    print(f"수집 결과: 성공 {counts['saved']}건, 기존 {counts['skipped']}건, 보류 {counts['held']}건")
    print(f"실행 기록: {failure_dir}")
    print("본문 추출·청크화·검색 등록은 수행하지 않았습니다.")
    return 1 if counts["held"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"수집 중단: {error}")
