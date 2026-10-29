import unittest
from datetime import date, timedelta

from spacedrep.checker import check_english, check_german, split_article
from spacedrep.cli import parse_german
from spacedrep.grammar import parse_phrase, separable_candidate
from spacedrep.scheduler import AGAIN, EASY, GOOD, HARD, Schedule, review
from spacedrep.store import Store

TODAY = date(2026, 10, 29)


class GermanTests(unittest.TestCase):
    def test_correct_noun(self):
        self.assertTrue(check_german("die Katze", "die", "Katze").correct)

    def test_wrong_article(self):
        r = check_german("der Katze", "die", "Katze")
        self.assertFalse(r.correct)
        self.assertTrue(r.grammar_error)
        self.assertIn("wrong article", r.feedback)

    def test_missing_article(self):
        r = check_german("Katze", "die", "Katze")
        self.assertFalse(r.correct)
        self.assertTrue(r.grammar_error)
        self.assertIn("Missing", r.feedback)

    def test_article_case_insensitive(self):
        self.assertTrue(check_german("Die Katze", "die", "Katze").correct)

    def test_lowercase_noun_accepted_with_note(self):
        r = check_german("die katze", "die", "Katze")
        self.assertTrue(r.correct)
        self.assertTrue(any("capitalisation" in n for n in r.notes))

    def test_umlaut_substitute(self):
        r = check_german("das Maedchen", "das", "Mädchen")
        self.assertTrue(r.correct)
        self.assertTrue(r.notes)
        self.assertTrue(check_german("die Strasse", "die", "Straße").correct)

    def test_typo_is_wrong_but_flagged_close(self):
        r = check_german("die Zeitnug", "die", "Zeitung")
        self.assertFalse(r.correct)
        self.assertFalse(r.grammar_error)
        self.assertIn("close", r.feedback)

    def test_wrong_word(self):
        self.assertFalse(check_german("der Hund", "die", "Katze").correct)

    def test_non_noun(self):
        self.assertTrue(check_german("laufen", None, "laufen").correct)
        self.assertFalse(check_german("gehen", None, "laufen").correct)

    def test_non_noun_starting_with_article_word(self):
        # e.g. a phrase card "das heißt" with no article stored
        self.assertTrue(check_german("das heißt", None, "das heißt").correct)

    def test_blank(self):
        self.assertFalse(check_german("", "der", "Hund").correct)

    def test_split_article(self):
        self.assertEqual(split_article("  der   Hund "), ("der", "Hund"))
        self.assertEqual(split_article("laufen"), (None, "laufen"))


def ok(answer, card):
    return check_german(answer, None, card).correct


class VerbTests(unittest.TestCase):
    def test_object_case(self):
        self.assertTrue(ok("etw betrachten", "etw (acc) betrachten"))
        self.assertTrue(ok("etw (akk) betrachten", "etw (acc) betrachten"))
        self.assertFalse(ok("betrachten", "etw (acc) betrachten"))
        self.assertTrue(ok("jdm helfen", "jdm helfen"))
        r = check_german("jdn helfen", None, "jdm helfen")
        self.assertFalse(r.correct)
        self.assertTrue(r.grammar_error)
        self.assertIn("DATIVE", r.feedback)

    def test_preposition_and_case(self):
        card = "auf jdn/etw (acc) warten"
        self.assertTrue(ok("auf jdn warten", card))
        self.assertTrue(ok("auf etw (acc) warten", card))
        self.assertTrue(ok("warten auf + Akk", card))
        self.assertIn("Which case", check_german("auf etw warten", None, card).feedback)
        self.assertIn("Wrong case", check_german("auf jdm warten", None, card).feedback)
        self.assertIn("Wrong preposition", check_german("für jdn warten", None, card).feedback)
        self.assertIn("Missing the preposition", check_german("warten", None, card).feedback)

    def test_fixed_case_prepositions_imply_case(self):
        self.assertTrue(ok("mit jdm sprechen", "mit jdm sprechen"))
        self.assertTrue(ok("mit etw sprechen", "mit jdm sprechen"))
        self.assertEqual(parse_phrase("für etw danken").slots[0].case, "acc")

    def test_object_order_doesnt_matter(self):
        self.assertTrue(ok("etw jdm geben", "jdm etw geben"))
        self.assertFalse(ok("etw geben", "jdm etw geben"))

    def test_reflexive(self):
        card = "sich (acc) für etw interessieren"
        self.assertTrue(ok("sich für etw interessieren", card))
        self.assertIn("sich", check_german("für etw interessieren", None, card).feedback)
        self.assertFalse(ok("sich etw vorstellen", "sich (dat) etw vorstellen"))
        self.assertTrue(ok("sich (D) etw vorstellen", "sich (dat) etw vorstellen"))

    def test_separable(self):
        self.assertEqual(parse_phrase("jdn an|rufen").sep_prefix, "an")
        self.assertTrue(ok("jdn anrufen", "jdn an|rufen"))      # marking is optional
        self.assertTrue(ok("jdn an|rufen", "jdn an|rufen"))
        self.assertFalse(ok("jdn anr|ufen", "jdn an|rufen"))
        r = check_german("über|setzen", None, "übersetzen")
        self.assertFalse(r.correct)
        self.assertIn("isn't separable", r.feedback)

    def test_wrong_verb(self):
        self.assertFalse(ok("auf jdn hoffen", "auf jdn/etw (acc) warten"))

    def test_plain_cards_ignore_extra_structure(self):
        self.assertTrue(ok("auf jdn warten", "warten"))

    def test_separable_candidate(self):
        self.assertEqual(separable_candidate("anrufen"), "an")
        self.assertEqual(separable_candidate("übersetzen"), "über")
        self.assertIsNone(separable_candidate("bekommen"))
        self.assertIsNone(separable_candidate("an|rufen"))

    def test_parse_card_german(self):
        self.assertEqual(parse_german("die katze"), ("die", "Katze"))
        self.assertEqual(parse_german("das Licht an|machen"), (None, "das Licht an|machen"))
        self.assertEqual(parse_german("die Vereinigten Staaten"), ("die", "Vereinigten Staaten"))
        self.assertEqual(parse_german("etw (acc) betrachten"), (None, "etw (acc) betrachten"))


class EnglishTests(unittest.TestCase):
    def test_alternatives(self):
        self.assertTrue(check_english("hound", "dog; hound").correct)
        self.assertTrue(check_english("Dog", "dog; hound").correct)

    def test_ignores_to_and_the(self):
        self.assertTrue(check_english("run", "to run; to walk").correct)
        self.assertTrue(check_english("to walk", "to run, to walk").correct)
        self.assertTrue(check_english("the table", "table").correct)

    def test_ignores_sth_sb(self):
        self.assertTrue(check_english("view", "to view sth.").correct)
        self.assertTrue(check_english("to view something", "to view sth.").correct)
        self.assertTrue(check_english("wait for", "to wait for sb/sth").correct)

    def test_typo_accepted(self):
        r = check_english("newpaper", "newspaper")
        self.assertTrue(r.correct)
        self.assertTrue(r.notes)

    def test_short_words_need_exact(self):
        self.assertFalse(check_english("bat", "cat").correct)

    def test_wrong(self):
        self.assertFalse(check_english("chair", "table").correct)


class SchedulerTests(unittest.TestCase):
    def test_intervals_grow(self):
        s = Schedule(due=TODAY)
        days = []
        for _ in range(5):
            s = review(s, GOOD, TODAY)
            days.append(s.interval)
        self.assertEqual(days[:2], [1, 3])
        self.assertTrue(all(b > a for a, b in zip(days, days[1:])))

    def test_fail_resets(self):
        s = Schedule(ease=2.5, interval=20, reps=4, due=TODAY)
        s = review(s, AGAIN, TODAY)
        self.assertEqual((s.reps, s.interval, s.lapses, s.due), (0, 0, 1, TODAY))
        self.assertLess(s.ease, 2.5)

    def test_hard_shorter_than_easy(self):
        base = Schedule(ease=2.5, interval=10, reps=3, due=TODAY)
        self.assertLess(review(base, HARD, TODAY).interval, review(base, EASY, TODAY).interval)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_card_creates_both_directions(self):
        c = self.store.add_card("der", "Hund", "dog", today=TODAY)
        due = self.store.due_reviews(TODAY)
        self.assertEqual({d.direction for d in due if d.card.id == c.id}, {"de_en", "en_de"})
        self.assertTrue(all(d.is_new for d in due))

    def test_reviewed_card_not_due(self):
        c = self.store.add_card("der", "Hund", "dog", today=TODAY)
        s = review(self.store.schedules(c.id)["de_en"], GOOD, TODAY)
        self.store.save_review(c.id, "de_en", s, TODAY)
        due = self.store.due_reviews(TODAY)
        self.assertEqual([d.direction for d in due], ["en_de"])
        self.assertEqual(len(self.store.due_reviews(TODAY + timedelta(days=1))), 2)

    def test_new_limit(self):
        for i in range(5):
            self.store.add_card(None, f"Wort{i}", f"word{i}", today=TODAY)
        due = self.store.due_reviews(TODAY, new_limit=2)
        self.assertEqual(len({d.card.id for d in due}), 2)
        self.assertEqual(len(due), 4)

    def test_delete_cascades(self):
        c = self.store.add_card("die", "Katze", "cat", today=TODAY)
        self.store.delete_card(c.id)
        self.assertEqual(self.store.due_reviews(TODAY), [])

    def test_article_misses(self):
        c = self.store.add_card("die", "Katze", "cat", today=TODAY)
        self.store.record_grammar_miss(c.id)
        self.assertEqual(self.store.stats(TODAY)["grammar_trouble"][0].grammar_misses, 1)


if __name__ == "__main__":
    unittest.main()
