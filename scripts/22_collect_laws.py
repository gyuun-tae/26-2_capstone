"""국가법령정보 Open API로 법령·고시 원문(JSON)을 받는다. 추출·청킹·색인은 하지 않는다.

대상: docs/contracts/law_sources.json. 인증값: 저장소 루트 .env의 LAW_OC (API에 등록한 IP에서만 동작).
기본은 목록 확인만 하고, --download일 때 바뀐 법령만 data/raw/LAW-xxx/<스냅샷>/에 저장한다.
버전 번호(법령 MST, 행정규칙 일련번호)가 직전 스냅샷과 같으면 받지 않는다 → 개정 확인용으로 다시 돌려도 된다.

  python scripts/22_collect_laws.py              # 현행 버전과 변경 여부만 보기
  python scripts/22_collect_laws.py --download   # 바뀐 것만 받기
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "docs/contracts/law_sources.json"
API = "https://www.law.go.kr/DRF"
USER_AGENT = "YGPA-Capstone/0.2"
TIMEOUT = 60

# target별 목록 응답 구조. 행정규칙은 법령과 이름·필드가 다르다
LIST_KEYS = {
    "law": dict(root="LawSearch", item="law", name="법령명한글", serial="법령일련번호", current=("현행연혁코드", "현행")),
    "admrul": dict(root="AdmRulSearch", item="admrul", name="행정규칙명", serial="행정규칙일련번호", current=("현행연혁구분", "현행")),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_oc(root: Path = ROOT) -> str:
    env = root / ".env"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        if line.strip().startswith("LAW_OC="):
            return line.split("=", 1)[1].strip()
    sys.exit("LAW_OC가 .env에 없습니다 (open.law.go.kr에서 받은 인증값)")


def get_json(path: str, params: dict, oc: str) -> tuple[dict, bytes]:
    url = f"{API}/{path}?" + urlencode({"OC": oc, "type": "JSON", **params})
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT) as r:
                raw = r.read()
            data = json.loads(raw)
            break
        except json.JSONDecodeError:
            # 등록되지 않은 IP·잘못된 OC면 JSON 대신 안내 HTML이 온다
            sys.exit(f"JSON이 아닌 응답입니다. 이 PC의 IP가 API에 등록돼 있는지 확인하세요: {raw[:200]!r}")
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    # 응답 안의 상세 링크에 OC가 들어 있다. 원본을 저장하기 전에 지운다 (공개 저장소·로그에 남지 않게)
    raw = json.dumps(data, ensure_ascii=False, indent=1).replace(oc, "OC_REMOVED").encode("utf-8")
    return json.loads(raw), raw


def find_current(entry: dict, oc: str) -> dict:
    """정확히 같은 이름의 현행 법령 하나를 찾는다. 없거나 둘 이상이면 멈춘다 (이름 오타·폐지 확인용)"""
    keys = LIST_KEYS[entry["target"]]
    data, _ = get_json("lawSearch.do", {"target": entry["target"], "query": entry["name"], "display": 100}, oc)
    items = data.get(keys["root"], {}).get(keys["item"]) or []
    items = [items] if isinstance(items, dict) else items
    field, value = keys["current"]
    found = {i[keys["serial"]]: i for i in items
             if i.get(keys["name"]) == entry["name"] and i.get(field, value) == value}
    if len(found) != 1:
        raise ValueError(f"{entry['doc_id']} '{entry['name']}' 현행 결과가 {len(found)}건입니다")
    item = next(iter(found.values()))
    return dict(serial=item[keys["serial"]], effective_date=item.get("시행일자", ""), item=item)


def latest_metadata(root: Path, doc_id: str) -> dict | None:
    snaps = sorted((root / "data/raw" / doc_id).glob("*/metadata.json"))
    return json.loads(snaps[-1].read_text(encoding="utf-8")) if snaps else None


def public_url(entry: dict, serial: str) -> str:
    """사람이 여는 국가법령정보센터 주소 (OC 없음)"""
    if entry["target"] == "law":
        return f"https://www.law.go.kr/법령/{quote(entry['name'])}"
    return f"https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq={serial}"


def collect(entry: dict, found: dict, oc: str, root: Path = ROOT) -> Path:
    params = {"target": entry["target"], ("MST" if entry["target"] == "law" else "ID"): found["serial"]}
    data, raw = get_json("lawService.do", params, oc)
    if oc in raw.decode("utf-8"):
        raise ValueError("원본에서 인증값을 지우지 못했습니다")
    if not (data.get("법령") or data.get("AdmRulService")):
        raise ValueError(f"{entry['doc_id']} 본문 응답 형식이 예상과 다릅니다: {list(data)[:5]}")
    fetched = datetime.now(timezone.utc)
    snapshot = fetched.strftime("%Y%m%dT%H%M%S%fZ")
    folder = root / "data/raw" / entry["doc_id"] / snapshot
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "source.json").write_bytes(raw)
    metadata = dict(
        doc_id=entry["doc_id"], title=entry["name"], target=entry["target"], tier=entry["tier"],
        serial=found["serial"], effective_date=found["effective_date"],
        source_url=public_url(entry, found["serial"]),
        api_request={"path": "lawService.do", **params, "type": "JSON"},  # OC 제외
        fetched_at=fetched.isoformat(), source_snapshot=snapshot, source_sha256=digest(raw),
        sources_sha256=digest(SOURCES.read_bytes()),
    )
    (folder / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", action="store_true", help="바뀐 법령의 원문을 받아 저장")
    parser.add_argument("--tier", type=int, default=1, help="이 단계 이하만 (기본 1)")
    args = parser.parse_args()

    oc = read_oc()
    entries = [e for e in json.loads(SOURCES.read_text(encoding="utf-8"))["laws"] if e["tier"] <= args.tier]
    for entry in entries:
        found = find_current(entry, oc)
        last = latest_metadata(ROOT, entry["doc_id"])
        changed = not last or last["serial"] != found["serial"]
        status = "변경" if last and changed else "신규" if changed else "그대로"
        line = f"{entry['doc_id']} {entry['name']} | 버전 {found['serial']} | 시행 {found['effective_date']} | {status}"
        if changed and args.download:
            line += f" → {collect(entry, found, oc).relative_to(ROOT)}"
        print(line)
        time.sleep(0.5)  # 공용 API에 몰아서 요청하지 않는다


if __name__ == "__main__":
    main()
