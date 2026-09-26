import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.robotparser import RobotFileParser

import requests


ROOT = Path(__file__).resolve().parents[1]
DOC_ID_TO_SKIP = "YGPA-001"
USER_AGENT = "YGPA-Capstone/0.1"
TIMEOUT = (10, 30)


def load_policy():
    path = ROOT / "docs" / "contracts" / "data_separation_policy.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_candidates(policy):
    catalog_path = ROOT / policy["catalog_path"]

    with catalog_path.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    targets = [
        row for row in rows
        if row["doc_id"] != DOC_ID_TO_SKIP
    ]

    if len(targets) != 19:
        raise ValueError(
            f"수집 대상이 19건이 아닙니다: {len(targets)}건"
        )

    return rows, targets


def check_candidate_url(url, policy, candidate_urls):
    decoded_url = unquote(url)
    parts = urlsplit(decoded_url)
    query = parse_qs(parts.query, keep_blank_values=True)

    if parts.scheme != "https":
        raise ValueError("HTTPS 주소가 아닙니다.")

    if parts.hostname not in policy["allowed_hosts"]:
        raise ValueError("허용된 공식 호스트가 아닙니다.")

    for blocked_prefix in policy["blocked_path_prefixes"]:
        if parts.path.lower().startswith(blocked_prefix.lower()):
            raise ValueError("FAQ 평가 전용 경로입니다.")

    for key, blocked_values in policy["blocked_query_values"].items():
        if any(
            value in blocked_values
            for value in query.get(key, [])
        ):
            raise ValueError("FAQ 평가 전용 게시판입니다.")

    if url not in candidate_urls:
        raise ValueError("후보 CSV에 없는 URL입니다.")


def get_robots(session, url, cache):
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"

    if robots_url in cache:
        return cache[robots_url]

    response = session.get(
        robots_url,
        timeout=TIMEOUT,
        allow_redirects=False,
    )

    if 300 <= response.status_code < 400:
        raise RuntimeError("robots.txt가 다른 주소로 이동했습니다.")

    if response.status_code == 404:
        result = ("not_found_404", 1)

    elif response.status_code != 200:
        raise RuntimeError(
            f"robots.txt 확인 실패: HTTP {response.status_code}"
        )

    elif "<html" in response.text.lower():
        raise RuntimeError(
            "robots.txt 대신 HTML이 반환되었습니다."
        )

    else:
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())

        if not parser.can_fetch(USER_AGENT, url):
            raise RuntimeError(
                "robots.txt에서 자동 수집을 허용하지 않습니다."
            )

        delay = parser.crawl_delay(USER_AGENT) or 0
        result = ("allowed", max(1, int(delay)))

    cache[robots_url] = result
    return result


def decode_html(response):
    raw = response.content

    for encoding in ("utf-8", "cp949"):
        try:
            return raw, raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "unknown",
        raw,
        0,
        len(raw),
        "UTF-8과 CP949로 해석할 수 없습니다.",
    )


def save_failure(failure_dir, row, error):
    failure = {
        "doc_id": row["doc_id"],
        "title": row["title"],
        "source_url": row["source_url"],
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "error": str(error),
        "index_approved": False,
    }

    failure_path = failure_dir / f"{row['doc_id']}.json"
    failure_path.write_text(
        json.dumps(
            failure,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def collect_one(session, row, policy, candidate_urls, robots_cache, batch_id):
    url = row["source_url"]

    check_candidate_url(
        url,
        policy,
        candidate_urls,
    )

    robots_status, delay = get_robots(
        session,
        url,
        robots_cache,
    )

    time.sleep(delay)

    response = session.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=False,
    )

    if 300 <= response.status_code < 400:
        raise RuntimeError(
            f"리다이렉트 응답입니다: HTTP {response.status_code}"
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"문서 수집 실패: HTTP {response.status_code}"
        )

    content_type = response.headers.get(
        "Content-Type",
        "",
    ).lower()

    if "text/html" not in content_type:
        raise RuntimeError(
            f"HTML 문서가 아닙니다: {content_type}"
        )

    if response.url != url:
        raise RuntimeError(
            f"최종 URL이 요청 URL과 다릅니다: {response.url}"
        )

    raw, html, encoding = decode_html(response)

    title_match = re.search(
        r"<title\b[^>]*>(.*?)</title>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    page_title = ""
    if title_match:
        page_title = re.sub(
            r"\s+",
            " ",
            title_match.group(1),
        ).strip()

    fetched_at = datetime.now(timezone.utc)
    snapshot_id = fetched_at.strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    output_dir = (
        ROOT
        / "data"
        / "raw"
        / row["doc_id"]
        / snapshot_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    source_path = output_dir / "source.html"
    source_path.write_bytes(raw)

    metadata = {
        **row,
        "requested_url": url,
        "final_url": response.url,
        "page_title": page_title,
        "fetched_at": fetched_at.isoformat(),
        "http_status": response.status_code,
        "content_type": content_type,
        "encoding": encoding,
        "raw_path": source_path.relative_to(ROOT).as_posix(),
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "robots_status": robots_status,
        "collection_batch": batch_id,
        "policy_version": policy["policy_version"],
        "ingestion_status": "raw_saved_pending_review",
        "index_approved": False,
    }

    (output_dir / "metadata.json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return output_dir


def main():
    policy = load_policy()
    rows, targets = load_candidates(policy)

    candidate_urls = {
        row["source_url"]
        for row in rows
    }

    batch_id = datetime.now(timezone.utc).strftime(
        "batch-%Y%m%dT%H%M%SZ"
    )

    failure_dir = (
        ROOT
        / "data"
        / "raw"
        / "_collection_failures"
        / batch_id
    )
    failure_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    session = requests.Session()
    session.headers.update(
        {"User-Agent": USER_AGENT}
    )

    robots_cache = {}
    success_count = 0
    failure_count = 0

    for row in targets:
        print(
            f"[수집 시작] {row['doc_id']} "
            f"{row['title']}"
        )

        try:
            output_dir = collect_one(
                session,
                row,
                policy,
                candidate_urls,
                robots_cache,
                batch_id,
            )

            success_count += 1
            print(
                f"[저장 완료] {row['doc_id']} "
                f"{output_dir}"
            )

        except Exception as error:
            failure_count += 1
            save_failure(
                failure_dir,
                row,
                error,
            )
            print(
                f"[보류] {row['doc_id']} "
                f"{error}"
            )

    print()
    print(
        f"수집 완료: 성공 {success_count}건, "
        f"보류 {failure_count}건"
    )
    print(f"배치 ID: {batch_id}")
    print(f"실패 기록: {failure_dir}")
    print("FAQ 데이터는 수집하지 않았습니다.")
    print("검색 등록은 아직 하지 않았습니다.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"수집 중단: {error}")