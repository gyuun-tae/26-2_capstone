"""질문 언어 판별과 언어별 고정 문구 (V3 다국어, 2026-11-06).

판별은 글자 종류를 센다 — 모델 호출 없음.
- 한글 음절이 라틴 글자의 절반 이상이면 한국어 ("Port-MIS가 뭐예요?"는 한국어, "How do I get a 출입증?"은 영어)
- 가나(ひらがな·カタカナ)가 있으면 일본어, 한자만 있고 가나가 없으면 중국어
- 라틴 글자만 있으면 영어. 그 밖의 언어(베트남어 등)도 고정 문구는 영어로 보낸다 (본문은 LLM이 질문 언어로 씀)
- 글자가 거의 없는 짧은 말("1", "네?")과 영문 한 단어("Port-MIS", "TEU")는 판단하지 않고 앞 질문의 언어를 따른다
  (앞 질문도 없으면 한국어 — 한국어 사이트에서 약어 하나만 친 사람은 대개 한국어 사용자)

지원 언어는 공사 홈페이지와 같은 한·영·일·중.
"""
import re

HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")
KANA = re.compile(r"[぀-ヿㇰ-ㇿ]")
HAN = re.compile(r"[一-鿿㐀-䶿]")
LATIN = re.compile(r"[A-Za-z]")
LANGS = ("ko", "en", "ja", "zh")
MIN_LETTERS = 2  # 이보다 적으면 판단 보류


def detect(text: str) -> str | None:
    """'ko' | 'en' | 'ja' | 'zh', 판단할 글자가 거의 없으면 None"""
    hangul, kana = len(HANGUL.findall(text)), len(KANA.findall(text))
    han, latin = len(HAN.findall(text)), len(LATIN.findall(text))
    if hangul + kana + han + latin < MIN_LETTERS:
        return None
    if hangul and hangul * 2 >= latin and hangul >= kana + han:
        return "ko"
    if kana:
        return "ja"
    if han and han >= hangul:
        return "zh"
    if latin:
        return "en" if len(text.split()) > 1 else None
    return "ko"


def of_messages(messages, hint: str | None = None) -> str:
    """이번 질문의 언어. 질문 언어가 우선 — 짧은 답이라 판단이 안 되면 앞 질문의 언어,
    그것도 없으면 화면에서 고른 언어(hint), 그것도 없으면 한국어"""
    for m in reversed([m for m in messages if m.role == "user"]):
        if found := detect(m.content):
            # 가나 없이 한자만 쓴 글("港湾施設使用料")은 일본어·중국어를 가를 수 없다 → 일본어 화면이면 일본어
            return "ja" if found == "zh" and hint == "ja" else found
    return hint if hint in LANGS else "ko"


def is_korean(text: str) -> bool:
    return detect(text) in ("ko", None)


# 고정 문구 — LLM이 쓰지 않고 코드가 그대로 보내는 글. 번역은 팀(외국어 검토 담당) 확인 전 초안
TEXT = {
    "gpu_down": {
        "ko": "지금은 답변 서버를 사용할 수 없어 질문에 답하지 못했습니다(점검 중이거나 운영 시간이 아닙니다). "
              "잠시 후 다시 질문해 주시거나, 급한 문의는 아래 대표전화로 연락해 주세요.",
        "en": "The answer server is not available right now, so we could not answer your question (it may be under maintenance "
              "or outside operating hours). Please try again later, or call the main number below for urgent inquiries.",
        "ja": "現在、回答サーバーを利用できないため、ご質問にお答えできませんでした（点検中または運用時間外です）。"
              "しばらくしてから再度ご質問いただくか、お急ぎの場合は下記の代表電話までお問い合わせください。",
        "zh": "目前无法使用回答服务器，未能回答您的问题（可能正在维护或不在运行时间内）。"
              "请稍后再试，如有急事请拨打下方的代表电话。",
    },
    "unknown": {
        "ko": "확인한 공식 자료만으로는 답을 확정하기 어렵습니다. 질문을 조금 더 구체적으로 써 주시거나, 아래 대표전화로 문의해 주세요.",
        "en": "We could not find a definite answer in the official materials we checked. "
              "Please make your question a little more specific, or call the main number below.",
        "ja": "確認した公式資料だけでは回答を確定できません。質問をもう少し具体的に書いていただくか、下記の代表電話までお問い合わせください。",
        "zh": "仅凭已确认的官方资料无法确定答案。请把问题写得更具体一些，或拨打下方的代表电话咨询。",
    },
    "date_note": {
        "ko": "\n\n질문하신 날짜·시기는 확인한 공식 자료에 없습니다. 아래 대표전화로 확인해 주세요.",
        "en": "\n\nThe date or period you asked about is not in the official materials we checked. Please confirm by calling the main number below.",
        "ja": "\n\nお尋ねの日付・時期は確認した公式資料にありません。下記の代表電話でご確認ください。",
        "zh": "\n\n您询问的日期或时间不在已确认的官方资料中。请拨打下方的代表电话确认。",
    },
    "port_mis_note": {
        "ko": "\n\n온라인 신청은 항만운영정보시스템(Port-MIS)에서도 할 수 있습니다[{n}].",
        "en": "\n\nYou can also apply online through the Port Management Information System (Port-MIS)[{n}].",
        "ja": "\n\nオンライン申請は港湾運営情報システム（Port-MIS）でも行えます[{n}]。",
        "zh": "\n\n也可以通过港口运营信息系统（Port-MIS）在线申请[{n}]。",
    },
    "main_label": {
        "ko": "여수광양항만공사 대표전화",
        "en": "Yeosu Gwangyang Port Authority (main line)",
        "ja": "麗水光陽港湾公社 代表電話",
        "zh": "丽水光阳港湾公社 代表电话",
    },
    "main_note": {
        "ko": "담당 부서를 모를 때",
        "en": "If you don't know which department to ask",
        "ja": "担当部署が分からない場合",
        "zh": "不清楚负责部门时",
    },
    "port_mis_label": {"ko": "Port-MIS 열기", "en": "Open Port-MIS", "ja": "Port-MISを開く", "zh": "打开 Port-MIS"},
    "login_needed": {"ko": "로그인 필요", "en": "Login required", "ja": "ログインが必要", "zh": "需要登录"},
}


def text(key: str, language: str) -> str:
    table = TEXT[key]
    return table.get(language) or table["en"]
