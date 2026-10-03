"""청크 → 화면용 근거 변환 확인: uv run python test_sources.py
실제 청크는 Git에 없으므로 형식별 합성 청크로 시험한다."""
from app.sources import chunk_to_source, form_download


def chunk(**kw):
    base = dict(doc_id="YGPA-X", chunk_id="c1", title="문서", source_url="https://www.ygpa.or.kr/x", section_titles=[],
                published_at="", updated_at="", date_status="not_displayed", fetched_at="2026-09-23T10:00:00+09:00")
    return base | kw


html_text = chunk(source_locator={"kind": "processed_text"}, section_titles=["신청자격", "신청절차"], text="신청자격\n- 회원가입 후 사용")
table = chunk(
    source_locator={"kind": "html_table"}, section_titles=["이용시간 기본정보"], title="체육시설",
    text="체육시설\n이용시간 기본정보\n행·열 번호는 원본 표 기준(1부터 시작).\n- 행 2, 열 1 [구분]: 축구장",
)
pdf_article = chunk(
    source_locator={"kind": "attachment_composite", "source_refs": [
        {"locator": {"kind": "pdf_page", "page_number": 3}}, {"locator": {"kind": "pdf_page", "page_number": 4}}]},
    chunk_kind="article", section_titles=["제5조"], text="제5조(사용허가) ① 항만시설을 사용하려는 자는",
)
form = chunk(
    source_locator={"kind": "attachment_composite", "source_refs": [{"locator": {"kind": "hwp_record"}}]},
    chunk_kind="whole_form", title="선박제원신고서", section_titles=["서식 전체"],
    source_url="https://www.ygpa.or.kr/hmpg/comm/file/fileDownLoad.do?file_no=F1",
    text="선박제원신고서\n표 밖 안내:\n【별지 제3호 서식】\n표 좌표는 1부터 시작합니다.\n행 1~1, 열 1~2: 선박명",
)

assert chunk_to_source(html_text).locator == "신청자격 · 신청절차"
s = chunk_to_source(table)
assert s.locator == "이용시간 기본정보 표" and s.snippet == "이용시간 기본정보 구분: 축구장", s.snippet
s = chunk_to_source(pdf_article)
assert s.locator == "제5조(사용허가) · 3~4쪽", s.locator
assert s.published_at is None and s.updated_at is None  # 빈 날짜는 null, 수집일로 채우지 않음
s = chunk_to_source(form)
assert s.locator == "서식 전체" and s.snippet == "【별지 제3호 서식】 선박명", s.snippet

# 법령 조문: 위치는 조문 번호·제목 그대로(띄어쓰기 유지), 날짜는 공포일
law = chunk(
    source_locator={"kind": "law_api", "article_label": "제41조(항만시설의 사용)", "part": 1, "part_count": 1},
    chunk_kind="article", title="항만법", section_titles=["제5장 항만시설의 사용", "제41조(항만시설의 사용)"],
    published_at="2026-02-27", effective_at="2026-02-27", date_status="official_api_current",
    text="제41조(항만시설의 사용)\n① 항만시설을 사용하려는 자는",
)
s = chunk_to_source(law)
assert s.locator == "제41조(항만시설의 사용)" and s.published_at == "2026-02-27", s
assert form_download(law, source_ref=1) is None

# 서식만 다운로드 버튼이 생기고, URL은 청크의 원문 주소 그대로
a = form_download(form, source_ref=2)
assert (a.type, a.label, a.url, a.source_ref) == ("download", "선박제원신고서(HWP)", form["source_url"], 2)
assert form_download(pdf_article, source_ref=1) is None

print("OK")
