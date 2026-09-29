"""Synthetic PDF/page fixtures; no official documents or FAQ evaluation content."""
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib
from pypdf import PdfWriter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import preserve_pdf_pages_031 as p


def pdf(count=29):
    writer=PdfWriter()
    for _ in range(count):writer.add_blank_page(width=100,height=200)
    stream=io.BytesIO();writer.write(stream);return stream.getvalue()


def png():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\xff\xff'))+chunk(b'IEND',b'')


def blocks():
    return [{'locator':{'kind':'pdf_page','page_number':n},'text':f'page {n} <sample>'} for n in range(1,30)]


class PageTests(unittest.TestCase):
    def test_page_numbers_and_original_block_indices(self):
        pages=p.describe_pages(pdf(),blocks())
        self.assertEqual([v['page_number'] for v in pages],[26,27,28,29])
        self.assertEqual([v['source_block_indices'] for v in pages],[[25],[26],[27],[28]])
        for raw,bb in ((pdf(28),blocks()),(pdf(),blocks()[:-1])):
            with self.assertRaises(ValueError):p.describe_pages(raw,bb)

    def test_renderer_args_preserve_full_page_and_no_shell(self):
        with tempfile.TemporaryDirectory() as folder:
            prefix=Path(folder)/'page-026';prefix.with_suffix('.png').write_bytes(png())
            with patch.object(p,'run_process',return_value=subprocess.CompletedProcess([],0,b'',b'')) as run:
                p.render_page('pdftoppm','source with spaces.pdf',26,prefix)
            args=run.call_args.args[0]
            self.assertEqual(args[1:5],['-f','26','-l','26'])
            self.assertIn('-singlefile',args)
            self.assertNotIn('-cropbox',args)
            self.assertIn('source with spaces.pdf',args)

    def test_png_validation_and_html_escaping(self):
        self.assertEqual(p.png_dimensions(png()),(1,1))
        with self.assertRaises(ValueError):p.png_dimensions(b'not png')
        pages=p.describe_pages(pdf(),blocks())
        for v in pages:v.update(width_pixels=1,height_pixels=1)
        page=p.render_review(pages)
        self.assertIn('&lt;sample&gt;',page)
        self.assertIn('OCR',page)
        self.assertEqual(page.count('<img '),4)

    def fixture(self,root):
        snap=root/'data/raw/YGPA-031/snapshot';dest=root/'data/processed/YGPA-031/snapshot';dest.mkdir(parents=True)
        row={'doc_id':'YGPA-031','source_url':'https://www.ygpa.or.kr/synthetic'}
        raw=pdf();bb=json.dumps(blocks()).encode();txt=b'preserve me'
        doc={**row,'document_version':p.sha(raw),'blocks_sha256':p.sha(bb),'text_sha256':p.sha(txt)}
        (dest/'blocks.json').write_bytes(bb);(dest/'document.txt').write_bytes(txt);(dest/'document.json').write_text(json.dumps(doc),encoding='utf8')
        return snap,dest,row,raw

    def test_save_skip_tamper_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);snap,dest,row,raw=self.fixture(root)
            before={x.name:x.read_bytes() for x in dest.iterdir()}
            with patch.object(p,'validate_source',return_value=(snap,{},raw)),patch.object(p,'resolve_renderer',return_value='renderer'),patch.object(p,'run_process',return_value=subprocess.CompletedProcess([],0,b'',b'version synthetic\n')),patch.object(p,'render_page',return_value=(png(),'')) as render:
                state,out,v=p.preserve(root,row,{})
                self.assertEqual(state,'saved');self.assertEqual(render.call_count,4)
                self.assertEqual([c.args[2] for c in render.call_args_list],[26,27,28,29])
                self.assertFalse(v['index_approved']);self.assertEqual(v['ocr_status'],'not_performed')
                self.assertEqual(p.preserve(root,row,{})[0],'existing');self.assertEqual(render.call_count,4)
                for name,data in before.items():self.assertEqual((dest/name).read_bytes(),data)
                (out/'page-026.png').write_bytes(b'tampered')
                with self.assertRaises(ValueError):p.preserve(root,row,{})

    def test_render_failure_leaves_no_partial_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);snap,dest,row,raw=self.fixture(root)
            with patch.object(p,'validate_source',return_value=(snap,{},raw)),patch.object(p,'resolve_renderer',return_value='renderer'),patch.object(p,'run_process',return_value=subprocess.CompletedProcess([],0,b'version',b'')),patch.object(p,'render_page',side_effect=ValueError('failed page')):
                with self.assertRaises(ValueError):p.preserve(root,row,{})
            self.assertFalse((dest/p.VERSION).exists())

    def test_preview_does_not_render(self):
        with patch.object(p,'select_targets',return_value=({},[{}])),patch.object(p,'preserve') as preserve:
            p.main([]);preserve.assert_not_called()
        with patch.object(p.shutil,'which',return_value=None):
            with self.assertRaises(ValueError):p.resolve_renderer()


if __name__=='__main__':unittest.main()
