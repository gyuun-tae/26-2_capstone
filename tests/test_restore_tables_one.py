"""Synthetic table fixtures; no real source forms or evaluation data."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import restore_tables_one as r


def rec(tag, level, payload):
    return struct.pack('<I', tag | (level << 10) | (len(payload) << 20)) + payload


def start_table(level, rows, cols):
    return rec(71, level, b' lbt') + rec(77, level + 1, struct.pack('<IHH', 0, rows, cols))


def cell(level, row, col, rs=1, cs=1, text='', count=1):
    header = struct.pack('<IIHHHH', count, 0, col, row, cs, rs) + b'\0' * 18
    return (rec(72, level, header) + rec(66, level, b'\0' * 24)
            + rec(67, level + 1, (text + '\r').encode('utf-16le')))


def source():
    return start_table(1, 2, 2) + cell(2, 0, 0, rs=2, text='담당자') + cell(2, 0, 1, text='성명') + cell(2, 1, 1)


class RestoreTests(unittest.TestCase):
    def test_merged_and_blank_cells(self):
        t = r.parse_section(source(), 'Section0')[0]
        self.assertEqual((t['rows'], t['columns']), (2, 2))
        self.assertEqual([(c['row'], c['column'], c['rowspan'], c['text']) for c in t['cells']],
                         [(0, 0, 2, '담당자'), (0, 1, 1, '성명'), (1, 1, 1, '')])
        self.assertTrue(t['cells'][-1]['is_blank'])

    def test_overlap_gap_and_overflow_are_rejected(self):
        streams = [start_table(1, 1, 2) + cell(2, 0, 0) + cell(2, 0, 0),
                   start_table(1, 1, 2) + cell(2, 0, 0),
                   start_table(1, 1, 1) + cell(2, 0, 0, cs=2)]
        for stream in streams:
            with self.assertRaises(ValueError): r.parse_section(stream, 'Section0')

    def test_nested_table_keeps_parent_cell(self):
        stream = start_table(1, 1, 1) + cell(2, 0, 0)
        stream += start_table(3, 1, 1) + cell(4, 0, 0, text='내부 항목')
        tables = r.parse_section(stream, 'Section0')
        self.assertEqual(len(tables), 2)
        outer_cell = tables[0]['cells'][0]
        self.assertEqual(tables[1]['parent_cell_id'], outer_cell['cell_id'])
        self.assertEqual(outer_cell['nested_table_ids'], [tables[1]['table_id']])
        self.assertTrue(outer_cell['is_text_blank'])
        self.assertFalse(outer_cell['is_blank'])
        self.assertEqual(outer_cell['text'], '')

    def test_return_to_outer_cell_after_nested_table(self):
        stream = start_table(1, 1, 2) + cell(2, 0, 0)
        stream += start_table(3, 1, 1) + cell(4, 0, 0, text='내부') + cell(2, 0, 1, text='외부')
        tables = r.parse_section(stream, 'Section0')
        self.assertEqual(tables[0]['cells'][1]['text'], '외부')
        self.assertEqual(tables[1]['cells'][0]['text'], '내부')

    def test_declared_paragraph_count(self):
        with self.assertRaises(ValueError):
            r.parse_section(start_table(1, 1, 1) + cell(2, 0, 0, count=2), 'Section0')

    def test_unsupported_caption_and_orphan_table(self):
        for stream in (rec(71,1,b' lbt') + cell(2,0,0), rec(77,2,b'\0'*8)):
            with self.assertRaises(ValueError): r.parse_section(stream,'Section0')

    def make_blocks(self, tables):
        return [{'locator':p['locator'],'text':p['text']} for t in tables for c in t['cells']
                for paragraph in c['paragraphs'] for p in paragraph['text_records'] if p['text']]

    def test_links_preserve_original_and_outside_text(self):
        tables = r.parse_section(source(), 'Section0')
        blocks = self.make_blocks(tables)
        blocks.append({'locator':{'section':'Section0','record_number':999},'text':'표 밖 안내'})
        before = copy.deepcopy(blocks)
        linked = r.link_blocks(tables, blocks)
        self.assertEqual(blocks,before)
        self.assertEqual(linked[0]['cell_id'],tables[0]['cells'][0]['cell_id'])
        self.assertIsNone(linked[-1]['cell_id'])
        for bad in (blocks[1:], [dict(blocks[0],text='다른 글자')]+blocks[1:], blocks+blocks[:1]):
            with self.assertRaises(ValueError): r.link_blocks(tables,bad)

    def test_html_escapes_source_text(self):
        tables = r.parse_section(start_table(1,1,1)+cell(2,0,0,text='<script>test</script>'),'Section0')
        rendered = r.render_tables(tables)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertNotIn('<script>', rendered)

    def test_sidecar_save_skip_and_no_overwrite(self):
        tables = r.parse_section(source(),'Section0')
        blocks = self.make_blocks(tables)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            snapshot=root/'data/raw/YGPA-021/snapshot'
            processed=root/'data/processed/YGPA-021/snapshot'
            processed.mkdir(parents=True)
            block_bytes=json.dumps(blocks,ensure_ascii=False).encode()
            text_bytes=b'unchanged'
            (processed/'blocks.json').write_bytes(block_bytes)
            (processed/'document.txt').write_bytes(text_bytes)
            row={'doc_id':'YGPA-021','source_url':'https://www.ygpa.or.kr/test'}
            raw=b'test source'
            doc={**row,'document_version':r.sha(raw),'blocks_sha256':r.sha(block_bytes),
                 'text_sha256':r.sha(text_bytes),'extraction_details':{'table_count':1}}
            (processed/'document.json').write_text(json.dumps(doc),encoding='utf8')
            with patch.object(r,'validate_source',return_value=(snapshot,{},raw)),patch.object(r,'read_tables',return_value=tables):
                state,out,validation=r.restore(root,row,{})
                self.assertEqual(state,'saved')
                self.assertEqual(r.restore(root,row,{})[0],'existing')
                self.assertEqual((processed/'document.txt').read_bytes(),text_bytes)
                self.assertEqual((processed/'blocks.json').read_bytes(),block_bytes)
                self.assertFalse(validation['index_approved'])
                (out/'tables.json').write_text('modified')
                with self.assertRaises(ValueError):r.restore(root,row,{})


if __name__=='__main__': unittest.main()
