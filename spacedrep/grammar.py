"""Parsing German verb phrases written in dictionary style.

Examples of what can be parsed:
    an|rufen                    separable verb (| marks the split)
    jdn an|rufen                accusative object + separable verb
    jdm helfen                  dative object (jdm = dative)
    etw (acc) betrachten        object with explicit case
    auf jdn/etw (acc) warten    verb + preposition + case
    sich (acc) für etw interessieren
    warten auf + Akk            the other common dictionary order

Rules:
- jdn/jdm/jds (also jmdn, jemanden, …) give the case on their own.
- Prepositions that only take one case (mit, für, wegen, …) give the case on their own.
- Two-way prepositions (an, auf, in, über, …) need a case marker to be tested.
- A bare 'etw' or 'sich' with no marker counts as accusative.
"""

import re
from dataclasses import dataclass, field

TWO_WAY = {"an", "auf", "hinter", "in", "neben", "über", "unter", "vor", "zwischen"}
FIXED_CASE = {
    **dict.fromkeys(["aus", "bei", "mit", "nach", "seit", "von", "zu", "gegenüber", "außer"], "dat"),
    **dict.fromkeys(["durch", "für", "gegen", "ohne", "um", "bis"], "acc"),
    **dict.fromkeys(["wegen", "trotz", "während", "statt", "anstatt"], "gen"),
}
PREPOSITIONS = TWO_WAY | set(FIXED_CASE)

OBJECT_WORDS = {
    "jdn": "acc", "jmdn": "acc", "jemanden": "acc",
    "jdm": "dat", "jmdm": "dat", "jemandem": "dat",
    "jds": "gen", "jmds": "gen", "jemandes": "gen",
    "etw": None, "etwas": None,
}
CASE_WORDS = {
    "acc": "acc", "akk": "acc", "accusative": "acc", "akkusativ": "acc",
    "dat": "dat", "dative": "dat", "dativ": "dat",
    "gen": "gen", "genitive": "gen", "genitiv": "gen",
}
CASE_LETTERS = {"a": "acc", "d": "dat", "g": "gen"}  # only inside ( ) or after +
CASE_NAMES = {"acc": "accusative", "dat": "dative", "gen": "genitive"}
CASE_OBJECT = {"acc": "jdn/etw", "dat": "jdm", "gen": "jds"}

# Prefixes that are (or can be) separable, longest first.
SEPARABLE_PREFIXES = sorted([
    "ab", "an", "auf", "aus", "bei", "dar", "ein", "fest", "fort", "her", "hin", "los", "mit",
    "nach", "vor", "weg", "weiter", "zu", "zurück", "zusammen", "vorbei", "heraus", "herein",
    "hinaus", "herunter", "hinauf", "entgegen",
    # can go either way depending on the verb
    "durch", "hinter", "über", "unter", "um", "voll", "wider", "wieder",
], key=len, reverse=True)


@dataclass
class Slot:
    """An object of the verb, optionally after a preposition."""
    prep: str | None
    case: str | None   # None = not stated (two-way preposition without a marker)
    has_object: bool = False

    def describe(self) -> str:
        if self.prep:
            return f"{self.prep} + {self.case.upper()}" if self.case else self.prep
        return f"{CASE_OBJECT[self.case]} ({self.case})"


@dataclass
class Phrase:
    verb: str = ""                 # e.g. "an|rufen"; may be several words ("Rad fahren")
    reflexive: bool = False
    reflexive_case: str | None = None
    slots: list[Slot] = field(default_factory=list)

    @property
    def verb_plain(self) -> str:
        return self.verb.replace("|", "")

    @property
    def sep_prefix(self) -> str | None:
        last = self.verb.split(" ")[-1] if self.verb else ""
        return last.split("|")[0] if "|" in last else None

    @property
    def has_structure(self) -> bool:
        return self.reflexive or bool(self.slots)


def parse_phrase(text: str) -> Phrase:
    text = re.sub(r"([()+])", r" \1 ", text)
    ph = Phrase()
    verb_words = []
    last = None          # what a case marker would attach to: "sich" or a Slot
    open_prep = None     # preposition slot still waiting for its object word
    in_paren = after_plus = False

    for tok in text.split():
        low = tok.lower().strip(".,;:")
        if low == "(":
            in_paren = True
            continue
        if low == ")":
            in_paren = False
            continue
        if low == "+":
            after_plus = True
            continue
        marker = CASE_WORDS.get(low) or ((in_paren or after_plus) and CASE_LETTERS.get(low))
        after_plus = False
        if marker:
            if last == "sich":
                ph.reflexive_case = marker
            elif isinstance(last, Slot):
                last.case = marker
            continue
        if not low:
            continue
        if low == "sich":
            ph.reflexive, last, open_prep = True, "sich", None
            continue
        if low in PREPOSITIONS:
            slot = Slot(low, FIXED_CASE.get(low))
            ph.slots.append(slot)
            last = open_prep = slot
            continue
        parts = low.split("/")
        if all(p in OBJECT_WORDS for p in parts):
            case = next((OBJECT_WORDS[p] for p in parts if OBJECT_WORDS[p]), None)
            if open_prep:
                open_prep.has_object = True
                if case:
                    open_prep.case = case
                last = open_prep
            else:
                last = Slot(None, case, has_object=True)
                ph.slots.append(last)
            open_prep = None
            continue
        verb_words.append(tok.strip(".,;:"))
        last = open_prep = None

    for s in ph.slots:
        if s.prep is None and s.case is None:
            s.case = "acc"          # bare 'etw' = accusative
    if ph.reflexive and ph.reflexive_case is None:
        ph.reflexive_case = "acc"
    ph.verb = " ".join(verb_words)
    return ph


def separable_candidate(verb: str) -> str | None:
    """If an unmarked verb starts with a possibly-separable prefix, return it."""
    if not verb or " " in verb or "|" in verb or not verb.islower() or not verb.endswith("n"):
        return None
    for p in SEPARABLE_PREFIXES:
        if verb.startswith(p) and len(verb) - len(p) >= 4:
            return p
    return None


def compare_structure(card: Phrase, ans: Phrase) -> list[str]:
    """Problems with sich / objects / prepositions / cases in an answer."""
    issues = []
    if card.reflexive and not ans.reflexive:
        issues.append("Missing 'sich' — it's reflexive.")
    elif ans.reflexive and not card.reflexive:
        issues.append("It's not reflexive — no 'sich'.")
    elif card.reflexive and card.reflexive_case != ans.reflexive_case:
        issues.append(f"Wrong case for sich: it's sich ({card.reflexive_case.upper()}).")

    remaining = list(ans.slots)
    pairs, unmatched = [], []
    # Match slots with the same preposition, preferring the same case too
    # (so 'etw jdm geben' matches 'jdm etw geben').
    for want_case in (True, False):
        for cs in [c for c in card.slots if not any(c is p[0] for p in pairs)]:
            m = next((a for a in remaining if a.prep == cs.prep and (not want_case or a.case == cs.case)), None)
            if m:
                remaining.remove(m)
                pairs.append((cs, m))
    unmatched = [c for c in card.slots if not any(c is p[0] for p in pairs)]

    for cs, a in pairs:
        if cs.case is None or cs.case == a.case:
            continue
        if cs.prep and a.case is None:
            issues.append(f"Which case? It's {cs.prep} + {cs.case.upper()}.")
        elif cs.prep:
            issues.append(f"Wrong case: it's {cs.prep} + {cs.case.upper()}, not {a.case}.")
        else:
            issues.append(f"Wrong case: the object is {CASE_NAMES[cs.case].upper()} ({CASE_OBJECT[cs.case]}).")

    for cs in unmatched:
        if cs.prep:
            other = next((a for a in remaining if a.prep), None)
            if other:
                remaining.remove(other)
                issues.append(f"Wrong preposition: it's {cs.describe().upper()}, not {other.prep}.")
            else:
                issues.append(f"Missing the preposition: {cs.describe()}.")
        else:
            issues.append(f"Missing the {CASE_NAMES[cs.case]} object ({CASE_OBJECT[cs.case]}).")

    for a in remaining:
        issues.append(f"No '{a.prep}' needed." if a.prep else "No extra object needed.")
    return issues
