"""검색 후보 재정렬: 벡터 검색 후보 N개를 재정렬 모델(GPU 서버 bge-reranker-v2-m3)로 다시 채점해 순서를 정한다.

벡터 검색은 질문과 청크를 따로 벡터로 만들어 비교하므로 겉모습이 비슷한 글("출입증"과 "출입 신고서")을 잘 못 가린다.
재정렬 모델은 질문과 청크를 한 쌍으로 읽고 관련도를 매긴다.

순서: 후보 2N개(문서당 상한만, 법령 상한 없이) 중 앞 N개를 재정렬 → 재정렬 점수와 벡터 점수 반반 → 법령 상한 → 상위 k개.
앞 N개에 법령이 많아 상한 뒤 k개가 안 되면 나머지 후보로 벡터 순서대로 채운다.
2026-10-07 GPU 서버 실험(질문 185개, docs/handoff/28_rerank.md): 정답 1위 147 → 155 (좋아짐 10·나빠짐 3), 후보 10개·반반이 가장 좋았다.
확인 불가 판단은 여기서 하지 않는다 — 각 근거의 "score"는 그대로 벡터 유사도로 두고, 재정렬 점수는 "rerank"에 따로 둔다.
재정렬이 꺼져 있거나 실패하면 벡터 순서 그대로 (답변은 계속된다).

기본은 끔: 재정렬만 켜면 확인 불가여야 할 질문(u02·u04)이 6/6 → 2/6으로 흔들린다 (docs/handoff/28_rerank.md).
답변 전 판정(app/gate.py, RAG_GATE)과 함께 켜면 이 문제가 없다 — 켤 때는 둘 다 (docs/handoff/31_answer_gate.md).

환경변수: RAG_RERANK(on/off, 기본 off), RAG_RERANK_N(후보 수, 기본 10), RAG_RERANK_TRUNCATE(토큰 상한, 기본 1024)
"""
import logging
import os

from app import gpu, search

N = 10
WEIGHT = 0.5  # 재정렬 점수 비중 (나머지는 벡터 점수)
TIMEOUT = 5.0  # 초. 넘으면 벡터 순서로
TRUNCATE = 1024  # 질문+청크 토큰 상한. 512는 긴 조문 끝의 정답 문장을 못 봄 (h12, docs/handoff/31_answer_gate.md)

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv("RAG_RERANK", "off").lower() in ("on", "1", "true")


def candidates() -> int:
    return int(os.getenv("RAG_RERANK_N", N))


def select(hits: list[dict], k: int, key) -> list[dict]:
    """key가 큰 순서로 법령 조문·법령 서식 상한을 지키며 k개 (search.SQL과 같은 규칙)"""
    out, used, cap = [], {"law": 0, "form": 0}, {"law": search.law_cap(), "form": search.form_cap()}
    for h in sorted(hits, key=lambda h: -key(h)):
        kind = search.kind(h["chunk"])
        if kind in cap:
            if used[kind] >= cap[kind]:
                continue
            used[kind] += 1
        out.append(h)
        if len(out) == k:
            break
    return out


def by_vector(hits: list[dict], k: int) -> list[dict]:
    """재정렬 없이 고른 근거 (확인 불가 판단·재정렬 실패 때)"""
    return select(hits, k, lambda h: h["score"])


async def rerank(query: str, pool: list[dict], k: int) -> list[dict]:
    """pool: 벡터 순서 후보(법령 상한 없이). 앞 candidates()개만 재정렬하고, 나머지는 모자랄 때 채우는 데만 쓴다"""
    head, rest = pool[:candidates()], pool[candidates():]
    try:
        scores = await gpu.rerank(query, [h["chunk"]["text"] for h in head], TIMEOUT, int(os.getenv("RAG_RERANK_TRUNCATE", TRUNCATE)))
    except Exception as e:  # 재정렬이 안 되면 지금까지처럼 벡터 순서로
        logger.warning("재정렬 실패, 벡터 순서 사용: %s: %s", type(e).__name__, e)
        return by_vector(pool, k)
    scored = [h | {"rerank": s} for h, s in zip(head, scores)]
    # 재정렬한 후보(0~1 점수)가 먼저, 나머지는 그 뒤에 벡터 순서로 (-1을 더해 항상 뒤에 오게)
    return select(scored + rest, k, lambda h: WEIGHT * h["rerank"] + (1 - WEIGHT) * h["score"] if "rerank" in h else h["score"] - 1)
