"""답변 전 판정: 검색한 근거가 질문의 주제를 다루는가 (있음/없음).

벡터 점수 기준(UNKNOWN_THRESHOLD)을 넘어도 근거에 답이 없는 질문이 있다. 이때 생성 LLM은 비슷해 보이는 근거를 붙잡고
답하거나 엉뚱하게 되묻는다 (u04 "해상 운임" → "어느 시설의 사용료?", h25). 재정렬·근거 6개가 1위 정답을 늘리고도
기각된 이유가 이것이다 (docs/handoff/28_rerank.md, 29_r02_retrieval.md).
그래서 답을 만들기 전에 같은 Qwen에 "있음/없음"만 따로 묻고, 없음이면 확인 불가로 보낸다.
판정이 실패하거나 TIMEOUT을 넘기면 판정 없이 답한다 (판정 때문에 답이 막히지 않게).

환경변수: RAG_GATE(on/off, 기본 off)
"""
import asyncio
import logging
import os

from app import gpu
from app.prompt import effective_question, evidence

TIMEOUT = 8.0  # 초
MAX_TOKENS = 12  # 모델이 "판정: **있음**"처럼 앞말을 붙이는 경우가 있어 여유를 둔다
NO = "없음"

SYSTEM = """당신은 검색된 [근거]가 사용자 [질문]의 주제를 다루는지 판정합니다. 질문에 답하지 말고 판정만 하세요.
- 있음: 근거 중 하나라도 질문이 묻는 대상·제도·절차·시설에 대한 정보를 담고 있다. 일부만 있어도, 질문이 모호해서 되물어야 해도, 근거의 기한이 지났거나 답이 "안 된다"여도 있음.
- 없음: 근거가 질문의 대상을 다루지 않고 비슷한 낱말만 겹친다. 예: 다른 항만(부산항 등)에 관한 질문, 근거에 없는 제도·요금·수치·날씨를 묻는 질문.
반드시 "있음" 또는 "없음" 한 단어로만 답하세요."""

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv("RAG_GATE", "off").lower() in ("on", "1", "true")


def build(messages, hits: list[dict], follow_up: bool = False) -> list[dict]:
    asked = effective_question(messages, follow_up)
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"[근거]\n{evidence(hits)}\n\n[질문]\n{asked}\n\n판정(있음/없음):"}]


async def answerable(messages, hits: list[dict], follow_up: bool = False) -> bool:
    """근거가 질문의 주제를 다루면 True. 판정 실패·시간 초과도 True (지금처럼 생성 LLM이 판단)"""
    async def ask() -> str:
        return "".join([p async for p in gpu.chat_stream(build(messages, hits, follow_up), MAX_TOKENS, 0.0)])
    try:
        verdict = await asyncio.wait_for(ask(), TIMEOUT)
    except Exception as e:
        logger.warning("답변 전 판정 실패, 판정 없이 답함: %s: %s", type(e).__name__, e)
        return True
    if NO in verdict:
        logger.info("답변 전 판정: 근거 없음 → 확인 불가")
        return False
    if "있음" not in verdict:
        logger.warning("답변 전 판정이 있음/없음이 아님, 판정 없이 답함: %r", verdict)
    return True
