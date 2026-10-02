"""실제 RAG 조립 (RAG_MODE=real): 질문 임베딩 → Neon 검색 → Qwen 생성 → 근거·버튼 정리.

1위 점수가 UNKNOWN_THRESHOLD보다 낮으면 LLM을 부르지 않고 unknown (scripts/19_unknown_threshold.py로 측정한 값).
근거 번호 [n] = sources 순서. URL은 청크 메타데이터와 app/actions.py에서만 채운다.
"""
import asyncio
import logging
import os
import re

from pydantic import ValidationError

from app import gpu, search
from app.actions import ACTIONS
from app.prompt import MetaFilter, RuleLineFilter, build_messages, parse_meta, violations
from app.rag import Answer
from app.schemas import Action, Option
from app.sources import chunk_to_source, form_download

K = 5
# 2026-10-02 측정: 관련 질문 1위 최소 0.594, 무관 질문 최대 0.455, 주변 주제(자료 없음) 0.42~0.52.
# 실제 사용자 표현은 예상 질문보다 점수가 낮을 수 있어 무관 쪽에 가깝게 잡는다. 주변 주제는 LLM이 unknown으로 판단
DEFAULT_THRESHOLD = 0.48
SHORT_QUESTION = 15  # 이보다 짧은 질문(예: 되묻기에 고른 선택지)은 앞 질문을 붙여 검색한다
MAX_TOKENS = 1024
TEMPERATURE = 0.3
UNKNOWN_TEXT = "확인한 공식 자료만으로는 답을 확정하기 어렵습니다. 질문을 조금 더 구체적으로 써 주시거나 담당 부서에 문의해 주세요."

logger = logging.getLogger(__name__)


def search_query(messages) -> str:
    last = messages[-1].content.strip()
    previous = [m.content for m in messages[:-1] if m.role == "user"]
    return f"{previous[-1]}\n{last}" if len(last) < SHORT_QUESTION and previous else last


def build_actions(kind: str, hits: list[dict], keys: list[str], text: str) -> list[Action]:
    """답변일 때만: 본문에 인용된 서식 청크의 다운로드 버튼 + LLM이 고른 고정 링크"""
    if kind != "answer":
        return []
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    actions = []
    for i, h in enumerate(hits, 1):
        if i in cited:
            try:
                if a := form_download(h["chunk"], source_ref=i):
                    actions.append(a)
            except ValidationError:  # https가 아닌 원문 주소 등은 버튼을 만들지 않는다
                logger.warning("서식 버튼 생략: %s", h["chunk"]["chunk_id"])
    # 고정 링크는 근거에 그 서비스가 실제로 나올 때만 (LLM이 관련 없는 질문에 고르는 것을 막는다)
    evidence = " ".join(h["chunk"]["text"] for h in hits).lower()
    return actions + [ACTIONS[k][0] for k in dict.fromkeys(keys) if ACTIONS[k][2] in evidence]


def answer(messages) -> Answer:
    result = Answer(sources=[], tokens=None)
    threshold = float(os.getenv("UNKNOWN_THRESHOLD", DEFAULT_THRESHOLD))

    async def tokens():
        vector = await gpu.embed(search_query(messages))
        hits = await asyncio.to_thread(search.search, vector, K)
        if not hits or hits[0]["score"] < threshold:
            result.answer_type = "unknown"
            yield UNKNOWN_TEXT
            return

        result.sources = [chunk_to_source(h["chunk"]) for h in hits]
        meta, rules, parts = MetaFilter(), RuleLineFilter(), []
        async for piece in gpu.chat_stream(build_messages(messages, hits), MAX_TOKENS, TEMPERATURE):
            if out := rules.feed(meta.feed(piece)):
                parts.append(out)
                yield out
        if out := rules.feed(meta.flush()) + rules.flush():
            parts.append(out)
            yield out

        text = "".join(parts)
        kind, options, keys = parse_meta(meta.meta)
        result.answer_type = kind
        if kind == "unknown":
            result.sources = []  # 답하지 못했으면 관련 없는 근거를 보여주지 않는다
        result.options = [Option(label=o) for o in options]
        result.actions = build_actions(kind, hits, keys, text)
        if found := violations(text, len(hits)):
            logger.warning("답변 규칙 위반 %s (1위 %s)", found, hits[0]["chunk"]["chunk_id"])

    result.tokens = tokens()
    return result
