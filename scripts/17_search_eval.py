"""개발용 검색 기준선: 문서 목록(CSV)의 예상 질문(sample_question)으로 정답 문서가 상위 k개에 나오는지 잰다.
FAQ·최종평가 자료는 쓰지 않는다. 예상 질문은 문서를 보고 쓴 것이라 실제 사용자 질문보다 쉬울 수 있다.

실행: .\\.venv\\Scripts\\python.exe -B .\\scripts\\17_search_eval.py [--index data/index/<버전>]
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag import dense  # noqa: E402

load_model = __import__("16_build_index").load_model


def latest_index():
    folders = sorted((ROOT / "data/index").glob("*/manifest.json"), key=lambda p: p.stat().st_mtime)
    if not folders:
        sys.exit("색인이 없습니다. 먼저 16_build_index.py를 실행하세요.")
    return folders[-1].parent


def evaluate(questions, embed, vectors, chunks, k=5):
    """문서 단위 적중: 정답 doc_id의 청크가 처음 나온 순위로 hit@1·3·5와 MRR을 계산"""
    rows = []
    for q in questions:
        hits = dense.search(embed(q["question"]), vectors, chunks, k=k)
        docs = [h["chunk"]["doc_id"] for h in hits]
        rank = docs.index(q["doc_id"]) + 1 if q["doc_id"] in docs else None
        rows.append({**q, "rank": rank, "top": [(h["chunk"]["doc_id"], round(h["score"], 3)) for h in hits]})
    n = len(rows)
    summary = {f"hit@{t}": round(sum(1 for r in rows if r["rank"] and r["rank"] <= t) / n, 3) for t in (1, 3, k)}
    summary["mrr@5"] = round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3)
    return summary, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path)
    args = ap.parse_args()

    folder = args.index or latest_index()
    vectors, chunks, manifest = dense.load(folder)
    indexed_docs = {c["doc_id"] for c in chunks}
    catalog = csv.DictReader((ROOT / "data/catalog/ygpa_document_candidates.csv").open(encoding="utf-8-sig"))
    questions = [{"doc_id": r["doc_id"], "question": r["sample_question"]}
                 for r in catalog if r["sample_question"] and r["doc_id"] in indexed_docs]

    model, revision = load_model(manifest["model_revision"])  # 색인과 같은 모델 revision
    if revision != manifest["model_revision"]:
        sys.exit(f"모델 revision 불일치: 색인 {manifest['model_revision']} / 현재 {revision}")
    summary, rows = evaluate(questions, lambda q: model.encode(q), vectors, chunks)

    for r in rows:
        mark = f"{r['rank']}위" if r["rank"] else "놓침"
        print(f"{r['doc_id']} {mark:>4} | {r['question'][:38]:<38} | 상위: {', '.join(d for d, _ in r['top'][:3])}")
    print(f"\n질문 {len(rows)}개 | " + " | ".join(f"{k} {v}" for k, v in summary.items()))
    report = {"index_version": manifest["index_version"], "evaluated_at": datetime.now(timezone.utc).isoformat(),
              "question_source": "data/catalog/ygpa_document_candidates.csv sample_question", "summary": summary, "rows": rows}
    (folder / "eval_catalog_questions.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
