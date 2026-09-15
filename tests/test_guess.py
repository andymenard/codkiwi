"""Typed answers, played through a real puzzle at several casings.

The scripts store their answers in sentence case and compare them to what the
player typed. Comparing raw meant 'grandmaster' failed where 'Grandmaster' passed,
which is not how the game read to anyone playing it.

    python3 tests/test_guess.py path/to/Volume_6.exp
"""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codkiwi import StoryRuntime, parse_kiwi                       # noqa: E402
from codkiwi.engine import fold                                    # noqa: E402
from codkiwi.exp import unpack                                     # noqa: E402

SOURCE = Path(sys.argv.pop()) if len(sys.argv) > 1 and sys.argv[-1].endswith('.exp') else None

## Volume 6 chapter four asks the player to unscramble 'Mad Stranger'. The script
## stores one spelling, 'Grandmaster', and rewards a correct answer immediately
## with the Detective Score notice.
CHAPTER, ANSWER = 25008, 'Grandmaster'


class Folding(unittest.TestCase):
    def test_it_ignores_case_both_ways(self):
        for typed in ('Grandmaster', 'grandmaster', 'GRANDMASTER', 'GrandMaster'):
            self.assertEqual(fold(typed), fold('Grandmaster'), typed)

    def test_it_is_not_fooled_by_a_different_word(self):
        self.assertNotEqual(fold('grandmasters'), fold('Grandmaster'))
        self.assertNotEqual(fold('grand master'), fold('Grandmaster'))


@unittest.skipUnless(SOURCE, 'Pass Volume_6.exp as the last argument.')
class Puzzle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        resources = unpack(SOURCE.read_bytes())
        cls.resources = resources
        cls.programs = {k: parse_kiwi(v) for k, v in resources.items() if v.startswith(b'kiwi')}

    def play(self, typed, limit=400):
        """Answer the chapter's input field with `typed`; did the score go up?"""
        r = StoryRuntime(self.programs, self.resources, random_fn=lambda: 123456789)
        r.reset(); r.load(25001); r.run()
        r.properties['0:1001'] = CHAPTER - 25001
        r.load(CHAPTER); r.run()
        answered = False
        for _ in range(limit):
            ui = r.ui
            if ui.get('kind') in ('ended', 'error'):
                break
            if answered:
                # The reward lands in the events of the lines just after.
                for event in r.effects.events:
                    if event.get('type') == 'dialog-aux-text' and 'Score Up' in event.get('text', ''):
                        return True
            asking = ui.get('kind') == 'input'
            r.effects.events = []
            if ui.get('timed'):
                r.tick(ui['remaining'] + 1)
            elif asking:
                r.respond(typed); answered = True
            else:
                enabled = [c for c in ui.get('choices', []) if c.get('enabled')]
                r.respond(enabled[0]['value'] if enabled else 0)
        return False

    def test_the_spelling_the_script_stores_is_accepted(self):
        self.assertTrue(self.play(ANSWER))

    def test_every_casing_of_it_is_accepted(self):
        for typed in (ANSWER.lower(), ANSWER.upper(), 'GrandMaster'):
            self.assertTrue(self.play(typed), typed)

    def test_a_wrong_answer_is_still_wrong(self):
        for typed in ('chessmaster', 'mad stranger', ''):
            self.assertFalse(self.play(typed), typed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
