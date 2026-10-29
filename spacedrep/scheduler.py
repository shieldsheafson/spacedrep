"""SM-2 style spaced repetition scheduling.

Each card is reviewed separately in each direction (German→English and
English→German), and each direction has its own schedule.
"""

from dataclasses import dataclass, replace
from datetime import date, timedelta

# Grades the user can give a review.
AGAIN = 1  # wrong answer
HARD = 3   # right, but it was a struggle
GOOD = 4   # right
EASY = 5   # right, instantly

MIN_EASE = 1.3


@dataclass(frozen=True)
class Schedule:
    ease: float = 2.5
    interval: int = 0      # days until the next review
    reps: int = 0          # correct reviews in a row
    lapses: int = 0        # times forgotten after being learned
    due: date | None = None


def review(s: Schedule, grade: int, today: date) -> Schedule:
    """Return the new schedule after a review with the given grade."""
    if grade < HARD:
        return replace(
            s,
            reps=0,
            interval=0,  # due again today, so it comes back in the session
            lapses=s.lapses + (1 if s.reps > 0 else 0),
            ease=max(MIN_EASE, s.ease - 0.2),
            due=today,
        )

    ease = s.ease + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)
    ease = max(MIN_EASE, ease)

    if s.reps == 0:
        interval = 1 if grade < EASY else 3
    elif s.reps == 1:
        interval = {HARD: 2, GOOD: 3, EASY: 6}[grade]
    else:
        interval = round(s.interval * ease)
        if grade == HARD:
            interval = round(s.interval * 1.2)
        elif grade == EASY:
            interval = round(interval * 1.3)
        interval = max(interval, s.interval + 1)

    return replace(
        s,
        ease=ease,
        interval=interval,
        reps=s.reps + 1,
        due=today + timedelta(days=interval),
    )
