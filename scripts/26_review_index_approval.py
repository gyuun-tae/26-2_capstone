"""색인 승인 검토: docs/contracts/index_approval_policy.md 기준으로 청크마다 승인 상태를 정해 승인 기록에 남긴다.

청크 파일은 고치지 않는다. 결과: data/catalog/index_approvals.json (Git에 올림 — 무엇을 언제 왜 승인했는지 기록).
현행성 재확인을 위해 공식 출처(YGPA 사이트, 국가법령정보 API)를 다시 조회한다. 법령 API는 등록한 IP에서만 동작.

  python scripts/26_review_index_approval.py            # 검토하고 승인 기록 저장
  python scripts/26_review_index_approval.py --offline  # 조회 없이 1~3·5번만 (현행성은 held로 남음, 저장 안 함)
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag import dense  # noqa: E402

POLICY_VERSION = "1.0"
LEDGER = ROOT / "data/catalog/index_approvals.json"
ALLOWED_HOSTS = {"www.ygpa.or.kr", "www.law.go.kr"}
USER_AGENT = "YGPA-Capstone/0.2"
# 정책 5번 표: 표시 → 승인 시 붙일 주의 문구 (None이면 주의 없이 승인)
FLAG_RULES = {
    "currentness_not_verified": None,  # 4번 현행성 재확인으로 해소
    "partial_document": None,
    "table_only_partial_document": None,
    "appendix_material_partially_held": None,
    "time_limited_items": "기한 있는 조항 — 지난 기한은 답변 단계에서 표시",
    "time_sensitive_schedule_confirm_with_operator": "일정 공지 — 운영자 확인 필요",
    "temporary_reservation_restriction_included": "예약 제한 공지 — 답변 첫 문장에서 안내",
    "manual_transcription_checked_against_pdf": "원본 PDF와 대조해 옮겨 적은 표",
}


def load_module(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def latest_snapshot(doc_id: str) -> Path | None:
    folder = ROOT / "data/raw" / doc_id
    snaps = sorted(p for p in folder.iterdir() if p.is_dir()) if folder.exists() else []
    return snaps[-1] if snaps else None


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as r:
        raw = r.read()
    time.sleep(0.5)  # 공공기관 사이트·API에 몰아서 요청하지 않는다
    return raw


# ---------- 4번 현행성 재확인 (문서 단위) ----------

def check_law(doc_id: str, snap: Path, chunks: list[dict], c22, oc: str, today: date) -> tuple[bool, str]:
    meta = json.loads((snap / "metadata.json").read_text(encoding="utf-8"))
    entry = {"doc_id": doc_id, "name": meta["title"], "target": meta["target"]}
    found = c22.find_current(entry, oc)
    effective = found["effective_date"]
    if found["serial"] != meta["serial"] or effective != meta["effective_date"]:
        return False, f"현행 버전이 바뀜: 수집 {meta['serial']}/{meta['effective_date']} → 현행 {found['serial']}/{effective} (22번으로 다시 받기)"
    if any(c.get("effective_at", "").replace("-", "") != effective for c in chunks):
        return False, "청크 시행일이 현행 시행일과 다름 (23번 다시 실행)"
    if effective > today.strftime("%Y%m%d"):
        return False, f"시행일 {effective}이 아직 오지 않음"
    return True, f"현행 버전 {found['serial']}·시행 {effective} 확인"


def check_page(snap: Path, c25) -> tuple[bool, str]:
    meta = json.loads((snap / "metadata.json").read_text(encoding="utf-8"))
    url = meta.get("final_url") or meta["source_url"]

    def body(html: str) -> str | None:
        text = c25.html_text(html)
        start, end = text.find("X(Twitter)"), text.find("담당자 만족도 평가")
        return text[start + len("X(Twitter)"):end].strip() if 0 <= start < end else None

    old = body((snap / "source.html").read_text(encoding="utf-8", errors="replace"))
    new = body(fetch(url).decode("utf-8", errors="replace"))
    if old is None or new is None:
        return False, "본문 경계를 찾지 못함 (사이트 구조 변경?)"
    return (True, "오늘 받은 페이지 본문이 수집본과 같음") if old == new else (False, "페이지 본문이 바뀜 (다시 수집)")


def check_file(snap: Path) -> tuple[bool, str]:
    meta = json.loads((snap / "metadata.json").read_text(encoding="utf-8"))
    source = next(p for p in snap.iterdir() if p.name.startswith("source.") and p.suffix != ".html")
    now = fetch(meta.get("final_url") or meta["source_url"])
    if sha(now) == sha(source.read_bytes()):
        return True, f"오늘 받은 파일 SHA-256이 수집본과 같음 ({source.name})"
    return False, "첨부 파일이 바뀜 (다시 수집)"


def check_org(doc_id: str, snap: Path, chunks: list[dict], c25) -> tuple[bool, str]:
    saved = json.loads((snap / "source.json").read_text(encoding="utf-8"))
    if doc_id == "ORG-000":
        def current():
            return [dept for _, dept in c25.org_structure(fetch(c25.HOST + c25.ORG_CHART).decode("utf-8"))]
        expected, what = list(saved), "조직도 부서 목록"
    else:
        dept = chunks[0]["section_titles"][0]

        def current():
            return [list(r) for r in c25.duties(dept)]
        expected, what = saved, f"{dept} 담당업무·전화"
    # 사이트가 연속 요청에 잠깐 빈 결과를 돌려준 적이 있다(2026-10-04) → 빈 결과는 확인 실패, 다르면 잠시 뒤 한 번 더
    for attempt in range(2):
        now = current()
        if now == expected:
            return True, f"{what}: 수집본과 같음"
        if attempt == 0:
            time.sleep(3)
    if not now:
        raise RuntimeError(f"{what} 조회 결과가 비어 있음")
    return False, f"{what}: 바뀜 (25번 다시 실행)"


# ---------- 청크 단위 판정 (1·2·3·5번) ----------

def decide(chunk: dict, doc_check: tuple[bool, str] | None, latest: str | None, policy: dict) -> tuple[str, list[str]]:
    """(상태, 사유·주의 목록). doc_check는 4번 결과 (None이면 확인 안 함)"""
    host = urlparse(chunk["source_url"]).hostname
    if dense.is_blocked(chunk["source_url"], policy):
        return "excluded", ["FAQ(최종평가 전용) 출처"]
    if host not in ALLOWED_HOSTS:
        return "held", [f"허용되지 않은 출처 {host}"]
    if chunk.get("chunk_kind") in dense.EXCLUDED_KINDS:
        return "excluded", ["과거 부칙"]
    if chunk["doc_id"] in dense.SUPERSEDED:
        return "excluded", [f"{dense.SUPERSEDED[chunk['doc_id']]}로 대체됨"]
    if not chunk.get("text", "").strip() or sha(chunk["text"]) != chunk["chunk_text_sha256"]:
        return "held", ["본문이 비었거나 본문 해시가 맞지 않음"]
    if latest and chunk["source_snapshot"] != latest:
        return "held", [f"최신 수집본({latest})이 아닌 {chunk['source_snapshot']}에서 만든 청크"]
    if doc_check is None:
        return "held", ["현행성 확인 안 함"]
    if not doc_check[0]:
        return "held", [doc_check[1]]
    notes = []
    for flag in chunk.get("review_flags", []):
        if flag == "historical_provision_not_current_rule":
            return "excluded", ["과거 규정"]
        if flag not in FLAG_RULES:
            return "held", [f"기준에 없는 검토 표시 {flag} — 정책 5번 표 갱신 필요"]
        if FLAG_RULES[flag]:
            notes.append(FLAG_RULES[flag])
    if chunk.get("date_status") == "conflicting":
        notes.append("페이지 날짜 표시가 서로 다름 — 본문은 오늘 원문과 같음")
    return ("approved_with_notes" if notes else "approved"), notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    policy = json.loads((ROOT / "docs/contracts/data_separation_policy.json").read_text(encoding="utf-8"))
    chunks = dense.load_chunks(ROOT)
    by_doc: dict[str, list[dict]] = {}
    for c in chunks:
        by_doc.setdefault(c["doc_id"], []).append(c)

    today = datetime.now(timezone.utc).astimezone().date()
    c22 = load_module("c22", "22_collect_laws.py")
    c25 = load_module("c25", "25_collect_ygpa_org_hinterland.py")
    oc = None if args.offline else c22.read_oc(ROOT)

    documents, decisions = {}, {}
    for doc_id, doc_chunks in sorted(by_doc.items()):
        snap = latest_snapshot(doc_id)
        check = None
        if not args.offline and snap and not all(c["doc_id"] in dense.SUPERSEDED or c.get("chunk_kind") in dense.EXCLUDED_KINDS
                                                  for c in doc_chunks):
            try:
                if doc_id.startswith("LAW-"):
                    check = check_law(doc_id, snap, doc_chunks, c22, oc, today)
                elif doc_id.startswith("ORG-"):
                    check = check_org(doc_id, snap, doc_chunks, c25)
                elif (snap / "source.html").exists():
                    check = check_page(snap, c25)
                else:
                    check = check_file(snap)
            except Exception as e:  # 조회 실패는 승인하지 않는다
                check = (False, f"현행성 확인 실패: {type(e).__name__}: {e}")
        documents[doc_id] = {"currentness": None if check is None else {"ok": check[0], "detail": check[1]},
                             "latest_snapshot": snap.name if snap else None, "chunks": len(doc_chunks)}
        for c in doc_chunks:
            status, notes = decide(c, check, snap.name if snap else None, policy)
            decisions[c["chunk_id"]] = {"doc_id": doc_id, "status": status, "chunk_text_sha256": c["chunk_text_sha256"],
                                        "notes": notes}
        print(f"{doc_id} | {Counter(decisions[c['chunk_id']]['status'] for c in doc_chunks)} | "
              f"{documents[doc_id]['currentness']['detail'] if check else '현행성 확인 안 함'}")

    summary = dict(Counter(d["status"] for d in decisions.values()))
    print("합계", summary)
    if args.offline:
        print("--offline: 승인 기록을 저장하지 않음")
        return
    LEDGER.write_text(json.dumps({
        "policy": "docs/contracts/index_approval_policy.md", "policy_version": POLICY_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(), "reviewer": "자료 담당 (26번 자동 검토)",
        "summary": summary, "documents": documents, "chunks": decisions,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"저장: {LEDGER.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
