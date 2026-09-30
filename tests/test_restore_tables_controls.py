"""Synthetic overlapping-text fixtures, without official forms or FAQ data."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
r = __import__("07_restore_tables_one")
from test_restore_tables_one import rec, start_table, cell


def overlap(text='가', ids=(2,3)):
    encoded=text.encode('utf-16le')
    return b'spct'+struct.pack('<H',len(encoded)//2)+encoded+struct.pack('<BbBB',0,-4,0,len(ids))+struct.pack(f'<{len(ids)}I',*ids)


class OverlapTests(unittest.TestCase):
    def test_preserves_glyphs_and_original_control_bytes(self):
        payload=overlap('가😀')
        control=r.parse_overlapping(payload,{'record_number':9})
        self.assertEqual(control['text'],'가😀')
        self.assertEqual(control['internal_size'],-4)
        self.assertEqual(control['charshape_ids'],[2,3])
        self.assertEqual(bytes.fromhex(control['raw_payload_hex']),payload)

    def test_rejects_truncated_extra_and_invalid_utf16(self):
        bad=b'spct'+struct.pack('<H',1)+b'\x00\xd8'+bytes(4)
        for payload in (overlap()[:-1],overlap()+b'x',b'spct',bad):
            with self.assertRaises(ValueError):r.parse_overlapping(payload,{})

    def test_control_stays_in_owning_cell_and_not_blank(self):
        stream=start_table(1,1,2)+cell(2,0,0)+rec(71,3,overlap('<'))+cell(2,0,1,text='뒤 칸')
        tables=r.parse_section(stream,'Section0',doc_id='YGPA-033')
        first,second=tables[0]['cells']
        self.assertEqual(first['text'],'')
        self.assertTrue(first['is_text_blank'])
        self.assertFalse(first['is_blank'])
        self.assertEqual(first['inline_controls'][0]['text'],'<')
        self.assertNotIn('inline_controls',second)
        self.assertEqual(second['text'],'뒤 칸')
        rendered=r.render_tables(tables,'YGPA-033')
        self.assertIn('글자 겹침: &lt;',rendered)
        self.assertIn('원문 확인',rendered)

    def test_unexpected_child_or_control_still_held(self):
        base=start_table(1,1,1)+cell(2,0,0)
        for stream in (base+rec(71,3,overlap())+rec(72,4,bytes(34)),base+rec(71,3,b' osg'+bytes(42))):
            with self.assertRaises(ValueError):r.parse_section(stream,'Section0',doc_id='YGPA-033')
        with self.assertRaises(ValueError):r.parse_section(base+rec(71,3,overlap()),'Section0',doc_id='YGPA-030')

if __name__=='__main__':unittest.main()
