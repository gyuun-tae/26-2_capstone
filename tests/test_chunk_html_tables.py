"""Synthetic HTML tables only. No network, official data, or evaluation answers."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chunk_html_tables as c
from test_chunk_remaining import fixture

TABLE='''<table><caption>시설 표</caption><thead><tr><th rowspan="2">시설</th><th colspan="2">수량</th></tr><tr><th>길이(m)</th><th>합계</th></tr></thead><tbody><tr><th rowspan="2">부두 A</th><td>100</td><td rowspan="2">300</td></tr><tr><td>200</td></tr><tr><th>부두 B</th><td></td><td>-</td></tr></tbody></table>'''

def html(table): return '앞부분\r\n<!-- 내용 시작 -->'+table+'<!-- 내용 끝 -->뒤'


class HtmlTableTests(unittest.TestCase):
    def test_nested_headers_shared_total_and_blank_cells(self):
        t=c.parse_tables(html(TABLE))[0]
        self.assertEqual(t['groups'],[(2,4),(4,5)])
        self.assertEqual(t['grid'][2][2],t['grid'][3][2])
        rendered=c.render_text('제목',t,2,4,[])
        self.assertEqual(rendered.count(': 300'),1)
        self.assertIn('행 3~4',rendered)
        self.assertIn('수량 / 길이(m)',rendered)
        second=c.render_text('제목',t,4,5,[])
        self.assertIn('(원문 빈칸)',second)
        self.assertIn(': -',second)

    def test_comments_scripts_and_inactive_tables_ignored(self):
        s=html('<!--'+TABLE+'--><script>var x="<table>";</script>'+TABLE)
        self.assertEqual(len(c.parse_tables(s)),1)

    def test_raw_cell_locations_keep_crlf_and_entities(self):
        s=html(TABLE.replace('부두 B','A &amp; B'))
        t=c.parse_tables(s)[0]
        self.assertEqual(s[t['char_start']:t['char_end']],TABLE.replace('부두 B','A &amp; B'))
        cell=t['rows'][-1]['cells'][0]
        self.assertEqual(cell['text'],'A & B')
        self.assertEqual(s[cell['char_start']:cell['char_end']],'<th>A &amp; B</th>')

    def test_broken_spans_preserved_but_not_guessed(self):
        for bad in (TABLE.replace('rowspan="2">300','rowspan="9">300'),TABLE.replace('<td>200</td>','')):
            t=c.parse_tables(html(bad))[0]
            self.assertIn('geometry_error',t)
            self.assertNotIn('grid',t)
            self.assertIn('300',str(t))
            view=c.review_html([t],dict(doc_id='synthetic',table_row_coverage=[]))
            self.assertIn('구조 검증 보류',view)

    def test_header_body_crossing_and_nested_tables_rejected(self):
        t=c.parse_tables(html(TABLE.replace('rowspan="2">시설','rowspan="3">시설')))[0]
        self.assertIn('geometry_error',t)
        with self.assertRaises(ValueError):c.parse_tables(html('<table><tr><td>'+TABLE+'</td></tr></table>'))

    def test_invalid_time_and_known_header_misalignment_held(self):
        t=c.parse_tables(html(TABLE.replace('100','13:000')))[0]
        self.assertIn('시각',c.hold_reason('YGPA-009',t,2,4))
        self.assertIn('13:000',t['rows'][2]['cells'][1]['text'])
        self.assertIn('열 의미 불일치',c.hold_reason('YGPA-013',t,2,4))
        self.assertIsNone(c.hold_reason('YGPA-009',c.parse_tables(html(TABLE))[0],2,4))

    def test_exceptions_and_total_exclusions_keep_exact_source_offsets(self):
        text='서두\n* 축구장 시설은 예외시간 운영\n예약기한 안내\n시설 사용료\n표\n체육시설 이용 시 유의사항\n우천 시 금지\n사용문의(연락처)\n'
        spans=c.contexts('YGPA-005',2,{'text':text})
        self.assertEqual(len(spans),2)
        for s in spans:self.assertEqual(s['text'],text[s['char_start']:s['char_end']])
        self.assertIn('예외시간',spans[0]['text'])
        self.assertIn('우천 시 금지',spans[1]['text'])
        foot='본문\n* 소형선부두·관용선 부두 등 산정 제외\n※ 컨테이너 하역능력 제외\n'
        self.assertIn('컨테이너',c.contexts('YGPA-012',1,{'text':foot})[0]['text'])

    def test_end_to_end_save_repeat_tamper_and_faq_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);text=fixture(root)
            source=html(TABLE).encode()
            raw=root/'data/raw/YGPA-003/snapshot'
            processed=root/'data/processed/YGPA-003/snapshot'
            (raw/'source.html').write_bytes(source)
            for p in (raw/'metadata.json',processed/'document.json'):
                data=json.loads(p.read_bytes());data['content_sha256']=c.sha(source)
                if 'document_version' in data:data['document_version']=c.sha(source)
                p.write_text(json.dumps(data),encoding='utf8')
            with patch.dict(c.SOURCES,{'YGPA-003':(c.sha(source),1)}),patch.dict(c.prose.REVIEWED,{'YGPA-003':c.sha(text.encode())}):
                chunks,tables,m=c.prepare(root,'YGPA-003')
                self.assertEqual(len(chunks),2)
                self.assertFalse(chunks[0]['index_approved'])
                self.assertEqual(c.prepare(root,'YGPA-003')[0],chunks)
                state,out=c.save(root,chunks,tables,m)
                self.assertEqual(state,'saved')
                self.assertEqual(c.save(root,chunks,tables,m)[0],'existing')
                (out/'tables.json').write_bytes(b'changed')
                with self.assertRaises(ValueError):c.save(root,chunks,tables,m)
                (raw/'source.html').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'해시'):c.prepare(root,'YGPA-003')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root,'https://www.ygpa.or.kr/hmpg/ygpa/comu/faqs/synthetic')
            with patch.dict(c.SOURCES,{'YGPA-003':('unused',1)}):
                with self.assertRaisesRegex(ValueError,'FAQ'):c.prepare(root,'YGPA-003')

    def test_review_escapes_source_markup(self):
        t=c.parse_tables(html(TABLE.replace('부두 B','&lt;script&gt;bad&lt;/script&gt;')))[0]
        view=c.review_html([t],dict(doc_id='synthetic',table_row_coverage=[]))
        self.assertNotIn('<script>',view)
        self.assertIn('&lt;script&gt;',view)


if __name__=='__main__':unittest.main()
