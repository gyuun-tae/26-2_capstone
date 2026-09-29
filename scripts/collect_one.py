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
POLICY = json.loads(
    (ROOT / "docs/contracts/data_separation_policy.json").read_text(encoding="utf-8")
)
DOC_ID = "YGPA-001"
USER_AGENT = "YGPA-Capstone/0.1"


def check_url(url):
    """FAQ 차단을 먼저 검사하고, 허용한 URL만 통과시킵니다."""
    parts = urlsplit(unquote(url))
    query = parse_qs(parts.query, keep_blank_values=True)
    if any(parts.path.lower().startswith(p.lower())
           for p in POLICY["blocked_path_prefixes"]):
        raise ValueError("평가 전용 FAQ 경로는 수집할 수 없습니다.")
    for key, blocked in POLICY["blocked_query_values"].items():
        if any(v in blocked for v in query.get(key, [])):
            raise ValueError("평가 전용 FAQ 게시판은 수집할 수 없습니다.")
    if parts.scheme != "https" or parts.hostname not in POLICY["allowed_hosts"]:
        raise ValueError("허용한 공식 HTTPS 주소가 아닙니다.")
    if url not in POLICY["allowed_urls"]:
        raise ValueError("현재 수집을 허용한 문서 URL이 아닙니다.")


def get_page(url):
    # 302로 FAQ나 로그인 화면에 이동하더라도 따라가지 않습니다.
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT},
        timeout=(10, 30), allow_redirects=False
    )
    if 300 <= response.status_code < 400:
        raise RuntimeError("주소 이동 응답입니다. 이동 경로를 먼저 확인해야 합니다.")
    return response


def check_robots(url):
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    response = get_page(robots_url)
    if response.status_code == 404:
        return "not_found_404", 1
    if response.status_code != 200:
        raise RuntimeError(f"robots.txt 확인 실패: HTTP {response.status_code}")
    if "<html" in response.text.lower():
        raise RuntimeError("robots.txt 대신 HTML이 반환되어 확인이 필요합니다.")
    rules = RobotFileParser()
    rules.parse(response.text.splitlines())
    if not rules.can_fetch(USER_AGENT, url):
        raise RuntimeError("robots.txt에서 이 문서의 자동 수집을 허용하지 않습니다.")
    return "allowed", max(1, rules.crawl_delay(USER_AGENT) or 0)


def main():
    with (ROOT / POLICY["catalog_path"]).open(encoding="utf-8-sig", newline="") as f:
        rows = [row for row in csv.DictReader(f) if row["doc_id"] == DOC_ID]
    if len(rows) != 1:
        raise ValueError("후보 목록에 문서 ID가 정확히 한 번 있어야 합니다.")
    row = rows[0]
    url = row["source_url"]
    check_url(url)  # 네트워크 요청 전에 차단

    robots_status, delay = check_robots(url)
    time.sleep(delay)
    response = get_page(url)
    if response.status_code != 200:
        raise RuntimeError(f"문서 수집 실패: HTTP {response.status_code}")
    if "text/html" not in response.headers.get("Content-Type", "").lower():
        raise RuntimeError("HTML 안내 문서가 아닌 응답입니다.")
    check_url(response.url)

    raw = response.content
    html = raw.decode("utf-8")  # 한글 해석 실패 시 저장하지 않고 중단
    title = re.search(r"<title\b[^>]*>(.*?)</title>", html, re.I | re.S)
    if not title or row["title"] not in title.group(1):
        raise RuntimeError("예상한 문서 제목이 없습니다. 오류·로그인 화면인지 확인하세요.")
    if "신청자격" not in html or "신청절차" not in html:
        raise RuntimeError("예상한 안내 본문이 없습니다. 페이지를 확인하세요.")

    now = datetime.now(timezone.utc)
    output = ROOT / "data/raw" / DOC_ID / now.strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    (output / "source.html").write_bytes(raw)
    metadata = {
        **row,
        "fetched_at": now.isoformat(),
        "final_url": response.url,
        "http_status": response.status_code,
        "raw_path": (output / "source.html").relative_to(ROOT).as_posix(),
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "robots_status": robots_status,
        "policy_version": POLICY["policy_version"],
        "ingestion_status": "raw_saved_pending_review",
        "index_approved": False,
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"문서 1건 저장 완료: {output}")
    print("다음 단계: 원본 확인 → 본문 추출. 아직 검색에 등록되지 않았습니다.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, requests.RequestException) as error:
        raise SystemExit(f"수집 중단: {error}")

