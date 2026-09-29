"""Synthetic, bounded glyph correction tests; no FAQ data."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import correct_symbols_032 as c

class SymbolTests(unittest.TestCase):
    def sample(self):return '앞 문장 \uf000'+c.TITLE+'\uf000 뒤 문장'
    def test_only_two_characters_change(self):
        before=self.sample();after,changes=c.correct_pair(before)
        self.assertEqual(len(before),len(after));self.assertEqual(sum(a!=b for a,b in zip(before,after)),2)
        self.assertEqual([x['after'] for x in changes],['『','』'])
    def test_wrong_count_or_context_is_rejected(self):
        for text in ('\uf000다른 이름\uf000',self.sample()+'\uf000',self.sample().replace('\uf000','')):
            with self.assertRaises(ValueError):c.correct_pair(text)
    def test_page_guard_and_input_preservation(self):
        blocks=[{'locator':{'kind':'pdf_page','page_number':9},'text':self.sample()}]
        corrected,changes=c.correct_blocks(blocks)
        self.assertEqual(blocks[0]['text'],self.sample());self.assertNotEqual(corrected,blocks)
        blocks[0]['locator']['page_number']=10
        with self.assertRaises(ValueError):c.correct_blocks(blocks)
    def test_preview_and_source_version_guard(self):
        with patch.object(c,'select_targets',return_value=({},[{}])),patch.object(c,'correct') as correct:
            c.main([]);correct.assert_not_called()
        with patch.object(c,'validate_source',return_value=(Path('snap'),{},b'another version')):
            with self.assertRaisesRegex(ValueError,'원본 버전'):c.correct(Path('.'),{'doc_id':c.DOC_ID},{})

if __name__=='__main__':unittest.main()
