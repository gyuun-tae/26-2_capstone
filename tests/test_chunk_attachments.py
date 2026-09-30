"""Synthetic attachment chunk tests; no evaluation material or network calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
c = __import__("15_chunk_attachments")


def block(text,page):return {'text':text,'locator':{'kind':'pdf_page','page_number':page}}


def fixture(root):
    raw=root/'data/raw/YGPA-021/snapshot';folder=root/'data/processed/YGPA-021/snapshot';side=folder/'hwp-tables-v1'
    raw.mkdir(parents=True);side.mkdir(parents=True);(root/'docs/contracts').mkdir(parents=True)
    url='https://www.ygpa.or.kr/synthetic';parent=url+'/parent'
    policy={'allowed_hosts':['www.ygpa.or.kr'],'allowed_urls':[url], 'blocked_path_prefixes':['/hmpg/ygpa/comu/faqs/'],'blocked_query_values':{'bbs_no':['230']}}
    (root/'docs/contracts/data_separation_policy.json').write_text(json.dumps(policy),encoding='utf8')
    row=dict(doc_id='YGPA-021',source_url=url,parent_source_url=parent)
    meta=dict(row,final_url=url)
    (raw/'metadata.json').write_text(json.dumps(meta),encoding='utf8')
    data=b'synthetic HWP bytes'
    loc={'kind':'hwp_record','section':'Section0','record_number':1}
    blocks=[{'locator':loc,'text':'신청 항목'}, {'locator':dict(loc,record_number=2),'text':'동의 여부와 예외 조건'}]
    encode=lambda x:json.dumps(x,ensure_ascii=False).encode()
    text=c.build_text({'blocks':blocks})
    doc=dict(meta,document_version=c.sha(data),source_snapshot='snapshot',extracted_format='hwp5',extraction_version='test',
             title='합성 신청서',text=text,text_sha256=c.sha(text.encode()),blocks_sha256=c.sha(encode(blocks)))
    (folder/'document.json').write_bytes(encode(doc));(folder/'document.txt').write_bytes(text.encode());(folder/'blocks.json').write_bytes(encode(blocks))
    cells=[dict(cell_id='C1',row=0,column=0,rowspan=1,colspan=1,text='신청 항목',nested_table_ids=[],is_blank=False),
           dict(cell_id='C2',row=0,column=1,rowspan=1,colspan=1,text='',nested_table_ids=[],is_blank=True)]
    tables=[dict(table_id='T1',rows=1,columns=2,cells=cells,parent_cell_id=None)]
    linked=[dict(blocks[0],table_id='T1',cell_id='C1'),dict(blocks[1],table_id=None,cell_id=None)]
    outputs={'tables.json':encode(dict(source_sha256=c.sha(data),doc_id=row['doc_id'],tables=tables)), 'blocks_with_tables.json':encode(linked)}
    for name,value in outputs.items():(side/name).write_bytes(value)
    report=dict(version='hwp-tables-v1',source_sha256=c.sha(data),input_blocks_sha256=doc['blocks_sha256'],output_hashes={k:c.sha(v) for k,v in outputs.items()})
    (side/'validation.json').write_bytes(encode(report))
    return row,policy,raw,meta,data,side


class AttachmentChunkTests(unittest.TestCase):
    def test_article_crosses_pages_and_preserves_exceptions(self):
        blocks=[block('제1조(대상) 원칙\n① 대상\n',1),block('② 다만 예외\n제2조(신청) 서류 전부\n부 칙 (2020)\n제1조(시행일) 과거 시행일',2)]
        units=c.split_regulation(blocks,[0,1],'blocks.json')
        self.assertEqual([u['kind'] for u in units],['article','article','historical_addendum'])
        self.assertIn('다만 예외',units[0]['text'])
        self.assertEqual([r['locator']['page_number'] for r in units[0]['source_refs']],[1,2])
        self.assertIn('과거 시행일',units[-1]['text'])
        for i,b in enumerate(blocks):
            ranges=sorted((r['char_start'],r['char_end']) for u in units for r in u['source_refs'] if r['block_index']==i)
            self.assertEqual(''.join(b['text'][a:z] for a,z in ranges),b['text'])

    def test_article_reference_is_not_boundary_and_subarticle_is(self):
        text='개정 이력\n제4조(제목) 내용\n제3조에 따라 신청함\n제4조의2(다음 조항) 예외\n'
        units=c.split_regulation([block(text,1)],[0],'blocks.json')
        self.assertEqual([u['title'] for u in units],['제·개정 이력','제4조','제4조의2'])
        self.assertIn('제3조에 따라',units[1]['text'])

    def test_whole_form_and_blank_fields_save_repeat_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);row,p,raw,meta,data,side=fixture(root)
            with patch.object(c,'validate_source',return_value=(raw,meta,data)),patch.dict(c.SOURCES,{'YGPA-021':c.sha(data)}):
                chunks,m=c.prepare(root,row,p)
                self.assertEqual(len(chunks),1);self.assertIn('동의 여부와 예외 조건',chunks[0]['text'])
                self.assertIn('미기재 빈 셀 1개',chunks[0]['text']);self.assertFalse(chunks[0]['index_approved'])
                self.assertEqual(chunks[0]['updated_at'],'');self.assertEqual(c.prepare(root,row,p)[0],chunks)
                state,out=c.save(root,chunks,m);self.assertEqual(state,'saved')
                self.assertEqual(c.save(root,chunks,m)[0],'existing')
                (out/'chunks.jsonl').write_bytes(b'tamper')
                with self.assertRaises(ValueError):c.save(root,chunks,m)
                (side/'tables.json').write_bytes(b'tamper')
                with self.assertRaisesRegex(ValueError,'해시'):c.prepare(root,row,p)

    def test_faq_is_blocked_even_after_mocked_source_validation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);row,p,raw,meta,data,side=fixture(root)
            url='https://www.ygpa.or.kr/hmpg/ygpa/comu/faqs/synthetic'
            p['allowed_urls'].append(url);row['source_url']=url;meta.update(source_url=url,final_url=url)
            docpath=side.parent/'document.json';doc=json.loads(docpath.read_bytes());doc.update(source_url=url,final_url=url);docpath.write_text(json.dumps(doc),encoding='utf8')
            with patch.object(c,'validate_source',return_value=(raw,meta,data)),patch.dict(c.SOURCES,{'YGPA-021':c.sha(data)}):
                with self.assertRaisesRegex(ValueError,'FAQ'):c.prepare(root,row,p)

    def test_pdf_appendices_held_historical_flag_and_missing_article_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'docs/contracts').mkdir(parents=True);(root/'docs/contracts/data_separation_policy.json').write_bytes(b'{}')
            blocks=[block('제1조(목적) 본문\n',1)]
            for n in range(2,13):
                text=''.join(f'제{i}조(제목) 조건\n' for i in range(2,32))+'부 칙 (2020)\n제1조(시행일) 2020년\n' if n==2 else '\n'
                blocks.append(block(text,n))
            blocks.append(block('미복원 표 숫자 999',13))
            doc=dict(doc_id='YGPA-031',source_snapshot='snapshot',document_version='hash',extracted_format='pdf')
            folder=root/'data/processed/YGPA-031/snapshot'
            with patch.object(c,'load',return_value=(doc,blocks,[],[],folder,{})):
                chunks,m=c.prepare(root,{'doc_id':'YGPA-031'}, {})
                self.assertEqual(len(chunks),32)
                self.assertTrue(all('999' not in x['text'] for x in chunks))
                self.assertIn('historical_provision_not_current_rule',chunks[-1]['review_flags'])
                self.assertEqual(m['coverage'][-1]['status'],'held')
                blocks[1]['text']=blocks[1]['text'].replace('제3조(제목)','제2조(제목)')
                with self.assertRaisesRegex(ValueError,'조항 번호'):c.prepare(root,{}, {})

    def test_nested_tables_and_inline_glyphs_preserved_graphics_rejected(self):
        cell=dict(row=0,column=0,rowspan=2,colspan=2,text='부모',is_blank=False,nested_table_ids=['T2'],inline_controls=[{'text':'①'}])
        table=dict(table_id='T1',rows=2,columns=2,parent_cell_id=None,cells=[cell])
        text=c.table_text([table]);self.assertIn('포함 표: T2',text);self.assertIn('①',text);self.assertIn('행 1~2, 열 1~2',text)
        cell['graphic_objects']=[{}]
        with self.assertRaisesRegex(ValueError,'시각 개체'):c.table_text([table])

    def test_output_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'side';folder.mkdir();(root/'outside').write_bytes(b'x')
            with self.assertRaises(ValueError):c.verify_outputs(folder,{'output_hashes':{'../outside':c.sha(b'x')}})


if __name__=='__main__':unittest.main()
