"""답변 전 판정: 검색한 근거가 질문의 주제를 다루는가 (있음/없음).

벡터 점수 기준(UNKNOWN_THRESHOLD)을 넘어도 근거에 답이 없는 질문이 있다. 이때 생성 LLM은 비슷해 보이는 근거를 붙잡고
답하거나 엉뚱하게 되묻는다 (u04 "해상 운임" → "어느 시설의 사용료?", h25). 재정렬·근거 6개가 1위 정답을 늘리고도
기각된 이유가 이것이다 (docs/handoff/28_rerank.md, 29_r02_retrieval.md).
그래서 LLM에 "있음/없음"만 따로 묻고, 없음이면 확인 불가로 보낸다.

시간: 판정도 생성도 시간 대부분이 긴 근거를 읽는 데 쓰인다(각 약 1.3초). 같은 GPU에서 차례로 하면 첫 글자가 그만큼 늦고,
동시에 해도 계산을 나눠 써 이득이 없다. 그래서 판정은 다른 GPU(0번)의 판정 모델(gate-llm, Qwen3-14B)로 생성과 동시에 시작하고,
판정이 나올 때까지 생성 조각은 화면에 보내지 않고 모아 둔다 (hold). 없음이면 생성을 멈추고 버린다.
기각 (docs/handoff/31_answer_gate.md): 근거를 청크당 400~1200자로 잘라 넘기기 — 빠르지만 답이 뒤쪽에 있는 질문을 막음(f05·l06·r01).
판정 요청을 생성 요청과 앞부분이 같게 만들어 vLLM 계산 재사용 — 답변 지시문이 앞에 있으면 판정이 '있음'으로 기울어 u04·h22를 놓침.
판정이 실패하거나 TIMEOUT을 넘기면 판정 없이 답한다 (판정 때문에 답이 막히지 않게).

환경변수: RAG_GATE(on/off, 기본 off), RAG_GATE_MODEL(기본 gate-llm), RAG_GATE_CHARS(실험용: 청크당 글자 수, 기본 답변과 같음)
"""
import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable

from app import gpu
from app.prompt import effective_question, evidence

TIMEOUT = 8.0  # 초
MODEL = os.getenv("RAG_GATE_MODEL", "gate-llm")  # GPU 0번의 판정 모델 (infra/gpu_server/start_gate.sh). 답변 모델로 판정하려면 qwen3-32b
MAX_TOKENS = 12  # 모델이 "판정: **있음**"처럼 앞말을 붙이는 경우가 있어 여유를 둔다
CHARS = int(os.getenv("RAG_GATE_CHARS", 0)) or None  # 판정에 넘기는 청크당 글자 수 (None: 답변과 같음)
NO = "없음"

SYSTEM = """당신은 검색된 [근거]가 사용자 [질문]의 주제를 다루는지 판정합니다. 질문에 답하지 말고 판정만 하세요.
- 있음: 근거 중 하나라도 질문이 묻는 대상·제도·절차·시설에 대한 정보를 담고 있다. 일부만 있어도, 질문이 모호해서 되물어야 해도, 근거의 기한이 지났거나 답이 "안 된다"여도 있음.
- 없음: 근거가 질문의 대상을 다루지 않고 비슷한 낱말만 겹친다. 예: 다른 항만(부산항 등)에 관한 질문, 근거에 없는 제도·요금·수치·날씨를 묻는 질문.
반드시 "있음" 또는 "없음" 한 단어로만 답하세요."""

logger = logging.getLogger(__name__)


class Blocked(Exception):
    """판정이 없음: 생성한 답을 버리고 확인 불가로 보낸다"""


def enabled() -> bool:
    return os.getenv("RAG_GATE", "off").lower() in ("on", "1", "true")


def build(messages, hits: list[dict], follow_up: bool = False) -> list[dict]:
    asked = effective_question(messages, follow_up)
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"[근거]\n{evidence(hits, CHARS)}\n\n[질문]\n{asked}\n\n판정(있음/없음):"}]


async def answerable(messages, hits: list[dict], follow_up: bool = False) -> bool:
    """근거가 질문의 주제를 다루면 True. 판정 실패·시간 초과도 True (지금처럼 생성 LLM이 판단)"""
    async def ask() -> str:
        return "".join([p async for p in gpu.chat_stream(build(messages, hits, follow_up), MAX_TOKENS, 0.0, MODEL)])
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


async def hold(stream: AsyncIterator[str], judge: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
    """판정(judge)과 생성을 함께 시작하고, 판정이 나올 때까지 생성 조각을 모아 둔다.
    있음이면 모은 것부터 내보낸다. 없음이면 생성을 멈추고 Blocked"""
    it = aiter(stream)
    verdict = asyncio.ensure_future(judge())
    held, pending, ended = [], None, False
    try:
        while not verdict.done() and not ended:
            pending = pending or asyncio.ensure_future(anext(it))
            await asyncio.wait({pending, verdict}, return_when=asyncio.FIRST_COMPLETED)
            if pending.done():
                try:
                    held.append(pending.result())
                except StopAsyncIteration:
                    ended = True
                pending = None
        if not await verdict:
            raise Blocked
        for piece in held:
            yield piece
        if pending is not None:
            try:
                yield await pending
            except StopAsyncIteration:
                ended = True
            pending = None
        if not ended:
            async for piece in it:
                yield piece
    finally:
        if pending is not None:  # 받던 조각을 취소하고 끝날 때까지 기다려야 생성 스트림을 닫을 수 있다
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        verdict.cancel()
        if hasattr(it, "aclose"):
            await it.aclose()
