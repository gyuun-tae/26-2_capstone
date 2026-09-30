"""Synthetic boundary/lineage tests; no FAQ content or network access."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
c = __import__("13_chunk_remaining")


def fixture(root, url='https://www.ygpa.or.kr/synthetic'):
    text = '신청자격현황\n업체회원만 신청 가능\n신청절차\n1. 신청\n2. 검토\n3. 발급\n'
    raw = root/'data/raw/YGPA-003/snapshot'
    processed = root/'data/processed/YGPA-003/snapshot'
    raw.mkdir(parents=True); processed.mkdir(parents=True)
    (root/'docs/contracts').mkdir(parents=True)
    (root/'catalog.csv').write_text('doc_id,source_url\nYGPA-003,'+url+'\n',encoding='utf8')
    policy = dict(catalog_path='catalog.csv',allowed_hosts=['www.ygpa.or.kr'],allowed_urls=[url],
                  blocked_path_prefixes=['/hmpg/ygpa/comu/faqs/'],blocked_query_values={'bbs_no':['230']})
    (root/'docs/contracts/data_separation_policy.json').write_text(json.dumps(policy),encoding='utf8')
    source = b'<html>synthetic</html>'
    (raw/'source.html').write_bytes(source)
    metadata = dict(doc_id='YGPA-003',source_url=url,final_url=url,content_sha256=c.sha(source))
    doc = dict(metadata,document_version=c.sha(source),text=text,text_sha256=c.sha(text.encode()),
               source_snapshot='snapshot',extraction_version='synthetic',title='합성',date_status='unknown')
    (raw/'metadata.json').write_text(json.dumps(metadata),encoding='utf8')
    (processed/'document.json').write_text(json.dumps(doc),encoding='utf8')
    (processed/'document.txt').write_bytes(text.replace('\n','\r\n').encode())
    return text


class BatchChunkTests(unittest.TestCase):
    def test_reservation_warning_remains_with_all_conditions(self):
        for n in (7,8):
            text='-\n소개\n※ 정부의 자원안보 위기 주의단계 경보 발령에 따라, 경보 해제 시까지 예약 제한\n최소 인원 조건\n'
            spans=c.ranges(f'YGPA-{n:03d}',text)
            body=''.join(text[s['char_start']:s['char_end']] for s in spans if s['status']=='chunk')
            self.assertIn('경보 해제 시까지 예약 제한',body)
            self.assertIn('최소 인원 조건',body)
            self.assertEqual(''.join(text[s['char_start']:s['char_end']] for s in spans),text)

    def test_calendar_excluded_but_two_limits_kept(self):
        text='소개\n1계정 당 하루 최대 2시간, 1개 코트만 예약 가능합니다.\n(코트 2개 중복 예약 불가)\n- 예약가능\n달력\n'
        spans=c.ranges('YGPA-006',text)
        body=''.join(text[s['char_start']:s['char_end']] for s in spans if s['status']=='chunk')
        self.assertIn('중복 예약 불가',body)
        self.assertNotIn('달력',body)

    def test_tables_held_and_not_falsely_covered(self):
        text='메뉴\n부두 정보\n- 면적 : 100㎡\n부두 제원 및 이용 현황\n| 수심 |\n| 10 |\n'
        spans=c.ranges('YGPA-014',text)
        self.assertEqual([s['status'] for s in spans],['excluded','chunk','held'])
        self.assertIn('| 수심 |',text[spans[-1]['char_start']:])
        self.assertEqual(c.ranges('YGPA-012',text)[0]['status'],'held')
        with self.assertRaises(ValueError):
            c.ranges('YGPA-014',text.replace('- 면적 : 100㎡','| 면적 |'))

    def test_crlf_exact_spans_idempotence_and_output_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); text=fixture(root)
            with patch.dict(c.REVIEWED,{'YGPA-003':c.sha(text.encode())}):
                chunks,m=c.prepare(root,'YGPA-003')
                self.assertEqual(c.prepare(root,'YGPA-003')[0],chunks)
                self.assertFalse(chunks[0]['index_approved'])
                self.assertEqual(chunks[0]['updated_at'],'')
                loc=chunks[0]['source_locator']
                self.assertEqual(chunks[0]['text'],text[loc['char_start']:loc['char_end']])
                state,out=c.save(root,chunks,m)
                self.assertEqual(state,'saved')
                self.assertEqual(c.save(root,chunks,m)[0],'existing')
                (out/'chunks.jsonl').write_bytes(b'tampered')
                with self.assertRaises(ValueError): c.save(root,chunks,m)

    def test_source_tampering_and_unreviewed_versions_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); text=fixture(root)
            with self.assertRaisesRegex(ValueError,'검토한 본문'):
                c.prepare(root,'YGPA-003')
            with patch.dict(c.REVIEWED,{'YGPA-003':c.sha(text.encode())}):
                (root/'data/raw/YGPA-003/snapshot/source.html').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'원본 해시'):
                    c.prepare(root,'YGPA-003')

    def test_faq_rejected_even_when_allowlisted(self):
        for url in ('https://www.ygpa.or.kr/hmpg/ygpa/comu/faqs/synthetic','https://www.ygpa.or.kr/synthetic?bbs_no=230'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);fixture(root,url)
                with self.assertRaisesRegex(ValueError,'FAQ'):
                    c.prepare(root,'YGPA-003')


if __name__=='__main__': unittest.main()
