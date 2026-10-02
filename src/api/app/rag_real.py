"""실제 RAG 조립 (RAG_MODE=real): 질문 임베딩 → Neon 검색 → Qwen 생성 → 근거·버튼 정리.

1위 점수가 UNKNOWN_THRESHOLD보다 낮으면 LLM을 부르지 않고 unknown (scripts/19_unknown_threshold.py로 측정한 값).
근거 번호 [n] = sources 순서. URL은 청크 메타데이터와 app/actions.py에서만 채운다.
"""
import asyncio
import logging
import os
import re

from pydantic import ValidationError

from app import contacts, gpu, search
from app.actions import ACTIONS
from app.prompt import (SHORT_QUESTION, UNKNOWN_PHRASE, CitationFilter, ContactFilter, Meta, MetaFilter, RuleLineFilter,
                        build_messages, parse_meta, violations)
from app.rag import Answer
from app.schemas import Action, Option
from app.sources import chunk_to_source, form_download

K = 5
# 2026-10-02 측정: 관련 질문 1위 최소 0.594, 무관 질문 최대 0.455, 주변 주제(자료 없음) 0.42~0.52.
# 실제 사용자 표현은 예상 질문보다 점수가 낮을 수 있어 무관 쪽에 가깝게 잡는다. 주변 주제는 LLM이 unknown으로 판단
DEFAULT_THRESHOLD = 0.48
MAX_TOKENS = 1024
TEMPERATURE = 0.1  # 2026-10-02 dev 측정: 0.3과 지표 같음, 반복 실행 때 답이 더 일정
UNKNOWN_TEXT = "확인한 공식 자료만으로는 답을 확정하기 어렵습니다. 질문을 조금 더 구체적으로 써 주시거나, 아래 대표전화로 문의해 주세요."

logger = logging.getLogger(__name__)


TERM = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,}")  # 영문 용어·약어 (Port-MIS, DWT, TEU)


def term_match(query: str, hits: list[dict]) -> bool:
    """질문의 영문 용어가 근거에 글자 그대로 있는가. 의미 검색은 "Port-MIS가 뭐예요?"처럼 약어 하나뿐인 짧은 질문의
    점수를 낮게 매겨(0.41) 확인 불가로 끝내 버린다 → 이런 경우는 LLM이 근거를 보고 판단하게 한다"""
    evidence = " ".join(h["chunk"]["text"] + " " + h["chunk"]["title"] for h in hits).lower()
    return any(t.lower() in evidence for t in TERM.findall(query))


ASKS_DATE = re.compile(r"언제|날짜|며칠|몇\s*월|몇\s*년")
HAS_DATE = re.compile(r"\d|[월화수목금토일]요일|매주|매월|매년|평일|주말|공휴일")
DATE_NOTE = "\n\n질문하신 날짜·시기는 확인한 공식 자료에 없습니다. 아래 대표전화로 확인해 주세요."


def missing_date(question: str, text: str) -> bool:
    """날짜·시기를 물었는데 답에 날짜·요일·숫자가 하나도 없는가"""
    body = re.sub(r"\[\d+\]|^\s*\d+\.\s", "", text, flags=re.M)  # 근거 번호·목록 번호의 숫자는 날짜가 아니다
    return bool(ASKS_DATE.search(question)) and not HAS_DATE.search(body)


def search_query(messages) -> str:
    """검색용 질문: 되묻기에 대한 짧은 답이면 앞 질문을 붙인다 (LLM에는 prompt.effective_question으로 같은 내용을 보낸다)"""
    last = messages[-1].content.strip()
    previous = [m.content for m in messages[:-1] if m.role == "user"]
    return f"{previous[-1]}\n{last}" if len(last) < SHORT_QUESTION and previous else last


def build_actions(meta: Meta, hits: list[dict], text: str) -> list[Action]:
    """확인 불가: 대표전화. 되묻기: 없음.
    답변: LLM이 '작성·제출할 서식'으로 고르고 본문에도 인용한 서식 청크의 다운로드 버튼 + 고정 링크 + 인용한 문서의 담당 연락처.
    인용만으로는 서식 버튼을 만들지 않는다 (일반 설명에 서식 근거가 섞여도 버튼이 붙던 문제).
    URL은 청크 메타데이터, 전화번호는 contacts.json에서만"""
    if meta.kind == "unknown":
        return [contacts.MAIN]
    if meta.kind != "answer":
        return []
    order = [int(n) for n in re.findall(r"\[(\d+)\]", text)]
    cited = set(order)
    actions = []
    for i, h in enumerate(hits, 1):
        if i in cited and i in meta.forms:
            try:
                if a := form_download(h["chunk"], source_ref=i):
                    actions.append(a)
            except ValidationError:  # https가 아닌 원문 주소 등은 버튼을 만들지 않는다
                logger.warning("서식 버튼 생략: %s", h["chunk"]["chunk_id"])
    # 고정 링크는 근거에 그 서비스가 실제로 나올 때만 (LLM이 관련 없는 질문에 고르는 것을 막는다)
    evidence = " ".join(h["chunk"]["text"] for h in hits).lower()
    links = [ACTIONS[k][0] for k in dict.fromkeys(meta.keys) if ACTIONS[k][2] in evidence]
    cited_docs = [hits[i - 1]["chunk"]["doc_id"] for i in dict.fromkeys(order) if 1 <= i <= len(hits)]
    return actions + links + contacts.for_docs(cited_docs)


def answer(messages) -> Answer:
    result = Answer(sources=[], tokens=None)
    threshold = float(os.getenv("UNKNOWN_THRESHOLD", DEFAULT_THRESHOLD))

    async def tokens():
        vector = await gpu.embed(search_query(messages))
        hits = await asyncio.to_thread(search.search, vector, int(os.getenv("RAG_K", K)))
        if not hits or (hits[0]["score"] < threshold and not term_match(search_query(messages), hits)):
            result.answer_type = "unknown"
            result.actions = [contacts.MAIN]
            yield UNKNOWN_TEXT
            return

        result.sources = [chunk_to_source(h["chunk"]) for h in hits]
        # 화면으로 나가기 전 거르기: 정리 줄(@@META) → 구분선 → 없는 근거 번호 → 근거에 없는 연락처
        meta, rules, cites, parts = MetaFilter(), RuleLineFilter(), CitationFilter(len(hits)), []
        guard = ContactFilter("\n".join(h["chunk"]["text"] for h in hits))
        temperature = float(os.getenv("RAG_TEMPERATURE", TEMPERATURE))
        async for piece in gpu.chat_stream(build_messages(messages, hits), MAX_TOKENS, temperature):
            piece = piece.replace("。", ".")  # Qwen이 가끔 쓰는 중국식 마침표
            if out := guard.feed(cites.feed(rules.feed(meta.feed(piece)))):
                parts.append(out)
                yield out
        if out := guard.feed(cites.feed(rules.feed(meta.flush()) + rules.flush()) + cites.flush()) + guard.flush():
            parts.append(out)
            yield out
        if guard.masked:
            logger.warning("근거에 없는 연락처를 가림: %d개", len(guard.masked))

        text = "".join(parts)
        parsed = parse_meta(meta.meta)
        if UNKNOWN_PHRASE in text and parsed.kind == "answer":  # 정리 줄을 잘못 적은 확인 불가 답변
            parsed = Meta("unknown")
        result.answer_type = parsed.kind
        if parsed.kind == "unknown":
            result.sources = []  # 답하지 못했으면 관련 없는 근거를 보여주지 않는다
        result.options = [Option(label=o) for o in parsed.options]
        result.actions = build_actions(parsed, hits, text)
        if parsed.kind == "answer" and missing_date(search_query(messages), text):
            yield DATE_NOTE  # 묻는 날짜는 없이 다른 내용(예: 절차)만 답한 경우. 지시문으로 고치면 다른 답이 흔들려 코드로 처리
            parts.append(DATE_NOTE)
            result.actions = [*result.actions, contacts.MAIN]
        if found := violations(text, len(hits)):
            logger.warning("답변 규칙 위반 %s (1위 %s)", found, hits[0]["chunk"]["chunk_id"])

    result.tokens = tokens()
    return result
