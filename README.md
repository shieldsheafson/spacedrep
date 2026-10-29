# spacedrep

[![tests](https://github.com/shieldsheafson/spacedrep/actions/workflows/tests.yml/badge.svg)](https://github.com/shieldsheafson/spacedrep/actions/workflows/tests.yml)

German ⇄ English flashcards in the terminal, with spaced repetition and grammar checking.
Add your own words, practise both directions, and get told exactly what you got wrong:
the article, the separable prefix, the preposition, or the case.

```
[3 left]  EN → DE
  to wait for sb/sth  (include preposition + case)
  German:  auf jdm warten
  ✗ Wrong case: it's auf + ACC, not dat.  Answer: auf jdn/etw (acc) warten

[2 left]  EN → DE
  cat  (noun — include der/die/das)
  German:  der Katze
  ✗ Right word, wrong article: it's DIE Katze, not der Katze.
```

No dependencies, just Python 3.10+.

## Getting started

```bash
git clone https://github.com/shieldsheafson/spacedrep.git
cd spacedrep
python3 -m spacedrep import example_words.csv   # optional: load some sample words
python3 -m spacedrep                            # main menu
```

Or install it as a command with `pip install -e .`, then run `spacedrep`.

```bash
spacedrep review       # review what's due
spacedrep add          # add words
spacedrep drill        # articles, separable verbs, prepositions & cases
spacedrep stats
spacedrep import FILE.csv
spacedrep export FILE.csv
```

## How it works

- **Adding words:** type German in dictionary style. Separate English alternatives with `;`.

  | You type                           | Meaning                                         |
  |------------------------------------|-------------------------------------------------|
  | `die Katze`                        | noun with its article (it asks if you forget)   |
  | `an\|rufen`                        | `\|` marks a separable prefix (it asks for an/auf/über/…) |
  | `jdm helfen`                       | object case: `jdn` = acc, `jdm` = dat, `jds` = gen |
  | `etw (acc) betrachten`             | or mark it: `(acc)`/`(akk)`/`(a)`, `(dat)`/`(d)`, `(gen)`/`(g)` |
  | `auf jdn/etw (acc) warten`         | preposition + case (`warten auf + Akk` also works) |
  | `sich (dat) etw vorstellen`        | reflexive, with the case of `sich`              |

  Prepositions with only one case (`mit`, `für`, `wegen`, …) don't need a marker. Two-way
  prepositions (`an`, `auf`, `in`, `über`, …) do, otherwise the case isn't tested. An unmarked
  `etw` or `sich` counts as accusative.
- **Both directions:** every word is tested DE → EN and EN → DE, each on its own schedule.
- **Grammar is checked:** when answering in German, a missing/wrong article, preposition,
  case, object or `sich` counts as wrong, with specific feedback (*"Right word, wrong article:
  it's DIE Katze"*, *"Wrong case: it's auf + ACC, not dat"*). Object order doesn't matter, and
  `anrufen` and `an|rufen` are both accepted — but marking the split in the wrong place, or on
  a verb that isn't separable, is wrong.
- **Grammar drill:** quick-fire questions — der/die/das for nouns, "separable? y/n" for prefix
  verbs, and "fill in the objects/preposition" for verb phrases. Grammar mistakes are counted,
  shown in Stats, and those words come up more often in the drill.
- **Forgiving where it doesn't matter:** `ae/oe/ue/ss` are accepted for `ä/ö/ü/ß`; lowercase
  nouns are accepted with a reminder; English ignores `to`/`the`/`a`/`sth`/`sb` and small typos.
  German typos are wrong, but flagged as "close". If the checker is too strict (e.g. a
  synonym you didn't list), press `o` to override.
- **Scheduling:** SM-2 style. After a correct answer press Enter (good), `h` (hard) or `e` (easy).
  Wrong answers come back later in the same session. Up to 20 new words per session (`--new N`).
- **CSV:** columns `german, english, notes`; comma, semicolon or tab separated.

Cards are stored in `~/.spacedrep/cards.db` (change with `--db PATH` or `SPACEDREP_DB`).

## Development

```bash
python3 -m unittest discover -s tests
```

| File | What it does |
|------|--------------|
| `spacedrep/checker.py`   | marks typed answers (articles, umlauts, typos, English alternatives) |
| `spacedrep/grammar.py`   | parses verb phrases: separable prefixes, objects, prepositions, cases |
| `spacedrep/scheduler.py` | SM-2 style review intervals |
| `spacedrep/store.py`     | SQLite storage |
| `spacedrep/cli.py`       | terminal interface |
