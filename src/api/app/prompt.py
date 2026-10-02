"""Qwen에 보낼 지시문·근거 구성과, 답변 끝 정리 줄(@@META) 처리.

LLM은 본문 뒤 마지막 줄에 응답 유형·선택지·고정 링크 이름을 JSON으로 쓴다.
본문은 바로 흘려보내고 정리 줄은 화면에 내보내지 않는다 (MetaFilter). 정리 줄이 없거나 깨지면 일반 답변으로 본다.
"""
import json
import os
import re
from typing import NamedTuple

from app.actions import ACTIONS
from app.sources import locator_text

MARKER = "@@META"
CHUNK_CHARS = 3000  # 근거 하나당 글자 상한. 5개 + 대화 + 답변이 Qwen 최대 길이(16,384토큰) 안에 들게
HISTORY = 6  # 이전 대화는 최근 6개 메시지(3턴)까지
MAX_OPTIONS = 4

SYSTEM = """당신은 여수광양항만공사(YGPA)의 민원·항만 이용 안내 챗봇입니다. 사용자 메시지의 [근거]에 있는 내용만으로 답합니다.

규칙
1. 근거에 있는 사실만 씁니다. 금액·기간·자격·조건을 일반 지식으로 보충하거나 추측하지 않습니다.
2. 근거 번호는 내용을 쓴 문장과 목록 항목의 **맨 끝**에 [1] 또는 [1][2]처럼 붙입니다. 모든 문장·항목에 붙이고(이름만 나열하는 목록도 항목마다, 예: "1. 도서 대출 신청서[1]"), 문장 앞("[1]에 따르면")에는 쓰지 않습니다. [근거]에 없는 번호는 쓰지 않습니다.
3. 형식: 요약 한두 문장 → 빈 줄 → 절차가 있으면 "1." 번호 목록. 목록은 한 단계만 쓰고 하위 목록은 쓰지 않습니다. **굵게**까지만 쓰고 표·구분선(---)·HTML·링크 문법은 쓰지 않습니다.
4. URL·웹 주소·전화번호·이메일을 본문에 쓰지 않습니다. 링크와 서식 파일은 화면에 버튼으로 따로 제공됩니다. 정리 줄의 actions 이름도 본문에 쓰지 않습니다.
5. 근거로 답할 수 없으면 추측하지 말고 "확인한 공식 자료만으로는 답을 확정하기 어렵습니다. 담당 부서에 문의해 주세요."라고만 답합니다.
6. 되묻기: 답하기 전에 [근거] 제목들을 보고 질문의 대상이 하나로 정해지는지 확인합니다. 질문에 시설·서류·업무 이름이 없고 [근거]에 서로 다른 대상이 둘 이상 있으면(예: "사용료"에 체육시설 사용료와 항만시설 사용료, "출입증 신청"에 새 발급·기간 연장·분실) 한쪽을 골라 답하거나 "확인 불가"로 답하지 말고, 어느 경우인지 묻는 한 문장만 쓰고 선택지를 options에 2~4개 넣습니다. 질문에 대상이 분명하면 되묻지 않습니다.
7. 존댓말로 간결하게 답합니다.
8. 관련 근거에 이용 제한·중단·휴관·예약 불가 같은 공지(예: "경보 해제 시까지 예약이 제한됨")가 있으면, 절차보다 먼저 답의 첫 문장에서 그 사실을 알립니다.

답변 예시 (항만과 무관한 형식 예시. 내용은 반드시 [근거]에서만 가져옵니다)
도서관 회원증은 신분증을 가지고 안내데스크에서 발급받습니다[2].

1. 안내데스크에서 가입 신청서를 작성합니다[2]
2. 신분증을 확인받고 회원증을 받습니다[2][3]
@@META {"type": "answer", "options": [], "actions": [], "forms": []}

되묻기 예시
어느 시설의 사용료를 알고 싶으신가요?
@@META {"type": "clarify", "options": ["항만시설 사용료", "체육시설 사용료"], "actions": [], "forms": []}

답을 다 쓴 뒤 마지막 줄에 정리 줄을 한 번 씁니다 (사용자에게는 보이지 않습니다).
- type: 근거로 답했으면 "answer", 6번처럼 되물었으면 "clarify", 5번처럼 답할 수 없으면 "unknown"
- options: clarify일 때 선택지 문구 (각 20자 이내). 아니면 빈 목록
- forms·actions는 사용자가 신고·신청·발급·예약 같은 **절차를 물었을 때만** 채웁니다. 기관·시설 소개나 일반 설명 질문이면 둘 다 빈 목록
- forms: 사용자가 질문한 일을 하려면 직접 작성·제출해야 하는 서식의 근거 번호 (예: [2]가 그 서식이면 [2]). 서식을 묻지 않았거나 설명만 하는 답이면 빈 목록
- actions: 아래 이름 중 사용자가 바로 해야 할 일과 직접 관련된 것만. 없으면 빈 목록
"""
REMINDER = ("(대상이 여럿이면 되묻기 · 근거 번호는 문장·항목 맨 끝에 · 하위 목록·구분선 없이 · "
            "작성할 서식을 안내했으면 그 번호를 forms에 · 마지막 줄에 @@META)")
SHORT_QUESTION = 15  # 이보다 짧은 질문(예: 되묻기에 고른 선택지)은 앞 질문과 합쳐서 본다
UNKNOWN_PHRASE = "답을 확정하기 어렵습니다"  # 지시문 5번 문구. 본문이 이 문구면 정리 줄과 상관없이 unknown


def effective_question(messages) -> str:
    """이번 질문. 되묻기에 대한 짧은 답이면 앞 질문과 합친다 (검색과 LLM에 같은 질문을 쓴다)"""
    last = messages[-1].content.strip()
    previous = [m.content for m in messages[:-1] if m.role == "user"]
    if len(last) < SHORT_QUESTION and previous:
        return f"{previous[-1]}\n(앞 질문에 대한 사용자의 선택: {last})"
    return last


def system_prompt() -> str:
    return SYSTEM + "".join(f'  - "{key}": {desc}\n' for key, (_, desc, _) in ACTIONS.items())


def evidence(hits: list[dict]) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        c = h["chunk"]
        date = f" (수정일 {c['updated_at']})" if c.get("updated_at") else ""
        limit = int(os.getenv("RAG_CHUNK_CHARS", CHUNK_CHARS))  # 실험용 조정값
        text = c["text"] if len(c["text"]) <= limit else c["text"][:limit] + " …(이하 생략)"
        blocks.append(f"[{i}] {c['title']} · {locator_text(c)}{date}\n{text.strip()}")
    return "\n\n".join(blocks)


NOTICE_WORDS = ("제한", "중단", "휴관", "불가", "중지", "폐쇄")


def notices(hits: list[dict]) -> list[tuple[int, str]]:
    """근거 속 '※'로 시작하는 이용 제한 공지 줄 (근거 번호, 문장). 지시문 8번만으로는 자주 빠뜨려 따로 짚어 준다"""
    found = []
    for i, h in enumerate(hits, 1):
        for line in h["chunk"]["text"].splitlines():
            line = line.strip()
            if line.startswith("※") and any(w in line for w in NOTICE_WORDS):
                found.append((i, line))
    return found


def build_messages(messages, hits: list[dict]) -> list[dict]:
    """지시문 + 최근 대화 + (근거 + 이번 질문). 근거는 이번 질문에만 붙인다"""
    history = [{"role": m.role, "content": m.content} for m in messages[:-1]][-HISTORY:]
    alert = "".join(f"\n(주의: 근거 [{i}]에 이용 제한 공지가 있습니다 — \"{line}\" 질문과 관련 있으면 첫 문장에서 알리세요)"
                    for i, line in notices(hits))
    question = f"[근거]\n{evidence(hits)}\n\n[질문]\n{effective_question(messages)}\n{alert}\n{REMINDER}"
    return [{"role": "system", "content": system_prompt()}, *history, {"role": "user", "content": question}]


class MetaFilter:
    """스트림에서 @@META 이후를 걸러 낸다. 표시 조각이 표식의 앞부분일 수 있으면 다음 조각까지 잠시 붙잡는다"""

    def __init__(self):
        self.buffer, self.meta, self.found = "", "", False

    def feed(self, text: str) -> str:
        if self.found:
            self.meta += text
            return ""
        self.buffer += text
        if (i := self.buffer.find(MARKER)) >= 0:
            out, self.meta, self.found, self.buffer = self.buffer[:i], self.buffer[i + len(MARKER):], True, ""
            return out
        keep = next((n for n in range(min(len(MARKER) - 1, len(self.buffer)), 0, -1)
                     if self.buffer.endswith(MARKER[:n])), 0)
        out, self.buffer = self.buffer[:len(self.buffer) - keep], self.buffer[len(self.buffer) - keep:]
        return out

    def flush(self) -> str:
        out, self.buffer = self.buffer, ""
        return out


class Meta(NamedTuple):
    kind: str = "answer"  # 응답 유형
    options: list[str] = []  # clarify 선택지
    keys: list[str] = []  # 고정 링크 이름
    forms: list[int] = []  # 내려받을 서식의 근거 번호 (서식 청크인지는 조립 쪽에서 확인)


def parse_meta(meta: str) -> Meta:
    """형식이 깨지면 일반 답변 (버튼 없음)"""
    try:
        data = json.loads(meta.strip().splitlines()[0])
    except (ValueError, IndexError):
        return Meta()
    kind = data.get("type") if data.get("type") in ("answer", "clarify", "unknown") else "answer"
    options = [o.strip() for o in data.get("options") or [] if isinstance(o, str) and 0 < len(o.strip()) <= 50]
    keys = [k for k in data.get("actions") or [] if isinstance(k, str) and k in ACTIONS]
    forms = [n for n in data.get("forms") or [] if isinstance(n, int) and not isinstance(n, bool)]
    if kind == "clarify" and not options:  # 선택지 없는 되묻기 = 유형을 잘못 적은 일반 답변
        kind = "answer"
    return Meta(kind, options[:MAX_OPTIONS] if kind == "clarify" else [], keys, forms)


URL_OR_PHONE = re.compile(r"https?://|www\.|\b0\d{1,2}-\d{3,4}-\d{4}\b|[\w.+-]+@[\w-]+\.\w+")


def violations(text: str, n_sources: int) -> list[str]:
    """보내고 난 답변의 규칙 위반 (로그용): URL·전화번호·이메일, 없는 근거 번호"""
    found = []
    if URL_OR_PHONE.search(text):
        found.append("url_or_phone")
    if any(not 1 <= int(n) <= n_sources for n in re.findall(r"\[(\d+)\]", text)):
        found.append("bad_citation")
    if re.search(r"\[[a-z_]+\]", text):  # 고정 링크 이름(예: [port_mis])을 본문에 씀
        found.append("action_name")
    return found


RULE_LINE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")  # 구분선: ---, ***, ___ (사이 공백 허용)


class RuleLineFilter:
    """스트림에서 구분선 줄을 지운다. 줄 머리가 구분선일 수 있는 동안(-·*·_·공백만)만 붙잡고, 아니면 바로 내보낸다"""

    def __init__(self):
        self.held = ""  # 줄 머리에서 붙잡은 글자
        self.at_line_start = True

    def feed(self, text: str) -> str:
        out = []
        for ch in text:
            if not self.at_line_start:
                out.append(ch)
                self.at_line_start = ch == "\n"
            elif ch == "\n":
                if not RULE_LINE.match(self.held):
                    out.append(self.held + ch)
                self.held = ""
            elif ch in "-*_ \t":
                self.held += ch
            else:  # 구분선이 아님 → 붙잡은 글자와 함께 내보낸다
                out.append(self.held + ch)
                self.held, self.at_line_start = "", False
        return "".join(out)

    def flush(self) -> str:
        out, self.held = ("" if RULE_LINE.match(self.held) else self.held), ""
        return out


def uncited_lines(text: str) -> list[str]:
    """근거 번호가 없는 내용 줄 (개발용 점검: 규칙 2 준수율)"""
    return [line for line in text.splitlines() if line.strip() and not re.search(r"\[\d+\]", line)]


CONTACT = re.compile(r"https?://[^\s)\]]+|www\.[^\s)\]]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+|0\d{1,2}-\d{3,4}-\d{4}")
MASK = "(공식 안내 참고)"


class ContactFilter:
    """전화번호·이메일·URL이 근거에 글자 그대로 없으면 화면에 나가기 전에 가린다 (LLM이 지어낸 연락처 차단).
    단어 단위로 붙잡았다가 공백에서 검사하므로 단어 하나만큼 늦게 나간다"""

    def __init__(self, evidence: str):
        self.evidence, self.word, self.masked = evidence, "", []

    def _check(self, word: str) -> str:
        def replace(m):
            if m.group(0).rstrip(".,") in self.evidence:
                return m.group(0)
            self.masked.append(m.group(0))
            return MASK
        return CONTACT.sub(replace, word)

    def feed(self, text: str) -> str:
        out = []
        for ch in text:
            if ch.isspace():
                out.append(self._check(self.word) + ch)
                self.word = ""
            else:
                self.word += ch
        return "".join(out)

    def flush(self) -> str:
        out, self.word = self._check(self.word), ""
        return out
