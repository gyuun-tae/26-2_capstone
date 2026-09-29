"""Synthetic preservation/linking tests; no source documents or FAQ fixtures."""
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import restore_graphics_030 as g
from test_restore_tables_one import rec,start_table,cell
r=g.r


def sample():
    group=rec(71,3,b' osg'+bytes(42))+rec(76,4,b'synthetic-shape')
    group+=rec(66,5,bytes(24))+rec(67,6,'표시문\r'.encode('utf-16le'))
    stream=start_table(1,1,2)+cell(2,0,0)+group+cell(2,0,1,text='다음 셀')
    tables=r.parse_section(stream,'Section0',doc_id='YGPA-030',preserve_graphics=True)
    return tables,group


class GraphicsTests(unittest.TestCase):
    def test_raw_records_and_cell_ownership_preserved(self):
        tables,group=sample()
        first,second=tables[0]['cells']
        obj=g.graphic_objects(tables)[0]
        self.assertEqual(b''.join(bytes.fromhex(v['raw_record_hex']) for v in obj['records']),group)
        self.assertEqual(obj['record_bytes_sha256'],r.sha(group))
        self.assertFalse(first['is_blank'])
        self.assertEqual(first['text'],'')
        self.assertEqual(second['text'],'다음 셀')
        self.assertNotIn('graphic_objects',second)
        self.assertEqual([v['text'] for v in obj['text_records']],['표시문'])
        self.assertEqual(obj['records'][1]['level_parent_record'],obj['locator']['record_number'])
        self.assertEqual(obj['visual_layout_status'],'not_rendered_pending_review')

    def test_graphic_text_links_and_missing_text_rejected(self):
        tables,_=sample();obj=g.graphic_objects(tables)[0]
        normal=tables[0]['cells'][1]['paragraphs'][0]['text_records'][0]
        blocks=[dict(obj['text_records'][0]),dict(normal)]
        linked=r.link_blocks(tables,blocks)
        self.assertEqual(linked[0]['graphic_object_id'],obj['object_id'])
        self.assertIsNone(linked[1]['graphic_object_id'])
        self.assertNotIn('cell_id',blocks[0])
        with self.assertRaises(ValueError):r.link_blocks(tables,blocks[1:])

    def test_binitem_rejects_links_paths_and_truncation(self):
        for payload in (struct.pack('<HHH',0,1,0),struct.pack('<HHH',1,1,2)+b'a\0',struct.pack('<HHH',1,1,2)+'..'.encode('utf-16le')):
            with self.assertRaises(ValueError):g.embedded_item(payload)

    def test_picture_uses_item_id_not_first_asset(self):
        info=rec(18,0,struct.pack('<HHH',1,3,3)+'jpg'.encode('utf-16le'))
        info+=rec(18,0,struct.pack('<HHH',1,7,3)+'jpg'.encode('utf-16le'))
        header=bytearray(256)
        streams={'FileHeader':bytes(header),'DocInfo':info,'BinData/BIN0007.jpg':b'\xff\xd8\xffsynthetic'}
        class FakeOle:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def openstream(self,path):return io.BytesIO(streams[path])
        payload=bytearray(78);struct.pack_into('<H',payload,71,2)
        objects=[{'records':[{'tag':85,'payload_hex':payload.hex(),'locator':{}}]}]
        with patch('olefile.OleFileIO',return_value=FakeOle()):
            assets,outputs=g.collect_assets(b'test',objects)
            self.assertEqual(assets[0]['storage_path'],'BinData/BIN0007.jpg')
            self.assertIn('image-002.jpg',outputs)
            streams['BinData/BIN0007.jpg']=b'bad-image'
            with self.assertRaises(ValueError):g.collect_assets(b'test',objects)

    def test_review_view_marks_layout_pending_and_escapes_text(self):
        tables,_=sample();objects=g.graphic_objects(tables)
        objects[0]['image_refs']=[]
        objects[0]['text_records'][0]['text']='<script>'
        page=g.render_graphics(objects,[])
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('<script>',page)
        self.assertIn('배치를 재현하지 않았습니다',page)
        self.assertIn('graphics.html#',r.render_tables(tables,'YGPA-030'))

    def test_save_skip_and_tamper_preserve_original(self):
        tables,_=sample();obj=g.graphic_objects(tables)[0]
        blocks=obj['text_records']+[tables[0]['cells'][1]['paragraphs'][0]['text_records'][0]]
        row={'doc_id':'YGPA-030','source_url':'https://www.ygpa.or.kr/synthetic'}
        raw=b'synthetic';text=b'original'
        block_bytes=json.dumps(blocks).encode()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);snapshot=root/'data/raw/YGPA-030/snapshot'
            processed=root/'data/processed/YGPA-030/snapshot';processed.mkdir(parents=True)
            doc={**row,'document_version':r.sha(raw),'blocks_sha256':r.sha(block_bytes),'text_sha256':r.sha(text),'extraction_details':{'table_count':1}}
            (processed/'document.json').write_text(json.dumps(doc),encoding='utf8')
            (processed/'document.txt').write_bytes(text);(processed/'blocks.json').write_bytes(block_bytes)
            def assets(raw,objects):
                for o in objects:o['image_refs']=[]
                return [],{}
            with patch.object(r,'validate_source',return_value=(snapshot,{},raw)),patch.object(r,'read_tables',return_value=tables),patch.object(g,'collect_assets',side_effect=assets):
                state,out,v=g.restore(root,row,{})
                self.assertEqual(state,'saved');self.assertEqual(g.restore(root,row,{})[0],'existing')
                self.assertFalse(v['index_approved'])
                self.assertEqual((processed/'document.txt').read_bytes(),text)
                (out/'graphics.json').write_text('broken')
                with self.assertRaises(ValueError):g.restore(root,row,{})

if __name__=='__main__':unittest.main()
