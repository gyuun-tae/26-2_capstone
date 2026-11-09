"""V3 이미지·도면: VLM(Qwen3-VL-8B)으로 이미지 내용을 글로 옮긴 초안을 만든다 (2026-11-09).

VLM = 이미지와 지시문을 함께 받아 글로 답하는 모델. OCR과 달리 지도·도면의 위치 관계, 표 구조까지 문장으로 푼다.
대신 없는 내용을 지어낼 수 있으므로 결과는 "초안"이다 — 색인에 넣을 때 확인 필요 표시를 달고, 핵심 도면은 사람이 검수한다.

준비 (둘 중 하나)
- 기본: AIPub H100 워크스페이스에서 vLLM + 임시 터널 (infra/aipub_vlm/README.md) → .env에 VLM_URL·VLM_API_KEY
- 대안: 기존 GPU 서버에서 tmux kill-session -t qwen && bash start_vlm.sh (그동안 챗봇 답변이 멈춤),
  관문 gateway.py가 model "vlm"을 받는 판이어야 함 → .env의 GPU_URL·GPU_API_KEY (16번과 같음)

실행(저장소 루트)
  uv run --no-project --with pillow --with httpx python scripts/31_vlm_drafts.py --sample          # 시험 이미지(data/catalog/vlm_sample_v1.json)
  uv run --no-project --with pillow --with httpx python scripts/31_vlm_drafts.py --all             # VLM 대상 전체(image_inventory.json의 vlm_target)
  ... --dry-run    GPU에 보내지 않고 이미지 준비(크기 줄이기)만 확인
  ... --report     결과를 OCR·사람 전사·alt와 나란히 놓은 검토 파일 data/processed/vlm_review.md 를 만든다 (GPU 불필요)
  ... --redo       이미 만든 초안도 다시 만든다 (기본: 같은 모델·지시문 판이면 건너뜀 → 끊겨도 이어서 돌릴 수 있음)
  uv run --no-project python scripts/31_vlm_drafts.py --all --split   # 초안을 나눈다 (GPU 불필요) → 29번이 읽음

결과: data/processed/vlm_drafts.json  {sha256: {text, model, prompt_version, doc_id, created, seconds, finish_reason, tokens, sent, repeats_removed}}

나누기(--split, 2026-11-09 시험 20장 결과로 정한 기준 — 미디어 질문셋·FAQ는 보지 않음)
- auto: 글자 이미지(절차·흐름도·카드뉴스·공고 등). 장식 설명 줄("정보 없음: …")을 지우고 data/processed/vlm_accepted.json 에 넣는다
        → 29번이 OCR 대신 본문에 넣고 vlm_text_unverified 표시
- review: 지도·도면(제목·alt·첫 줄로 판단) 또는 반복으로 잘린 것. 8B 모델이 이름·숫자를 지어내므로 색인에 넣지 않는다
        → data/processed/vlm_review_queue.csv. 핵심 도면은 사람이 원본과 대조해 data/catalog/image_transcripts.json 에 옮긴다
- none: 사진·장식("정보 없음"으로 시작)이거나 글이 너무 짧음 → 넣지 않는다 (alt·OCR 처리는 29번 그대로)
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "data/processed/image_inventory.json"  # 30번 결과
SAMPLE = ROOT / "data/catalog/vlm_sample_v1.json"
OUT = ROOT / "data/processed/vlm_drafts.json"
REPORT = ROOT / "data/processed/vlm_review.md"
OCR_CACHE = ROOT / "data/processed/ocr_cache.json"
TRANSCRIPTS = ROOT / "data/catalog/image_transcripts.json"
ACCEPTED = ROOT / "data/processed/vlm_accepted.json"  # --split 결과, 29번이 읽는다
QUEUE = ROOT / "data/processed/vlm_review_queue.csv"
MAP_WORDS = re.compile(r"지도|도면|평면도|배치도|조감도|위치도|현황도|구역도|항세도|map|plan|平面|配置|地図|地图", re.I)
DECOR = re.compile(r"^\s*\[?\s*정보 없음\s*:")  # 장식 설명 줄 (본문 중간에 섞여 나옴)

MODEL = "vlm"  # 관문의 서빙 이름. 실제 모델은 start_vlm.sh (Qwen/Qwen3-VL-8B-Instruct)
MODEL_NAME = "Qwen/Qwen3-VL-8B-Instruct"
PROMPT_VERSION = "v2"  # v1(11/9): 큰 지도 5/20이 같은 줄 반복으로 잘림, 지도에서 이름·회사명 지어냄 → v2: Qwen 권장 샘플링 + 반복 제거 + 지도는 읽은 글자 위주
MAX_SIDE = 2048  # 긴 변 상한. Qwen3-VL은 32×32px당 토큰 1개 → 2048×1400이면 약 2,800토큰
MAX_SEND = 2_500_000  # 보낼 이미지 바이트 상한 (관문 MAX_BODY_VLM 4MB, base64로 4/3배)
MAX_TOKENS = 1536  # v1에서 2048까지 간 것은 전부 반복이었다
WORKERS = 4  # 동시에 보내는 요청 수. vLLM이 묶어서 처리한다
TIMEOUT = 300

SYSTEM = "당신은 항만 공공기관 웹사이트의 이미지를 검색용 글로 옮기는 작업자입니다."
INSTRUCTION = """이 이미지는 웹 페이지 「{title}」에 있습니다.{alt_line}

챗봇이 이 글만 보고 이용자 질문에 답할 수 있도록 이미지 내용을 글로 옮기세요.
규칙:
1. 이미지 안의 글자는 빠짐없이 원래 언어·표기 그대로 옮긴다. 숫자·단위·전화번호·날짜·금액은 특히 정확히 옮긴다.
2. 표는 한 행씩 "항목: 값" 형식으로 쓴다.
3. 절차·흐름도는 순서대로 번호를 붙여 쓴다.
4. 지도·도면은 이미지에 적힌 시설·구역 이름과 수치·범례·축척을 한 번씩만 목록으로 쓴다. 위치 관계는 이미지에서 분명히 보이는 것만 짧게 덧붙인다.
5. 읽을 수 없거나 확실하지 않은 글자는 [판독 불가]로 쓴다. 이미지에 없는 이름·숫자·회사명을 추측하거나 덧붙이지 않는다.
6. 같은 줄이나 같은 항목을 되풀이하지 않는다. 다 옮겼으면 바로 끝낸다.
7. 글자가 거의 없는 사진·장식·화면 캡처는 "정보 없음: "으로 시작해 무엇이 보이는지 한 줄로만 쓴다.
8. 설명 문장은 한국어로 쓴다. 머리말·맺음말 없이 내용만 쓴다."""


def load_env() -> tuple[str, str]:
    """16번과 같은 방식: 저장소 루트 .env.
    VLM_URL·VLM_API_KEY가 있으면 그쪽(AIPub H100 워크스페이스의 vLLM을 터널로 직접, infra/aipub_vlm/README.md),
    없으면 GPU_URL·GPU_API_KEY(기존 GPU 서버 관문)"""
    env = dict(line.split("=", 1) for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
               if "=" in line and not line.startswith("#"))
    env = {k.strip(): v.strip() for k, v in env.items()}
    url, key = (env.get("VLM_URL") or env.get("GPU_URL", "")).rstrip("/"), env.get("VLM_API_KEY") or env.get("GPU_API_KEY", "")
    if not url or not key:
        raise SystemExit(".env에 VLM_URL·VLM_API_KEY(또는 GPU_URL·GPU_API_KEY)가 없습니다")
    print("보낼 곳:", url)
    return url, key


def prepare(path: Path) -> tuple[bytes, str, dict]:
    """긴 변 MAX_SIDE 이하로 줄이고, MAX_SEND를 넘으면 JPEG 품질·크기를 낮춘다. (바이트, MIME, 기록용 정보)"""
    from PIL import Image

    with Image.open(path) as img:
        img.load()
        orig = img.size
        if img.mode in ("RGBA", "LA", "P"):  # 투명 배경은 흰색으로 (검은 배경에 검은 글자가 되지 않게)
            rgba = img.convert("RGBA")
            img = Image.new("RGB", rgba.size, "white")
            img.paste(rgba, mask=rgba.getchannel("A"))
        else:
            img = img.convert("RGB")
    scale = min(1.0, MAX_SIDE / max(img.size))
    for quality in (92, 85, 75, 75, 75):
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        out = io.BytesIO()
        img.resize(size, Image.LANCZOS).save(out, "JPEG", quality=quality) if size != img.size else img.save(out, "JPEG", quality=quality)
        data = out.getvalue()
        if len(data) <= MAX_SEND:
            return data, "image/jpeg", {"orig": list(orig), "size": list(size), "quality": quality, "bytes": len(data)}
        scale *= 0.8
    raise ValueError(f"{path.name}: 줄여도 {len(data)}바이트")


def build_messages(item: dict, image: bytes, mime: str) -> list[dict]:
    alt = item.get("alt", "").strip()
    alt_line = f"\n참고 — 페이지에 적힌 이미지 설명(틀리거나 부족할 수 있음): {alt[:300]}" if alt else ""
    url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}},
                                         {"type": "text", "text": INSTRUCTION.format(title=item.get("title", ""), alt_line=alt_line)}]}]


def ask(client, url: str, key: str, item: dict) -> dict:
    image, mime, sent = prepare(ROOT / item["file"])
    body = {"model": MODEL, "messages": build_messages(item, image, mime), "max_tokens": MAX_TOKENS,
            "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5, "seed": 0}
    # Qwen3-VL Instruct 권장 샘플링. v1의 temperature 0 + repetition_penalty 1.05는 큰 지도에서 같은 줄을 끝없이 반복했다
    start = time.perf_counter()
    r = client.post(f"{url}/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    data = r.json()
    choice = data["choices"][0]
    text, removed = dedupe((choice["message"]["content"] or "").strip())
    return {"text": text, "repeats_removed": removed, "model": MODEL_NAME, "prompt_version": PROMPT_VERSION,
            "doc_id": item["doc_id"], "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "seconds": round(time.perf_counter() - start, 2), "finish_reason": choice.get("finish_reason"),
            "tokens": data.get("usage", {}), "sent": sent}


def dedupe(text: str) -> tuple[str, int]:
    """같은 줄이 두 번 넘게 나오면 처음 것만 남긴다 (반복 고리 방어). 빈 줄·짧은 기호 줄은 그대로"""
    seen, out, removed = set(), [], 0
    for line in text.splitlines():
        key = line.strip()
        if len(key) > 3 and key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append(line)
    return "\n".join(out).strip(), removed


def targets(args) -> list[dict]:
    items = {x["sha256"]: x for x in json.loads(INVENTORY.read_text(encoding="utf-8"))}
    if args.sample:
        picked = []
        for s in json.loads(SAMPLE.read_text(encoding="utf-8"))["images"]:
            item = items[s["sha256"]]
            if not item["file"]:
                raise SystemExit(f"{s['sha256'][:10]}: 이미지 파일 없음")
            picked.append(item)  # 시험 목록은 vlm_target이 아니어도 넣는다 (사람 전사 대조용)
        return picked
    return [x for x in items.values() if x["vlm_target"]]


def run(args):
    todo = targets(args)
    drafts = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if not args.redo:
        todo = [x for x in todo if not (d := drafts.get(x["sha256"])) or (d["model"], d["prompt_version"]) != (MODEL_NAME, PROMPT_VERSION)]
    print(f"보낼 이미지 {len(todo)}개 (이미 있는 초안 {len(drafts)}개)")

    if args.dry_run:
        total = 0
        for x in todo:
            _, _, sent = prepare(ROOT / x["file"])
            total += sent["bytes"]
            print(f"  {x['sha256'][:10]} {x['doc_id']:<22} {sent['orig']} → {sent['size']} q{sent['quality']} {sent['bytes'] // 1024}KB")
        print(f"합계 {total / 1e6:.1f}MB (GPU에 보내지 않음)")
        return

    import httpx

    url, key = load_env()
    lock, done, failed = threading.Lock(), 0, []
    with httpx.Client() as client, ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(ask, client, url, key, x): x for x in todo}
        for f in as_completed(futures):
            x = futures[f]
            try:
                result = f.result()
            except Exception as e:  # 한 장 실패로 전체를 멈추지 않는다. 다시 실행하면 실패한 것만 보낸다
                failed.append(x["sha256"][:10])
                print(f"  실패 {x['sha256'][:10]} {x['doc_id']}: {e}")
                continue
            with lock:
                drafts[x["sha256"]] = result
                done += 1
                OUT.write_text(json.dumps(drafts, ensure_ascii=False, indent=1), encoding="utf-8")  # 한 장마다 저장
            cut = (" (길이 상한에서 잘림)" if result["finish_reason"] == "length" else "") + (f" 반복 {result['repeats_removed']}줄 제거" if result["repeats_removed"] else "")
            print(f"  [{done}/{len(todo)}] {x['sha256'][:10]} {x['doc_id']} {result['seconds']}초 {len(result['text'])}자{cut}")
    print(f"완료 {done}개, 실패 {len(failed)}개 {failed}", "\n저장:", OUT.relative_to(ROOT))


def report(args):
    """사람이 훑어볼 검토 파일. 이미지 링크는 저장소 루트 기준 상대 경로 (VS Code·옵시디언 미리보기에서 보임)"""
    drafts = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    ocr = json.loads(OCR_CACHE.read_text(encoding="utf-8")) if OCR_CACHE.exists() else {}
    manual = json.loads(TRANSCRIPTS.read_text(encoding="utf-8")) if TRANSCRIPTS.exists() else {}
    sample = {s["sha256"]: s for s in json.loads(SAMPLE.read_text(encoding="utf-8"))["images"]} if args.sample else {}
    items = targets(args)
    lines = [f"# VLM 초안 검토 ({MODEL_NAME}, 지시문 {PROMPT_VERSION})", "",
             "보는 법: 이미지 원본과 VLM 글을 대조해 숫자·이름이 맞는지, 이미지에 없는 내용을 지어냈는지 확인한다.", ""]
    for i, x in enumerate(items, 1):
        d = drafts.get(x["sha256"])
        why = sample.get(x["sha256"], {}).get("why", "")
        lines += [f"## {i}. {x['doc_id']} · {x['state']} · {x['width']}×{x['height']}", "",
                  f"- 페이지: {x['title']}", f"- sha256: `{x['sha256'][:16]}`" + (f" · 고른 이유: {why}" if why else ""), "",
                  f"![]({'../../' + x['file']})", ""]
        if x.get("alt"):
            lines += ["**alt**", "", "> " + x["alt"][:500], ""]
        if ocr.get(x["sha256"], "").strip():
            lines += ["**OCR (현재 색인 기준)**", "", "```", ocr[x["sha256"]].strip()[:1500], "```", ""]
        if x["sha256"] in manual:
            lines += ["**사람 전사 (정답 대조용)**", "", "```", manual[x["sha256"]].strip(), "```", ""]
        if d:
            meta = f"{d['seconds']}초, {d['tokens'].get('completion_tokens', '?')}토큰" + (", 잘림" if d["finish_reason"] == "length" else "") + (f", 반복 {d.get('repeats_removed')}줄 제거" if d.get("repeats_removed") else "")
            lines += [f"**VLM** ({meta})", "", "```", d["text"], "```", ""]
        else:
            lines += ["**VLM**: 아직 없음", ""]
        lines += ["- 판정: [ ] 맞음  [ ] 일부 틀림  [ ] 지어냄  [ ] 정보 없음이 맞음", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"검토 파일 {len(items)}개 항목 (초안 있음 {sum(x['sha256'] in drafts for x in items)}개) →", REPORT.relative_to(ROOT))


def classify(item: dict, draft: dict) -> tuple[str, str, str]:
    """(auto|review|none, 이유, 넣을 글)"""
    if draft["finish_reason"] == "length" or draft.get("repeats_removed", 0) >= 3:
        return "review", "반복·잘림", ""
    raw = draft["text"].strip()
    if DECOR.match(raw):
        return "none", "사진·장식", ""
    if MAP_WORDS.search(f"{item.get('title', '')} {item.get('alt', '')}") or raw.startswith("지도"):
        return "review", "지도·도면", ""
    text = "\n".join(line for line in raw.splitlines() if not DECOR.match(line))
    text = re.sub(r"\[정보 없음:[^\]]*\]", "", text).strip()
    if len(re.sub(r"\s", "", text)) < 20:
        return "none", "글 거의 없음", ""
    return "auto", "", text


def split(args):
    drafts = json.loads(OUT.read_text(encoding="utf-8"))
    items = {x["sha256"]: x for x in targets(args)}
    accepted, queue, counts = {}, [], {}
    for key, item in items.items():
        if not (d := drafts.get(key)) or (d["model"], d["prompt_version"]) != (MODEL_NAME, PROMPT_VERSION):
            counts["초안 없음"] = counts.get("초안 없음", 0) + 1
            continue
        kind, why, text = classify(item, d)
        counts[f"{kind}{'·' + why if why else ''}"] = counts.get(f"{kind}{'·' + why if why else ''}", 0) + 1
        if kind == "auto":
            accepted[key] = {"text": text, "model": d["model"], "prompt_version": d["prompt_version"], "doc_id": item["doc_id"]}
        elif kind == "review":
            queue.append([why, item["doc_id"], item["title"], f"{item['width']}x{item['height']}", item["file"], key, d["text"][:300].replace("\n", " / ")])
    ACCEPTED.write_text(json.dumps(accepted, ensure_ascii=False, indent=1), encoding="utf-8")
    with QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["이유", "doc_id", "제목", "크기", "파일", "sha256", "VLM 앞부분(지어낸 내용 있을 수 있음)"])
        w.writerows(sorted(queue))
    print("나누기:", dict(sorted(counts.items())))
    print("저장:", ACCEPTED.relative_to(ROOT), f"({len(accepted)}개),", QUEUE.relative_to(ROOT), f"({len(queue)}개)")


def main():
    ap = argparse.ArgumentParser()
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--sample", action="store_true", help="시험 이미지만 (data/catalog/vlm_sample_v1.json)")
    which.add_argument("--all", action="store_true", help="VLM 대상 전체")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--split", action="store_true", help="초안을 auto·review·none으로 나눈다 (GPU 불필요)")
    args = ap.parse_args()
    report(args) if args.report else split(args) if args.split else run(args)


if __name__ == "__main__":
    main()
