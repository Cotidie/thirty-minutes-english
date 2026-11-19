"""Summaries judged in the background: the route keeps what was said and answers at once, and the judgment fills the
summary in later, paid for only when it ran.

The executor is not the session generator's: a generation takes minutes, and a judgment queued behind one would too.
"""

import logging
import sqlite3
from collections.abc import Callable

from app.coaching.summary_feedback import SummaryCoach
from app.db.credits import CreditRepo
from app.db.records import RecordRepo
from app.generation.jobs import Executor

log = logging.getLogger(__name__)

RESTARTED = "The server restarted before the feedback came back."
NOT_SAVED = "feedback failed: it came back but could not be saved"

# How many judgments run at once; each is a claude CLI process. The rest wait their turn.
JUDGES = 4


class SummaryJudges:
    def __init__(self, records: RecordRepo, credits: CreditRepo, executor: Executor) -> None:
        self._records = records
        self._credits = credits
        self._executor = executor

    def judge(self, summary_id: int, coach: SummaryCoach, hold: int | None) -> None:
        """Hands the summary, already waiting for its feedback, to a judge; `hold` is its price."""
        self._executor.submit(self._judge, summary_id, coach, hold)

    def _judge(self, summary_id: int, coach: SummaryCoach, hold: int | None) -> None:
        """Settles or gives back `hold` exactly once, whatever fails: nothing on this thread reaches anyone else, so a
        summary must never be left waiting with its price held."""
        try:
            paid = self._fill_in(summary_id, coach)
        except Exception:
            log.exception("summary %s could not be judged or saved", summary_id)
            paid = False
            try:
                self._records.fail_summary(summary_id, NOT_SAVED)
            except sqlite3.Error:
                log.exception("summary %s stays judging until the app starts again", summary_id)
        _quietly(self._credits.settle if paid else self._credits.release, hold)

    def _fill_in(self, summary_id: int, coach: SummaryCoach) -> bool:
        """Judges the summary and keeps the feedback. True when the judgment ran and was kept, or its summary went with
        the session meanwhile; False when there was nothing to pay for."""
        said = self._records.summary_to_judge(summary_id)
        if said is None:  # gone with its session before a judge got to it
            return False
        try:
            feedback = coach.feedback(*said)
        except Exception as e:
            log.exception("summary %s could not be judged", summary_id)
            self._records.fail_summary(summary_id, f"feedback failed: {getattr(e, 'message', e)}")
            return False
        self._records.finish_summary(summary_id, feedback)
        return True


def _quietly(step: Callable[[int | None], None], hold: int | None) -> None:
    """A failure of the ledger is logged, not raised: the hold goes back when the app next starts."""
    try:
        step(hold)
    except sqlite3.Error:
        log.exception("could not finish credit hold %s", hold)
