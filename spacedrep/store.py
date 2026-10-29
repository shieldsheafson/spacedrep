"""SQLite storage for cards and their review schedules."""

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .scheduler import Schedule

DIRECTIONS = ("de_en", "en_de")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id             INTEGER PRIMARY KEY,
    article        TEXT,               -- der / die / das, or NULL for non-nouns
    german         TEXT NOT NULL,      -- the word without its article
    english        TEXT NOT NULL,      -- alternatives separated by ';' or ','
    notes          TEXT NOT NULL DEFAULT '',
    grammar_misses INTEGER NOT NULL DEFAULT 0,  -- article/prefix/preposition/case
    created        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    card_id     INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    direction   TEXT NOT NULL CHECK (direction IN ('de_en', 'en_de')),
    ease        REAL NOT NULL DEFAULT 2.5,
    interval    INTEGER NOT NULL DEFAULT 0,
    reps        INTEGER NOT NULL DEFAULT 0,
    lapses      INTEGER NOT NULL DEFAULT 0,
    due         TEXT NOT NULL,
    last_review TEXT,
    PRIMARY KEY (card_id, direction)
);
"""


@dataclass
class Card:
    id: int
    article: str | None
    german: str
    english: str
    notes: str = ""
    grammar_misses: int = 0

    @property
    def german_full(self) -> str:
        return f"{self.article} {self.german}" if self.article else self.german


@dataclass
class Due:
    card: Card
    direction: str
    schedule: Schedule
    is_new: bool


def default_db_path() -> Path:
    return Path.home() / ".spacedrep" / "cards.db"


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self._migrate()
        self.db.executescript(SCHEMA)

    def _migrate(self):
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(cards)")}
        if "article_misses" in cols:  # older databases
            self.db.execute("ALTER TABLE cards RENAME COLUMN article_misses TO grammar_misses")
            self.db.commit()

    def close(self):
        self.db.close()

    # --- cards -------------------------------------------------------------

    def add_card(self, article, german, english, notes="", today: date | None = None) -> Card:
        today = today or date.today()
        with self.db:
            cur = self.db.execute(
                "INSERT INTO cards (article, german, english, notes, created) VALUES (?, ?, ?, ?, ?)",
                (article, german, english, notes, today.isoformat()),
            )
            card_id = cur.lastrowid
            for d in DIRECTIONS:
                self.db.execute(
                    "INSERT INTO reviews (card_id, direction, due) VALUES (?, ?, ?)",
                    (card_id, d, today.isoformat()),
                )
        return self.get_card(card_id)

    def update_card(self, card: Card):
        with self.db:
            self.db.execute(
                "UPDATE cards SET article = ?, german = ?, english = ?, notes = ? WHERE id = ?",
                (card.article, card.german, card.english, card.notes, card.id),
            )

    def delete_card(self, card_id: int):
        with self.db:
            self.db.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    def get_card(self, card_id: int) -> Card | None:
        row = self.db.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return _card(row) if row else None

    def find_duplicate(self, german: str) -> Card | None:
        row = self.db.execute(
            "SELECT * FROM cards WHERE lower(german) = lower(?)", (german,)
        ).fetchone()
        return _card(row) if row else None

    def list_cards(self, search: str = "") -> list[Card]:
        like = f"%{search}%"
        rows = self.db.execute(
            "SELECT * FROM cards WHERE german LIKE ? OR english LIKE ? ORDER BY german COLLATE NOCASE",
            (like, like),
        ).fetchall()
        return [_card(r) for r in rows]

    def record_grammar_miss(self, card_id: int):
        with self.db:
            self.db.execute(
                "UPDATE cards SET grammar_misses = grammar_misses + 1 WHERE id = ?", (card_id,)
            )

    # --- reviews -----------------------------------------------------------

    def due_reviews(self, today: date, new_limit: int = 20) -> list[Due]:
        """Reviews due today, plus up to `new_limit` cards never seen before."""
        rows = self.db.execute(
            """SELECT c.*, r.direction, r.ease, r.interval, r.reps, r.lapses, r.due,
                      r.last_review IS NULL AS is_new
               FROM reviews r JOIN cards c ON c.id = r.card_id
               WHERE r.due <= ?
               ORDER BY r.due, c.id""",
            (today.isoformat(),),
        ).fetchall()
        out, new_cards = [], set()
        for r in rows:
            if r["is_new"]:
                if r["id"] not in new_cards and len(new_cards) >= new_limit:
                    continue
                new_cards.add(r["id"])
            out.append(Due(_card(r), r["direction"], _schedule(r), bool(r["is_new"])))
        return out

    def save_review(self, card_id: int, direction: str, s: Schedule, today: date):
        with self.db:
            self.db.execute(
                """UPDATE reviews SET ease = ?, interval = ?, reps = ?, lapses = ?, due = ?,
                          last_review = ?
                   WHERE card_id = ? AND direction = ?""",
                (s.ease, s.interval, s.reps, s.lapses, s.due.isoformat(), today.isoformat(),
                 card_id, direction),
            )

    def schedules(self, card_id: int) -> dict[str, Schedule]:
        rows = self.db.execute("SELECT * FROM reviews WHERE card_id = ?", (card_id,)).fetchall()
        return {r["direction"]: _schedule(r) for r in rows}

    def stats(self, today: date) -> dict:
        q = lambda sql, *a: self.db.execute(sql, a).fetchone()[0]
        t = today.isoformat()
        return {
            "cards": q("SELECT COUNT(*) FROM cards"),
            "nouns": q("SELECT COUNT(*) FROM cards WHERE article IS NOT NULL"),
            "due_today": q("SELECT COUNT(*) FROM reviews WHERE due <= ? AND last_review IS NOT NULL", t),
            "new": q("SELECT COUNT(*) FROM reviews WHERE last_review IS NULL"),
            "due_week": q(
                "SELECT COUNT(*) FROM reviews WHERE due <= date(?, '+7 days') AND last_review IS NOT NULL", t),
            "learning": q("SELECT COUNT(*) FROM reviews WHERE last_review IS NOT NULL AND interval < 21"),
            "mature": q("SELECT COUNT(*) FROM reviews WHERE interval >= 21"),
            "reviewed_today": q("SELECT COUNT(*) FROM reviews WHERE last_review = ?", t),
            "grammar_trouble": [
                _card(r) for r in self.db.execute(
                    "SELECT * FROM cards WHERE grammar_misses > 0 ORDER BY grammar_misses DESC LIMIT 10"
                )
            ],
        }


def _card(row) -> Card:
    return Card(row["id"], row["article"], row["german"], row["english"], row["notes"],
                row["grammar_misses"])


def _schedule(row) -> Schedule:
    return Schedule(row["ease"], row["interval"], row["reps"], row["lapses"],
                    date.fromisoformat(row["due"]))
