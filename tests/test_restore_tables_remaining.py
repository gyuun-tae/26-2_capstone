"""Synthetic multi-section and batch checks; no official forms or FAQ content."""
import io
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import restore_tables_one as r
import restore_tables_remaining as batch


def record(tag, level, payload):
    return struct.pack('<I', tag | level << 10 | len(payload) << 20) + payload


def section(text):
    return (record(71,1,b' lbt') + record(77,2,struct.pack('<IHH',0,1,1))
            + record(72,2,struct.pack('<IIHHHH',1,0,0,0,1,1)+b'\0'*18)
            + record(66,2,b'\0'*24) + record(67,3,(text+'\r').encode('utf-16le')))


class BatchTests(unittest.TestCase):
    def test_multiple_sections_preserve_ids_and_locations(self):
        header=bytearray(256)
        header[:17]=b'HWP Document File'
        header[35]=5
        struct.pack_into('<I',header,36,1)
        streams={'FileHeader':bytes(header)}
        for i in range(11):
            compressor=zlib.compressobj(wbits=-15)
            streams[f'BodyText/Section{i}']=compressor.compress(section(str(i)))+compressor.flush()
        class FakeOle:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def listdir(self):return [['BodyText',f'Section{i}'] for i in reversed(range(11))]
            def openstream(self,path):return io.BytesIO(streams['/'.join(path) if isinstance(path,list) else path])
        with patch('olefile.OleFileIO',return_value=FakeOle()):
            tables=r.read_tables(b'synthetic','YGPA-025')
        self.assertEqual([t['locator']['section'] for t in tables],[f'Section{i}' for i in range(11)])
        self.assertEqual([t['table_id'] for t in tables],[f'YGPA-025-T{i:03}' for i in range(1,12)])
        self.assertEqual([t['cells'][0]['text'] for t in tables],[str(i) for i in range(11)])
        blocks=[{'locator':c['paragraphs'][0]['text_records'][0]['locator'],'text':c['text']}
                for t in tables for c in t['cells']]
        linked=r.link_blocks(tables,blocks)
        self.assertEqual(len({b['cell_id'] for b in linked}),11)
        self.assertIn('YGPA-025 표 구조 검토',r.render_tables(tables,'YGPA-025'))

    def test_unknown_cell_control_is_held_with_location(self):
        stream=section('설명')+record(71,3,b'????')
        with self.assertRaisesRegex(ValueError,'Section1.*control=3f3f3f3f'):
            r.parse_section(stream,'Section1',doc_id='YGPA-033')

    def test_batch_continues_after_hold(self):
        with patch.object(batch,'restore',side_effect=[ValueError('unsupported'),('saved',Path('out'),{'table_count':1,'cell_count':2})]):
            result=batch.run_batch(Path('.'),[{'doc_id':'YGPA-030'},{'doc_id':'YGPA-022'}],{})
        self.assertEqual([v['state'] for v in result],['held','saved'])
        self.assertEqual(result[0]['reason'],'unsupported')

    def test_preview_does_not_restore(self):
        with patch.object(batch,'select_targets',return_value=({},[{'doc_id':'YGPA-022','title':'합성'}])),patch.object(batch,'run_batch') as run:
            self.assertEqual(batch.main([]),0)
            run.assert_not_called()
        self.assertNotIn('YGPA-021',batch.REMAINING_IDS)
        self.assertNotIn('YGPA-031',batch.REMAINING_IDS)
        self.assertNotIn('YGPA-032',batch.REMAINING_IDS)


if __name__=='__main__':unittest.main()
