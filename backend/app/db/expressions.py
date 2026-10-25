"""The expression corpus: each expression once, by its normalized phrase. Which sessions taught
which expression lives in session_expressions, so the corpus itself holds only the expressions."""

import json
import random
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.generation.exclusions import key
from app.models import Expression

if TYPE_CHECKING:
    from app.db import Database

COLUMNS = "e.id, e.phrase, e.meaning, e.synonyms, e.examples, e.usage_note, e.korean, e.setting"


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

    def list_all(self) -> list[Expression]:
        with self._db.connect() as conn:
            return [expression_from(row) for row in conn.execute(f"SELECT {COLUMNS} FROM expressions e ORDER BY e.id")]

    def count(self) -> int:
        with self._db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM expressions").fetchone()[0]

    def pick(self, count: int, rng: random.Random) -> list[Expression]:
        """Up to `count` expressions for a new session: never-taught ones first, taken in turn from each
        setting so a session mixes them; when those run out, the ones taught longest ago."""
        with self._db.connect() as conn:
            rows = conn.execute(
                f"""SELECT {COLUMNS}, MAX(se.session_id) AS last_taught FROM expressions e
                    LEFT JOIN session_expressions se ON se.expression_id = e.id
                    GROUP BY e.id ORDER BY e.id"""
            ).fetchall()
        by_setting: dict[str | None, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            if row["last_taught"] is None:
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
        taught = sorted((r for r in rows if r["last_taught"] is not None), key=lambda r: (r["last_taught"], r["id"]))
        picked += taught[: count - len(picked)]
        return [expression_from(row) for row in picked]
