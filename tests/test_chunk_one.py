"""Synthetic pilot and FAQ boundary tests; no evaluation content."""
import json
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chunk_one as c

TEXT='신청자격\n- 예외 조건 유지\n신청절차\n1. 회원가입\n2. 신청서 작성\n3. 신청서 검토\n4. 신청서 완료\n'+c.SUFFIX
URL='https://www.ygpa.or.kr/synthetic'

def fixture(root,url=URL):
    raw=root/'data/raw/YGPA-001/snapshot';processed=root/'data/processed/YGPA-001/snapshot'
    raw.mkdir(parents=True);processed.mkdir(parents=True);(root/'docs/contracts').mkdir(parents=True)
    (root/'catalog.csv').write_text('doc_id,source_url\nYGPA-001,'+url+'\n',encoding='utf8')
    policy={'catalog_path':'catalog.csv','allowed_hosts':['www.ygpa.or.kr'],'allowed_urls':[url],
            'blocked_path_prefixes':['/hmpg/ygpa/comu/faqs/'],'blocked_query_values':{'bbs_no':['230']}}
    (root/'docs/contracts/data_separation_policy.json').write_text(json.dumps(policy),encoding='utf8')
    data=b'<html>synthetic</html>';(raw/'source.html').write_bytes(data)
    meta={'doc_id':c.DOC_ID,'source_url':url,'final_url':url,'content_sha256':c.sha(data)}
    (raw/'metadata.json').write_text(json.dumps(meta),encoding='utf8')
    doc={**meta,'document_version':c.sha(data),'text_sha256':c.sha(TEXT.encode()),'source_snapshot':'snapshot',
         'text':TEXT,'extraction_version':'test-v1','title':'합성 안내','fetched_at':'2026-09-29T00:00:00Z','date_status':'unknown'}
    (processed/'document.json').write_text(json.dumps(doc),encoding='utf8')
    (processed/'document.txt').write_bytes(TEXT.replace('\n','\r\n').encode())
    return processed

class ChunkTests(unittest.TestCase):
    def test_step_integrity_and_coverage(self):
        body,excluded=c.split_body(TEXT)
        self.assertIn('예외 조건 유지',body);self.assertIn('4. 신청서 완료',body)
        self.assertEqual(body+excluded['text'],TEXT)
        self.assertNotIn('사진촬영신청',body)
        with self.assertRaises(ValueError):c.split_body(TEXT.replace('2. 신청서 작성','3. 신청서 작성'))
    def test_crlf_offsets_stable_id_save_and_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);processed=fixture(root);before=(processed/'document.txt').read_bytes()
            chunks,m=c.prepare(root);self.assertEqual(c.prepare(root)[0],chunks)
            loc=chunks[0]['source_locator'];self.assertEqual(TEXT[loc['char_start']:loc['char_end']],chunks[0]['text'])
            self.assertFalse(chunks[0]['index_approved']);self.assertEqual(chunks[0]['updated_at'],'')
            state,out=c.save(root,chunks,m);self.assertEqual(state,'saved');self.assertEqual(c.save(root,chunks,m)[0],'existing')
            self.assertEqual((processed/'document.txt').read_bytes(),before)
            (out/'chunks.jsonl').write_bytes(b'tamper')
            with self.assertRaises(ValueError):c.save(root,chunks,m)
    def test_faq_deny_before_allowlist(self):
        for url in ('https://www.ygpa.or.kr/hmpg/ygpa/comu/faqs/synthetic','https://www.ygpa.or.kr/synthetic?bbs_no=230'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);fixture(root,url)
                with self.assertRaisesRegex(ValueError,'FAQ'):c.prepare(root)
    def test_modified_source_or_text_is_rejected(self):
        for path in ('data/raw/YGPA-001/snapshot/source.html','data/processed/YGPA-001/snapshot/document.txt'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);fixture(root);(root/path).write_bytes(b'modified')
                with self.assertRaises(ValueError):c.prepare(root)

if __name__=='__main__':unittest.main()
