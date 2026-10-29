"""Terminal interface."""

import argparse
import csv
import os
import random
import sys
from datetime import date
from pathlib import Path

try:
    import readline  # noqa: F401  (gives arrow-key editing in input())
except ImportError:
    pass

from . import checker
from .grammar import TWO_WAY, parse_phrase, separable_candidate
from .scheduler import AGAIN, EASY, GOOD, HARD, review
from .store import Card, Store, default_db_path

# --- output helpers ----------------------------------------------------------

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code):
    return (lambda s: f"\033[{code}m{s}\033[0m") if USE_COLOR else (lambda s: s)


bold, dim, green, red, yellow, cyan = _c(1), _c(2), _c(32), _c(31), _c(33), _c(36)

ARROW = {"de_en": "DE → EN", "en_de": "EN → DE"}


class Quit(Exception):
    pass


def ask(prompt: str = "> ") -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        raise Quit


def yes(prompt: str) -> bool:
    return ask(prompt + " [y/N] ").strip().lower() in ("y", "yes")


# --- review session ----------------------------------------------------------

def review_session(store: Store, today: date, new_limit: int):
    queue = store.due_reviews(today, new_limit)
    if not queue:
        print(green("Nothing due right now. Add some words or come back later."))
        return
    random.shuffle(queue)
    queue = _spread(queue)

    print(bold(f"\n{len(queue)} reviews. Type your answer and press Enter."))
    print(dim("Leave blank if you don't know. Type :q to stop. "
              "No umlaut keys? ae/oe/ue/ss are accepted.\n"))

    seen = right = 0
    try:
        while queue:
            item = queue.pop(0)
            card = item.card
            print(dim(f"[{len(queue) + 1} left]  {ARROW[item.direction]}") +
                  (yellow("  new") if item.is_new else ""))

            if item.direction == "de_en":
                print("  " + bold(card.german_full))
                answer = ask("  English: ")
                if answer.strip() == ":q":
                    break
                result = checker.check_english(answer, card.english)
            else:
                hint = dim(f"  ({_hint(card)})") if _hint(card) else ""
                print("  " + bold(card.english) + hint)
                answer = ask("  German:  ")
                if answer.strip() == ":q":
                    break
                result = checker.check_german(answer, card.article, card.german)

            grade = _grade(result, card, item.direction)
            seen += 1
            if grade == AGAIN:
                if result.grammar_error:
                    store.record_grammar_miss(card.id)
            else:
                right += 1

            item.schedule = review(item.schedule, grade, today)
            store.save_review(card.id, item.direction, item.schedule, today)
            if grade == AGAIN:
                # Bring it back a few cards later in this session.
                queue.insert(min(len(queue), 3), item)
            print()
    except Quit:
        pass

    if seen:
        print(bold(f"Session done: {right}/{seen} correct."))
        if queue:
            print(dim(f"{len(queue)} reviews left for later."))


def _hint(card: Card) -> str:
    """What the German answer needs to include, without giving it away."""
    if card.article:
        return "noun — include der/die/das"
    ph = parse_phrase(card.german)
    parts = []
    if ph.reflexive:
        parts.append("sich")
    if any(s.prep is None for s in ph.slots):
        parts.append("object (jdn/jdm/etw)")
    if any(s.prep for s in ph.slots):
        parts.append("preposition + case")
    return "include " + ", ".join(parts) if parts else ""


def _grade(result, card: Card, direction: str) -> int:
    answer_line = (card.english if direction == "de_en" else card.german_full)
    if result.correct:
        print("  " + green("✓ Correct") + dim(f"  — {answer_line}"))
        for n in result.notes:
            print("  " + yellow(n))
        if card.notes:
            print("  " + dim(card.notes))
        choice = ask(dim("  [Enter] good   h = hard   e = easy  ")).strip().lower()
        return {"h": HARD, "e": EASY}.get(choice[:1], GOOD)

    print("  " + red("✗ " + result.feedback))
    if direction == "de_en":
        print("  " + dim(f"Answer: {card.english}"))
    for n in result.notes:
        print("  " + yellow(n))
    if card.notes:
        print("  " + dim(card.notes))
    choice = ask(dim("  [Enter] continue   o = I was right (override)  ")).strip().lower()
    if choice == "o":
        print("  " + green("Counted as correct."))
        return GOOD
    return AGAIN


def _spread(queue):
    """Avoid asking both directions of the same card back to back."""
    out = []
    pending = list(queue)
    while pending:
        for i, item in enumerate(pending):
            if not out or item.card.id != out[-1].card.id:
                out.append(pending.pop(i))
                break
        else:
            out.append(pending.pop(0))
    return out


# --- grammar drill -----------------------------------------------------------

def _drill_questions(cards: list[Card]) -> list[tuple[str, Card]]:
    qs = []
    for c in cards:
        if c.article:
            qs.append(("article", c))
            continue
        ph = parse_phrase(c.german)
        if ph.has_structure:
            qs.append(("phrase", c))
        if ph.sep_prefix or separable_candidate(ph.verb_plain):
            qs.append(("separable", c))
    return qs


def grammar_drill(store: Store, rounds: int = 15):
    pool = _drill_questions(store.list_cards())
    if not pool:
        print(yellow("Nothing to drill yet. Add nouns (die Katze), separable verbs (an|rufen) "
                     "or verbs with objects/prepositions (auf etw (acc) warten)."))
        return
    # Words you've got wrong before come up more often.
    picks = []
    while pool and len(picks) < rounds:
        weights = [1 + 3 * c.grammar_misses for _, c in pool]
        picks.append(pool.pop(random.choices(range(len(pool)), weights)[0]))

    print(bold(f"\nGrammar drill — {len(picks)} questions. :q to stop."))
    print(dim("Articles: der/die/das (or r / e / s).  Separable: y / n.  "
              "Phrases: type the objects/prepositions, e.g. 'auf etw (acc)' or 'jdm'.\n"))
    score = answered = 0
    try:
        for i, (kind, card) in enumerate(picks, 1):
            print(dim(f"[{i}/{len(picks)}]"), end="  ")
            ok = {"article": _drill_article, "separable": _drill_separable, "phrase": _drill_phrase}[kind](card)
            answered += 1
            if ok:
                score += 1
            else:
                store.record_grammar_miss(card.id)
    except Quit:
        pass
    if answered:
        print(bold(f"\nScore: {score}/{answered}"))


def _ask_drill(prompt: str) -> str:
    a = ask(prompt).strip().lower()
    if a == ":q":
        raise Quit
    return a


def _drill_article(card: Card) -> bool:
    print(f"___ {bold(card.german)}" + dim(f"   ({card.english})"))
    shortcuts = {"r": "der", "e": "die", "s": "das"}
    while (a := shortcuts.get(x := _ask_drill("  Article: "), x)) not in checker.ARTICLES:
        print(dim("  Type der, die or das (r / e / s)."))
    if a == card.article:
        print("  " + green(f"✓ {card.german_full}"))
        return True
    print("  " + red(f"✗ It's {card.article.upper()} {card.german}"))
    return False


def _drill_separable(card: Card) -> bool:
    ph = parse_phrase(card.german)
    verb = ph.verb.split(" ")[-1]
    print(f"{bold(verb.replace('|', ''))}" + dim(f"   ({card.english})"))
    while (a := _ask_drill("  Separable? [y/n] ")[:1]) not in ("y", "n"):
        pass
    separable = ph.sep_prefix is not None
    if (a == "y") == separable:
        print("  " + green("✓ " + (f"Separable: {verb}" if separable else "Not separable")))
        return True
    print("  " + red("✗ " + (f"It IS separable: {verb}" if separable else "It's NOT separable")))
    return False


def _drill_phrase(card: Card) -> bool:
    ph = parse_phrase(card.german)
    print(f"___ {bold(ph.verb_plain)}" + dim(f"   ({card.english})"))
    answer = _ask_drill("  Objects / preposition: ")
    if not parse_phrase(answer).verb:
        answer = f"{answer} {ph.verb_plain}"  # let them type just the missing part
    result = checker.check_german(answer, None, card.german)
    if result.correct:
        print("  " + green(f"✓ {card.german}"))
        return True
    print("  " + red("✗ " + result.feedback))
    return False


# --- adding and editing ------------------------------------------------------

def parse_german(text: str) -> tuple[str | None, str]:
    """Split 'der Hund' into ('der', 'Hund'). Verb phrases like
    'das Licht an|machen' keep their 'das' and get no article."""
    article, word = checker.split_article(text)
    if article and "|" not in word and (" " not in word or all(w[:1].isupper() for w in word.split())):
        if word[:1].islower():
            word = word[:1].upper() + word[1:]  # nouns are capitalised
        return article, word
    return None, (f"{article} {word}" if article else word)


def check_verb_entry(word: str) -> str:
    """Ask about separability / missing cases when adding a verb. Returns the
    (possibly updated) German text."""
    ph = parse_phrase(word)
    verb = ph.verb.split(" ")[-1] if ph.verb else ""
    prefix = separable_candidate(verb)
    if prefix and yes(yellow(f"  Is '{verb}' separable ({prefix}|{verb[len(prefix):]})?")):
        marked = f"{prefix}|{verb[len(prefix):]}"
        i = word.rfind(verb)
        word = word[:i] + marked + word[i + len(verb):]
    for s in ph.slots:
        if s.prep in TWO_WAY and s.case is None:
            print(dim(f"  Tip: add the case after '{s.prep}' so it gets tested, "
                      f"e.g. '{s.prep} etw (acc)' or '{s.prep} jdm'."))
    return word


def add_words(store: Store, today: date):
    print(bold("\nAdd words."), dim("Leave German blank to finish. Examples:\n"
          "  die Katze                 nouns need their article\n"
          "  an|rufen                  | marks a separable prefix\n"
          "  jdm helfen                jdn = acc, jdm = dat, jds = gen\n"
          "  etw (acc) betrachten      or mark the case with (acc)/(dat)/(gen)\n"
          "  auf jdn/etw (acc) warten  preposition + case\n"
          "  sich (acc) für etw interessieren\n"
          "Separate English alternatives with ';', e.g. 'to view sth.; to look at sth.'\n"))
    added = 0
    try:
        while True:
            german = ask("German:  ").strip()
            if not german:
                break
            article, word = parse_german(german)
            if article is None and word[:1].isupper() and " " not in word:
                a = ask(yellow(f"  '{word}' looks like a noun. Article? (der/die/das, Enter for none) ")
                        ).strip().lower()
                if a in checker.ARTICLES:
                    article = a
            if article is None:
                word = check_verb_entry(word)
            english = ask("English: ").strip()
            if not english:
                print(dim("  Skipped (no English given).\n"))
                continue
            notes = ask(dim("Notes (optional): ")).strip()
            dup = store.find_duplicate(word)
            if dup and not yes(yellow(f"  You already have '{dup.german_full} = {dup.english}'. Add anyway?")):
                print()
                continue
            card = store.add_card(article, word, english, notes, today)
            added += 1
            print(green(f"  Added: {card.german_full} = {card.english}\n"))
    except Quit:
        pass
    print(f"{added} word(s) added.")


def browse(store: Store):
    while True:
        search = ask("\nSearch (Enter for all, :q to go back): ").strip()
        if search == ":q":
            return
        cards = store.list_cards(search)
        if not cards:
            print(dim("No matches."))
            continue
        for c in cards:
            sched = store.schedules(c.id)
            due = "  ".join(f"{ARROW[d][:2]}→{ARROW[d][-2:]} {s.due:%d %b}" for d, s in sorted(sched.items()))
            print(f"  {dim(str(c.id).rjust(4))}  {c.german_full:<28} {c.english:<30} {dim(due)}")
        choice = ask("\nCard id to edit or delete (Enter to search again): ").strip()
        if not choice:
            continue
        if not choice.isdigit() or not (card := store.get_card(int(choice))):
            print(red("No card with that id."))
            continue
        edit_card(store, card)


def edit_card(store: Store, card: Card):
    print(f"\n{bold(card.german_full)} = {card.english}" + (dim(f"  ({card.notes})") if card.notes else ""))
    action = ask("e = edit, d = delete, Enter = back: ").strip().lower()
    if action == "d":
        if yes(red(f"Delete '{card.german_full}'?")):
            store.delete_card(card.id)
            print("Deleted.")
    elif action == "e":
        print(dim("Press Enter to keep the current value."))
        g = ask(f"German  [{card.german_full}]: ").strip()
        if g:
            card.article, card.german = parse_german(g)
        e = ask(f"English [{card.english}]: ").strip()
        if e:
            card.english = e
        n = ask(f"Notes   [{card.notes}]: ").strip()
        if n:
            card.notes = "" if n == "-" else n
        store.update_card(card)
        print(green(f"Saved: {card.german_full} = {card.english}"))


# --- import / export ---------------------------------------------------------

def import_csv(store: Store, path: Path, today: date) -> tuple[int, int]:
    """Columns: german, english[, notes]. Returns (added, skipped)."""
    text = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    added = skipped = 0
    for i, row in enumerate(csv.reader(text.splitlines(), dialect)):
        row = [x.strip() for x in row]
        if not row or not any(row):
            continue
        if i == 0 and row[0].lower() in ("german", "deutsch"):
            continue
        if len(row) < 2 or not row[0] or not row[1]:
            skipped += 1
            continue
        article, word = parse_german(row[0])
        if store.find_duplicate(word):
            skipped += 1
            continue
        store.add_card(article, word, row[1], row[2] if len(row) > 2 else "", today)
        added += 1
    return added, skipped


def export_csv(store: Store, path: Path) -> int:
    cards = store.list_cards()
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["german", "english", "notes"])
        for c in cards:
            w.writerow([c.german_full, c.english, c.notes])
    return len(cards)


# --- stats -------------------------------------------------------------------

def show_stats(store: Store, today: date):
    s = store.stats(today)
    print(bold("\nStats"))
    print(f"  Cards:            {s['cards']}  ({s['nouns']} nouns)")
    print(f"  Due now:          {s['due_today']} reviews, {s['new']} new")
    print(f"  Due next 7 days:  {s['due_week']}")
    print(f"  Learning/mature:  {s['learning']} / {s['mature']}  (mature = 3+ week interval)")
    print(f"  Reviewed today:   {s['reviewed_today']}")
    if s["grammar_trouble"]:
        print(bold("\n  Trickiest grammar") + dim(" (articles, prefixes, prepositions, cases)"))
        for c in s["grammar_trouble"]:
            print(f"    {c.german_full:<34} {red(str(c.grammar_misses))} miss(es)")


# --- main --------------------------------------------------------------------

def menu(store: Store, today: date, new_limit: int):
    print(bold("\nspacedrep — German ⇄ English flashcards"))
    while True:
        due = store.due_reviews(today, new_limit)
        n_new = sum(d.is_new for d in due)
        print(f"\n  1  Review       {bold(str(len(due) - n_new))} due, {bold(str(n_new))} new")
        print("  2  Add words")
        print("  3  Browse / edit / delete")
        print("  4  Grammar drill (articles, separable verbs, prepositions & cases)")
        print("  5  Import CSV")
        print("  6  Export CSV")
        print("  7  Stats")
        print("  q  Quit")
        try:
            choice = ask("\n> ").strip().lower()
        except Quit:
            return
        try:
            if choice == "1":
                review_session(store, today, new_limit)
            elif choice == "2":
                add_words(store, today)
            elif choice == "3":
                browse(store)
            elif choice == "4":
                grammar_drill(store)
            elif choice == "5":
                p = Path(ask("CSV file (columns: german, english, notes): ").strip()).expanduser()
                if p.is_file():
                    a, s = import_csv(store, p, today)
                    print(green(f"Imported {a} card(s)") + (dim(f", skipped {s}") if s else ""))
                else:
                    print(red("File not found."))
            elif choice == "6":
                p = Path(ask("Save to (e.g. ~/cards.csv): ").strip()).expanduser()
                print(green(f"Exported {export_csv(store, p)} card(s) to {p}"))
            elif choice == "7":
                show_stats(store, today)
            elif choice in ("q", ":q", "quit", "exit"):
                return
        except Quit:
            continue


def main(argv=None):
    p = argparse.ArgumentParser(prog="spacedrep", description="German ⇄ English spaced repetition flashcards.")
    p.add_argument("--db", type=Path, default=Path(os.environ.get("SPACEDREP_DB", default_db_path())),
                   help="card database file (default: ~/.spacedrep/cards.db)")
    p.add_argument("--new", type=int, default=20, dest="new_limit",
                   help="max new words introduced per session (default: 20)")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("review", help="start a review session straight away")
    sub.add_parser("add", help="add words")
    sub.add_parser("drill", help="grammar drill: articles, separable verbs, prepositions, cases")
    sub.add_parser("stats", help="show stats")
    sub.add_parser("import", help="import a CSV (german, english, notes)").add_argument("file", type=Path)
    sub.add_parser("export", help="export all cards to CSV").add_argument("file", type=Path)
    args = p.parse_args(argv)

    today = date.fromisoformat(os.environ["SPACEDREP_TODAY"]) if os.environ.get("SPACEDREP_TODAY") else date.today()
    store = Store(args.db)
    try:
        if args.cmd == "review":
            review_session(store, today, args.new_limit)
        elif args.cmd == "add":
            add_words(store, today)
        elif args.cmd == "drill":
            grammar_drill(store)
        elif args.cmd == "stats":
            show_stats(store, today)
        elif args.cmd == "import":
            a, s = import_csv(store, args.file, today)
            print(f"Imported {a} card(s), skipped {s}.")
        elif args.cmd == "export":
            print(f"Exported {export_csv(store, args.file)} card(s).")
        else:
            menu(store, today, args.new_limit)
    except Quit:
        pass
    finally:
        store.close()
