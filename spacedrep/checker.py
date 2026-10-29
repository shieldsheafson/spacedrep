"""Checking typed answers, including German article correctness."""

import re
import unicodedata
from dataclasses import dataclass, field

from .grammar import compare_structure, parse_phrase

ARTICLES = ("der", "die", "das")

# What people type when they don't have umlaut keys.
UMLAUT_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


@dataclass
class Result:
    correct: bool
    feedback: str = ""
    notes: list[str] = field(default_factory=list)  # hints shown even when correct
    # article / separable prefix / preposition / case mistake on an otherwise known word
    grammar_error: bool = False


def split_article(text: str) -> tuple[str | None, str]:
    """'der Hund' -> ('der', 'Hund'); 'laufen' -> (None, 'laufen')."""
    text = _clean(text)
    parts = text.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() in ARTICLES:
        return parts[0].lower(), parts[1].strip()
    return None, text


def english_alternatives(english: str) -> list[str]:
    return [a.strip() for a in re.split(r"[;,]", english) if a.strip()]


def check_german(answer: str, article: str | None, word: str) -> Result:
    """Check an answer typed in German against the expected article + word."""
    expected_full = f"{article} {word}" if article else word
    answer = _clean(answer)
    if not answer:
        return Result(False, f"Answer: {expected_full}")

    if article is None:
        return _check_phrase(answer, word)

    ans_article, ans_word = split_article(answer)
    word_ok, notes = _compare_german_word(ans_word, word)

    # Noun: both the article and the word must be right.
    if ans_article is None:
        if word_ok:
            return Result(False, f"Missing the article — it's {expected_full}.",
                          notes, grammar_error=True)
        return Result(False, _wrong_word(ans_word, word, expected_full), grammar_error=True)

    if ans_article != article:
        if word_ok:
            return Result(False, f"Right word, wrong article: it's {article.upper()} {word}, "
                                 f"not {ans_article} {word}.", notes, grammar_error=True)
        return Result(False, f"Wrong article and word. Answer: {expected_full}",
                      grammar_error=True)

    if not word_ok:
        return Result(False, "Article is right, but " + _wrong_word(ans_word, word, expected_full))

    return Result(True, notes=notes)


def _check_phrase(answer: str, expected: str) -> Result:
    """Non-nouns: plain words, separable verbs, verbs with objects/prepositions."""
    card, ans = parse_phrase(expected), parse_phrase(answer)
    word_ok, notes = _compare_german_word(ans.verb_plain, card.verb_plain)
    if not word_ok:
        # Someone put an article in front of a non-noun.
        art, rest = split_article(ans.verb_plain)
        if art and _compare_german_word(rest, card.verb_plain)[0]:
            ans.verb, word_ok = rest, True
            notes.append(f"'{card.verb_plain}' doesn't take an article.")
    if not word_ok:
        msg = _wrong_word(ans.verb_plain, card.verb_plain, expected)
        return Result(False, msg[:1].upper() + msg[1:])

    issues = []
    # Separability is only checked when the answer marks a split with |.
    if ans.sep_prefix is not None and ans.sep_prefix.lower() != (card.sep_prefix or "").lower():
        issues.append(f"It separates as {card.verb.split(' ')[-1]}." if card.sep_prefix
                      else f"'{card.verb_plain}' isn't separable.")
    if card.has_structure:
        issues += compare_structure(card, ans)
    if issues:
        return Result(False, " ".join(issues) + f"  Answer: {expected}", notes, grammar_error=True)
    return Result(True, notes=notes)


def check_english(answer: str, english: str) -> Result:
    """Check an English answer against the card's alternatives."""
    alts = english_alternatives(english)
    ans = _norm_en(answer)
    if not ans:
        return Result(False, f"Answer: {english}")
    for alt in alts:
        if ans == _norm_en(alt):
            return Result(True, notes=_other_meanings(alts, alt))
    for alt in alts:
        target = _norm_en(alt)
        if _distance(ans, target) <= _typo_allowance(target):
            return Result(True, notes=[f"Accepted — spelled '{alt}'."] + _other_meanings(alts, alt))
    return Result(False, f"Answer: {english}")


# --- helpers -----------------------------------------------------------------

def _clean(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", " ", s).strip().strip(".!?")


def _same(a: str, b: str) -> bool:
    return _clean(a).lower() == _clean(b).lower()


def _compare_german_word(given: str, expected: str) -> tuple[bool, list[str]]:
    given, expected = _clean(given), _clean(expected)
    if given == expected:
        return True, []
    if given.lower() == expected.lower():
        return True, [f"Watch the capitalisation: {expected}"]
    if given.lower().translate(UMLAUT_FOLD) == expected.lower().translate(UMLAUT_FOLD):
        return True, [f"Spelled with umlauts/ß: {expected}"]
    return False, []


def _wrong_word(given: str, expected: str, expected_full: str) -> str:
    g = given.lower().translate(UMLAUT_FOLD)
    e = expected.lower().translate(UMLAUT_FOLD)
    if given and _distance(g, e) <= _typo_allowance(e):
        return f"close — check the spelling: {expected_full}"
    return f"the answer is {expected_full}"


def _norm_en(s: str) -> str:
    s = _clean(s).lower()
    s = re.sub(r"\(.*?\)", "", s)           # drop "(informal)" style notes
    s = re.sub(r"[^\w\s'-]", " ", s)
    # 'to view sth.' == 'view' == 'view something'
    s = re.sub(r"\b(sth|sb|something|someone|somebody|oneself|one's|sb's|sth's)\b", "", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(to|the|a|an) ", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


def _other_meanings(alts: list[str], used: str) -> list[str]:
    others = [a for a in alts if a != used]
    return [f"Also: {', '.join(others)}"] if others else []


def _typo_allowance(target: str) -> int:
    if len(target) >= 9:
        return 2
    if len(target) >= 5:
        return 1
    return 0


def _distance(a: str, b: str) -> int:
    """Edit distance where swapping two neighbouring letters counts as one typo."""
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]
