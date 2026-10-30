"""The expression corpus: each expression once, by its normalized phrase. Which sessions taught
which expression lives in session_expressions, and which ones a session swapped out in
swapped_expressions, so the corpus itself holds only the expressions."""

import json
import random
import sqlite3
from collections import defaultdict
from collections.abc import Collection
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.db.shares import VISIBLE_SESSIONS
from app.generation.exclusions import key
from app.models import CorpusEntry, Expression

if TYPE_CHECKING:
    from app.db import Database

COLUMNS = "e.id, e.phrase, e.meaning, e.synonyms, e.examples, e.usage_note, e.korean, e.setting, e.korean_example"
# Every session that used an expression: taught it, or swapped it out.
USES = "SELECT session_id, expression_id FROM session_expressions UNION ALL SELECT session_id, expression_id FROM swapped_expressions"


def expression_from(row: sqlite3.Row) -> Expression:
    return Expression(
        id=row["id"],
        phrase=row["phrase"],
        meaning=row["meaning"],
        synonyms=json.loads(row["synonyms"]),
        usage_note=row["usage_note"],
        examples=json.loads(row["examples"]),
        korean=row["korean"],
        setting=row["setting"],
        korean_example=row["korean_example"] and json.loads(row["korean_example"]),
    )


def upsert(
    conn: sqlite3.Connection, phrase: str, meaning: str, synonyms: list[str], examples: list[str], usage_note: str,
    korean: str | None, setting: str | None, source: str, added_at: str,
) -> int:
    """The id of the corpus row for `phrase`, written or rewritten on `conn`'s open transaction."""
    (expression_id,) = conn.execute(
        """INSERT INTO expressions (key, phrase, meaning, synonyms, examples, usage_note, korean, setting, source, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (key) DO UPDATE SET phrase = excluded.phrase, meaning = excluded.meaning,
               synonyms = excluded.synonyms, examples = excluded.examples, usage_note = excluded.usage_note,
               korean = excluded.korean, setting = excluded.setting, source = excluded.source
           RETURNING id""",
        (key(phrase), phrase, meaning, json.dumps(synonyms, ensure_ascii=False), json.dumps(examples, ensure_ascii=False),
         usage_note, korean, setting, source, added_at),
    ).fetchone()
    return expression_id


class ExpressionRepo:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def add(
        self,
        phrase: str,
        meaning: str,
        synonyms: list[str],
        examples: list[str],
        usage_note: str,
        korean: str | None,
        setting: str | None,
        source: str,
        added_at: datetime | None = None,
    ) -> int:
        """The expression's id. A phrase already in the corpus (close variants included) keeps its id and takes the new wording."""
        with self._db.connect() as conn:
            return upsert(conn, phrase, meaning, synonyms, examples, usage_note, korean, setting, source, (added_at or datetime.now(UTC)).isoformat())

    def get(self, expression_id: int) -> Expression | None:
        with self._db.connect() as conn:
            row = conn.execute(f"SELECT {COLUMNS} FROM expressions e WHERE e.id = ?", (expression_id,)).fetchone()
        return expression_from(row) if row else None

    def list_all(self) -> list[CorpusEntry]:
        with self._db.connect() as conn:
            rows = conn.execute(
                f"""SELECT {COLUMNS}, e.source, e.added_at,
                        (SELECT json_group_array(session_id) FROM (SELECT session_id FROM session_expressions
                            WHERE expression_id = e.id ORDER BY session_id)) AS sessions,
                        (SELECT json_group_array(session_id) FROM (SELECT session_id FROM swapped_expressions
                            WHERE expression_id = e.id ORDER BY session_id)) AS swapped
                    FROM expressions e ORDER BY e.id"""
            ).fetchall()
        return [
            CorpusEntry(**expression_from(row).model_dump(), source=row["source"], added_at=row["added_at"],
                        sessions=json.loads(row["sessions"]), swapped=json.loads(row["swapped"]))
            for row in rows
        ]

    def delete(self, expression_id: int) -> bool:
        """Takes the expression out of the corpus and out of every session that taught it, with its stars
        there; False when there was no such expression."""
        with self._db.connect() as conn:
            conn.execute("DELETE FROM session_expressions WHERE expression_id = ?", (expression_id,))
            return conn.execute("DELETE FROM expressions WHERE id = ?", (expression_id,)).rowcount > 0

    def count(self) -> int:
        with self._db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM expressions").fetchone()[0]

    def pick(self, count: int, rng: random.Random, exclude: Collection[int] = (), seen_by: int | None = None) -> list[Expression]:
        """Up to `count` expressions for a session, none of `exclude`: never-used ones first, taken in turn
        from each setting so a session mixes them; when those run out, the ones used longest ago.
        With `seen_by`, used means in the sessions that account made or had shared with it."""
        uses, params = (USES, ()) if seen_by is None else (f"SELECT * FROM ({USES}) WHERE session_id IN ({VISIBLE_SESSIONS})", (seen_by, seen_by))
        with self._db.connect() as conn:
            rows = conn.execute(
                f"""SELECT {COLUMNS}, MAX(u.session_id) AS last_used FROM expressions e
                    LEFT JOIN ({uses}) u ON u.expression_id = e.id
                    GROUP BY e.id ORDER BY e.id""",
                params,
            ).fetchall()
        rows = [row for row in rows if row["id"] not in exclude]
        by_setting: dict[str | None, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            if row["last_used"] is None:
                by_setting[row["setting"]].append(row)
        groups = sorted(by_setting.values(), key=lambda g: str(g[0]["setting"]))
        rng.shuffle(groups)
        for group in groups:
            rng.shuffle(group)
        picked: list[sqlite3.Row] = []
        while len(picked) < count and any(groups):
            for group in groups:
                if group and len(picked) < count:
                    picked.append(group.pop())
        used = sorted((r for r in rows if r["last_used"] is not None), key=lambda r: (r["last_used"], r["id"]))
        picked += used[: count - len(picked)]
        return [expression_from(row) for row in picked]
