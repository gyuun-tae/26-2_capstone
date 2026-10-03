"""YGPA-032(여수광양항만공사 사용료 규정) PDF 11~23쪽 별표를 쪽 단위 청크로 만든다. 네트워크를 쓰지 않는다.

15번은 이 범위를 '표·도면·한시 요율 검토 전'으로 보류했다(semantic-attachments-v1 manifest의 pdf_appendix).
요율은 해수부 고시와 비교해 확인했고(선박입출항료 135원/톤 등), 한시 감면("2024년 12월 31일까지")은 기한이
지났을 수 있어 review_flags에 남기고 답변 단계(app/prompt.py)에서 기한 지난 날짜를 짚는다.
기존 청크는 건드리지 않고 같은 스냅샷 아래 pdf-annex-v2 폴더를 따로 만든다.
v2: 12·13쪽 요율표는 PDF 배치 그대로면 칸이 섞여 LLM이 다른 근거(해수부 고시 300원)를 고른다(f06). 원본 PDF 화면과
대조해 행 단위로 옮겨 적은 표 청크(TABLES)를 쪽 청크와 함께 넣는다.

  python scripts/24_chunk_ygpa032_annex.py
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ID = "YGPA-032"
VERSION = "pdf-annex-v2"
STRUCTURE = "text-corrected-v1"
# 쪽 → 별표 이름 (원문 머리글 기준: 11쪽 【별표 1】 1.사용료의 종류 및 요율, 15쪽 2.산정기준, 19쪽 【별표 2】)
SECTIONS = [
    (range(11, 15), "【별표 1】 항만시설사용료의 종류·요율"),
    (range(15, 19), "【별표 1】 항만시설사용료의 산정기준"),
    (range(19, 24), "【별표 2】 항만시설사용료별 감면율 및 감면대상"),
]
# 원본 PDF 12·13쪽 화면과 한 칸씩 대조해 옮겨 적음 (2026-10-03). 값이 바뀌면 원문 재수집 후 다시 대조한다
TABLES = [
    (12, "【별표 1】 화물입출항료 요율표", """(원문 12쪽 표를 행 단위로 옮겨 적음)
단위: 일반화물·기계하역처리화물·무연탄 원/1톤, 컨테이너화물 원/1TEU, 송유관이용액체화물 원/10바렐
- 일반화물 외항 입항: 194원
- 일반화물 외항 출항: 120원
- 일반화물 내항: 54원
- 기계하역처리화물 외항: 120원
- 기계하역처리화물 내항: 51원
- 컨테이너화물 외항: 2,742원
- 컨테이너화물 내항: 1,161원
- 송유관이용화물 외항: 111원
- 송유관이용화물 내항: 75원
- 무연탄: 27원
비고: 20' 이외의 컨테이너는 BOX 요금징수 — 10'는 1TEU 요율의 2분의 1배, 35'는 1.7배, 40'는 2배, 45'는 2.3배를 각각 적용. 외항컨테이너화물은 감면율(50%) 적용."""),
    (12, "【별표 1】 화물체화료·여객터미널이용료 요율표", """(원문 12쪽 표를 행 단위로 옮겨 적음)
화물체화료 (화물의 유통시설과 판매시설, 원/10톤·1일)
- 요금면제기간: 야적장 외항화물 입항 5일·출항 7일, 야적장 내항화물 4일, 창고 외항화물 입항 5일·출항 7일, 창고 내항화물 4일
- 면제기간 경과 후 1~10일: 야적장 외항화물 86원, 야적장 내항화물 65원, 창고 외항화물 187원, 창고 내항화물 132원
- 면제기간 경과 후 11~20일: 야적장 외항화물 187원, 야적장 내항화물 132원, 창고 외항화물 274원, 창고 내항화물 196원
- 면제기간 경과 후 21~30일: 야적장 외항화물 244원, 야적장 내항화물 183원, 창고 외항화물 292원, 창고 내항화물 210원
- 면제기간 경과 후 31일 이상: 야적장 외항화물 292원, 야적장 내항화물 210원, 창고 외항화물 339원, 창고 내항화물 236원
여객터미널이용료
- 국제여객터미널이용료(여객이용시설 중 대합실·여객승강용시설): 출항여객 1인당 1,500원, 부가세 포함. 6세 미만 소아는 제외
- 연안(종합)여객터미널이용료: 출항여객 1인당 여객운임의 10% (최저 400원, 최고 1,500원. 도서민과 2세 이상 13세 미만 어린이는 50% 할인), 부가세 포함. 2세 미만 영아 면제
- 주차장시설: 사장이 정하는 주차요금"""),
    (13, "【별표 1】 창고 및 야적장 사용료 요율표", """(원문 13쪽 표를 행 단위로 옮겨 적음)
라. 항만시설 전용사용료 (1) 창고 및 야적장 사용료 (화물의 유통시설과 판매시설, 원/1㎡, 1월)
- 창고(상옥) 외항화물: 1,029원
- 창고(상옥) 내항화물: 743원
- 야적장 포장 외항화물: 420원
- 야적장 포장 내항화물: 307원
- 야적장 미포장 외항화물: 277원
- 야적장 미포장 내항화물: 203원
비고: 컨테이너조작장의 사용료는 사용자와의 임대차계약에 의함
(4) 에이프런사용료: 부두의 구조 및 기능상 에이프런 전용사용이 필요한 경우에는 (1) 창고 및 야적장 사용료의 "포장·외항화물" 요율을 적용한다."""),
]
TIME_LIMITED = re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일\s*까지")


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def tidy(text: str) -> str:
    """PDF 배치용 공백을 줄인다. 칸 사이(공백 3개 이상)는 두 칸으로 남겨 표의 열 구분을 유지한다"""
    lines = [re.sub(r" {3,}", "  ", line.rstrip()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def build(root: Path) -> tuple[list[dict], dict]:
    base_dir = sorted((root / "data/chunks" / DOC_ID).glob("*/semantic-attachments-v1"))[-1]
    base = json.loads((base_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()[0])
    snap = base["source_snapshot"]
    blocks_path = f"data/processed/{DOC_ID}/{snap}/{STRUCTURE}/blocks.json"
    blocks_bytes = (root / blocks_path).read_bytes()
    blocks = json.loads(blocks_bytes)

    keep = ("doc_id", "document_version", "source_snapshot", "extraction_version", "text_sha256", "title",
            "source_url", "parent_source_url", "publisher", "fetched_at", "published_at", "updated_at",
            "date_status", "date_evidence")
    chunks = []
    for pages, section in SECTIONS:
        for page in pages:
            index, block = next((i, b) for i, b in enumerate(blocks) if b["locator"].get("page_number") == page)
            text = f"{section} ({page}쪽)\n{tidy(block['text'])}"
            flags = ["currentness_not_verified"] + (["time_limited_items"] if TIME_LIMITED.search(text) else [])
            chunks.append({
                **{k: base[k] for k in keep},
                "chunk_id": f"{DOC_ID}-" + sha(f"{VERSION}|{page}")[:24],
                "chunking_version": VERSION, "structure_version": STRUCTURE,
                "section_titles": [section], "text": text, "chunk_text_sha256": sha(text), "chunk_kind": "table",
                "source_locator": {"kind": "attachment_composite", "source_refs": [{
                    "path": blocks_path, "block_index": index, "locator": block["locator"],
                    "char_start": 0, "char_end": len(block["text"]), "offset_unit": "unicode_codepoint", "end_exclusive": True,
                }], "table_ids": []},
                "review_status": "draft_pending_chunk_review", "index_approved": False, "review_flags": flags,
            })
    for page, title, body in TABLES:
        index, block = next((i, b) for i, b in enumerate(blocks) if b["locator"].get("page_number") == page)
        text = f"{title}\n{body}"
        chunks.append({
            **{k: base[k] for k in keep},
            "chunk_id": f"{DOC_ID}-" + sha(f"{VERSION}|table|{title}")[:24],
            "chunking_version": VERSION, "structure_version": "manual-table-v1",
            "section_titles": [title], "text": text, "chunk_text_sha256": sha(text), "chunk_kind": "table",
            "source_locator": {"kind": "attachment_composite", "source_refs": [{
                "path": blocks_path, "block_index": index, "locator": block["locator"],
                "char_start": 0, "char_end": len(block["text"]), "offset_unit": "unicode_codepoint", "end_exclusive": True,
            }], "table_ids": []},
            "review_status": "draft_pending_chunk_review", "index_approved": False,
            "review_flags": ["currentness_not_verified", "manual_transcription_checked_against_pdf"],
        })
    manifest = dict(doc_id=DOC_ID, source_snapshot=snap, document_version=base["document_version"],
                    chunking_version=VERSION, input_hashes={blocks_path: sha(blocks_bytes)},
                    covers="semantic-attachments-v1 manifest의 pdf_appendix(보류) 범위, PDF 11~23쪽",
                    chunk_count=len(chunks), index_approved=False)
    return chunks, manifest


def save(root: Path, chunks: list[dict], manifest: dict) -> str:
    lines = [f"# {DOC_ID} 별표 청크 검토 ({VERSION})", "검색 승인 전 초안. 한시 감면(…까지)은 기한이 지났을 수 있다."]
    for c in chunks:
        lines += [f"## {c['section_titles'][0]} · {c['source_locator']['source_refs'][0]['locator']['page_number']}쪽", c["text"]]
    outputs = {"chunks.jsonl": "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks),
               "review.md": "\n\n".join(lines) + "\n"}
    expected = {**manifest, "output_hashes": {k: sha(v) for k, v in outputs.items()}}
    out = root / "data/chunks" / DOC_ID / manifest["source_snapshot"] / VERSION
    if (out / "manifest.json").exists():
        old = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        if all(old.get(k) == v for k, v in expected.items()):
            return "그대로"
        raise ValueError(f"{out}의 기존 청크와 다릅니다. 덮어쓰지 않습니다")
    out.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        (out / name).write_text(text, encoding="utf-8")
    created = {**expected, "created_at": datetime.now(timezone.utc).isoformat()}
    (out / "manifest.json").write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
    return "생성"


if __name__ == "__main__":
    chunks, manifest = build(ROOT)
    status = save(ROOT, chunks, manifest)
    limited = sum("time_limited_items" in c["review_flags"] for c in chunks)
    print(f"{DOC_ID} 별표 {len(chunks)}개 청크 (한시 조항 포함 {limited}개), 최대 {max(len(c['text']) for c in chunks)}자 | {status}")
