import hashlib
import json
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from collect_one import check_url


ROOT = Path(__file__).resolve().parents[1]
DOC_ID = "YGPA-001"


class BodyParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0
        self.step_count = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.skip_depth += 1

        if self.skip_depth:
            return

        attrs_map = dict(attrs)
        classes = (attrs_map.get("class") or "").split()

        if tag in {"div", "p", "h3", "li", "br"}:
            self.parts.append("\n")

        if tag == "li":
            self.parts.append("- ")

        if "step-title" in classes:
            self.step_count += 1
            self.parts.append(f"\n{self.step_count}. ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return

        if not self.skip_depth and tag in {"div", "p", "h3", "li", "em"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def find_latest_snapshot():
    raw_root = ROOT / "data" / "raw" / DOC_ID

    snapshots = [
        path for path in raw_root.iterdir()
        if path.is_dir()
    ]

    if not snapshots:
        raise ValueError("수집된 원본 폴더가 없습니다.")

    return sorted(snapshots, key=lambda path: path.name, reverse=True)[0]


def extract_body(html):
    blocks = re.findall(
        r"<!--\s*내용 시작\s*-->(.*?)<!--\s*내용 끝\s*-->",
        html,
        flags=re.DOTALL,
    )

    if len(blocks) != 1:
        raise ValueError(
            "본문 시작·끝 경계를 찾지 못했습니다. 원본 HTML 구조를 확인하세요."
        )

    body = blocks[0]

    update_dates = set(
        re.findall(
            r"""\$\(["']#cont_last_mdfcn_dt["']\)\.html\(["'](\d{4}-\d{2}-\d{2})["']\)""",
            body,
        )
    )

    if len(update_dates) != 1:
        raise ValueError("페이지 갱신일을 하나로 확정할 수 없습니다.")

    updated_at = date.fromisoformat(update_dates.pop()).isoformat()

    parser = BodyParser()
    parser.feed(body)
    parser.close()

    lines = []

    for line in "".join(parser.parts).splitlines():
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            lines.append(line)

    text = "\n".join(lines) + "\n"

    expected_sections = [
        "신청자격",
        "신청절차",
        "1. 회원가입",
        "2. 신청서 작성",
        "3. 신청서 검토",
        "4. 신청서 완료",
    ]

    positions = [text.find(section) for section in expected_sections]

    if parser.step_count != 4:
        raise ValueError("신청 절차 단계 수가 예상과 다릅니다.")

    if -1 in positions:
        raise ValueError("필수 본문 제목이나 절차가 빠졌습니다.")

    if positions != sorted(positions):
        raise ValueError("본문 절차 순서가 예상과 다릅니다.")

    return text, updated_at


def main():
    source_dir = find_latest_snapshot()
    source_html_path = source_dir / "source.html"
    source_metadata_path = source_dir / "metadata.json"

    metadata = json.loads(
        source_metadata_path.read_text(encoding="utf-8")
    )

    if metadata["doc_id"] != DOC_ID:
        raise ValueError("문서 ID가 일치하지 않습니다.")

    check_url(metadata["source_url"])
    check_url(metadata["final_url"])

    raw_bytes = source_html_path.read_bytes()
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()

    if raw_hash != metadata["content_sha256"]:
        raise ValueError("원본 HTML의 해시가 수집 당시 기록과 다릅니다.")

    html = raw_bytes.decode("utf-8")
    text, updated_at = extract_body(html)

    output_dir = (
        ROOT
        / "data"
        / "processed"
        / DOC_ID
        / source_dir.name
    )

    if output_dir.exists():
        raise FileExistsError(
            f"처리 결과 폴더가 이미 있습니다: {output_dir}"
        )

    processed_at = datetime.now(timezone.utc).isoformat()
    text_hash = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()

    document = {
        **metadata,
        "updated_at": updated_at,
        "date_status": "page_updated",
        "date_evidence": (
            "원본 본문의 cont_last_mdfcn_dt 날짜 표시 스크립트에서 확인한 값. "
            "페이지 갱신일이며 발행일이나 규정 시행일이 아님."
        ),
        "document_version": raw_hash,
        "source_snapshot": source_dir.name,
        "source_metadata_path": (
            source_metadata_path.relative_to(ROOT).as_posix()
        ),
        "processed_at": processed_at,
        "extraction_version": "ygpa001-v1",
        "text": text,
        "text_sha256": text_hash,
        "section_titles": [
            "신청자격",
            "신청절차",
        ],
        "ingestion_status": "text_extracted_pending_review",
        "index_approved": False,
    }

    output_dir.mkdir(parents=True)

    (output_dir / "document.txt").write_text(
        text,
        encoding="utf-8",
    )

    (output_dir / "document.json").write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"본문 1건 추출 완료: {output_dir}")
    print("다음 단계: document.txt 원문 대조. 아직 검색에 등록되지 않았습니다.")


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        KeyError,
        FileExistsError,
    ) as error:
        raise SystemExit(f"추출 중단: {error}")