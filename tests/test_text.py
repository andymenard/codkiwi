import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codkiwi.text import dialogue_pages, story_pages
class TextTests(unittest.TestCase):
    def test_emphasis_stays_balanced_across_pages(self):
        raw='Before `one two three four five six seven eight nine ten` after.'
        pages=dialogue_pages(raw,20)
        self.assertGreater(len(pages),1)
        self.assertTrue(all(p.count('`')%2==0 for p in pages))
        self.assertEqual(' '.join(' '.join(pages).replace('`','').split()),raw.replace('`',''))
    def test_short_line_unchanged(self):
        self.assertEqual(dialogue_pages('Hello, `Detective`.'),['Hello, `Detective`.'])
    def test_long_word_is_not_dropped(self):
        self.assertEqual(dialogue_pages('abcdefghijk',3),['abcdefghijk'])
    def test_empty(self):self.assertEqual(dialogue_pages(''),[''])
    def test_original_docks_narration_stays_in_one_bubble(self):
        text='A little while later, you stand on the docks with Natara. An EMT takes Ashley away, a blanket draped over her shoulders.'
        self.assertEqual(dialogue_pages(text,109)[-1],'her shoulders.')
        for small in (False, True):
            self.assertEqual(story_pages(dict(text=text,speaker=''),small),[text])
    def test_narration_has_no_replacement_character_cutoff(self):
        text='A `long narration` with intact emphasis. ' * 10
        self.assertEqual(story_pages(dict(text=text,speaker=''),True),[text])
        self.assertGreater(len(story_pages(dict(text=text,speaker='Mal'),True)),1)
if __name__=='__main__':unittest.main(verbosity=2)
