"""'확인 불가(unknown)' 조기 판단 기준 측정: 검색 1위 점수가 기준보다 낮으면 LLM을 부르지 않는다.

관련 질문(문서 목록의 예상 질문)과 무관한 질문의 1위 점수 분포를 비교한다. FAQ·최종평가 자료는 쓰지 않는다.
실행: .\\.venv\\Scripts\\python.exe -B .\\scripts\\19_unknown_threshold.py [--index data/index/<버전>]
"""
import argparse
import csv
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from rag import dense  # noqa: E402

load_model = __import__("16_build_index").load_model
latest_index = __import__("17_search_eval").latest_index

# 명백히 무관: 조기 판단으로 걸러야 하는 질문
OFF_TOPIC = [
    "오늘 서울 날씨 어때?", "김치찌개 맛있게 끓이는 법 알려줘", "파이썬에서 리스트 정렬하는 방법",
    "비트코인 가격 전망은?", "요즘 볼만한 영화 추천해줘", "다이어트 식단 짜줘", "아이폰 배터리 교체 비용",
    "영어 회화 공부 방법", "점심 메뉴 골라줘", "안녕하세요", "너는 누구야?", "로또 번호 추천해줘",
]
# 항만·해운 주제지만 수집 자료에 없는 질문: 참고용 (조기 판단에서 못 거르면 LLM이 unknown으로 판단해야 함)
NEAR_DOMAIN = [
    "부산항 신항 컨테이너 터미널 운영사는 어디야?", "해양수산부 장관이 누구야?", "최근 SCFI 운임지수 알려줘",
    "선원 취업 비자는 어떻게 받나요?", "인천항 크루즈 터미널 위치", "컨테이너선 한 척 가격은 얼마야?",
    "여수 맛집 추천해줘", "항만공사 신입사원 연봉은 얼마인가요?",
]


def top_scores(questions, encode, vectors, chunks):
    return [dense.search(encode(q), vectors, chunks, k=1)[0]["score"] for q in questions]


def describe(name, scores):
    return f"{name:<14} {len(scores):>3}개 | 최소 {min(scores):.3f} · 중앙 {statistics.median(scores):.3f} · 최대 {max(scores):.3f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path)
    args = ap.parse_args()

    folder = args.index or latest_index()
    vectors, chunks, manifest = dense.load(folder)
    indexed_docs = {c["doc_id"] for c in chunks}
    catalog = csv.DictReader((ROOT / "data/catalog/ygpa_document_candidates.csv").open(encoding="utf-8-sig"))
    related = [r["sample_question"] for r in catalog if r["sample_question"] and r["doc_id"] in indexed_docs]

    model, revision = load_model(manifest["model_revision"])
    if revision != manifest["model_revision"]:
        sys.exit(f"모델 revision 불일치: 색인 {manifest['model_revision']} / 현재 {revision}")
    encode = lambda q: model.encode(q)  # noqa: E731

    groups = {"관련(예상 질문)": related, "무관": OFF_TOPIC, "주변 주제": NEAR_DOMAIN}
    scores = {name: top_scores(qs, encode, vectors, chunks) for name, qs in groups.items()}
    for name, s in scores.items():
        print(describe(name, s))

    low_related, high_off = min(scores["관련(예상 질문)"]), max(scores["무관"])
    print(f"\n관련 최소 {low_related:.3f} vs 무관 최대 {high_off:.3f} → "
          + (f"분리됨, 가운데 {(low_related + high_off) / 2:.3f}" if low_related > high_off else "겹침"))
    for name in ("무관", "주변 주제"):
        for q, s in sorted(zip(groups[name], scores[name]), key=lambda x: -x[1]):
            print(f"  [{name}] {s:.3f} {q}")
    report = {"index_version": manifest["index_version"],
              "groups": {n: [{"question": q, "top1": s} for q, s in zip(groups[n], scores[n])] for n in groups}}
    (folder / "unknown_threshold.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
