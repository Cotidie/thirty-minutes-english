import sqlite3

import pytest

from app.db import Database
from app.db.pictures import PictureStat
from app.generation.progress import Stage


def test_a_fresh_file_is_at_version_2_with_strict_tables_and_live_foreign_keys(tmp_path):
    db = Database(tmp_path / "s.db")
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        sqls = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        assert sqls and all(s.rstrip().endswith("STRICT") for s in sqls)
        assert {r[1] for r in conn.execute("PRAGMA table_info(sessions)")} == {"id", "created_at", "topic", "title", "note", "questions", "sources", "translation"}
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO paragraphs (session_id, position, text) VALUES (999, 0, 'x')")


def test_stage_times_keep_the_latest_runs_oldest_first(tmp_path):
    stages = Database(tmp_path / "s.db").stages
    for s in (10, 20, 30, 40, 50, 60):
        stages.add(Stage.WRITING, s)
    assert stages.recent(Stage.WRITING, 5) == [20, 30, 40, 50, 60]
    assert stages.recent(Stage.SEARCHING) == []


def test_pictures_are_rows_with_an_id_and_stats_skip_unknown_models(tmp_path):
    pictures = Database(tmp_path / "s.db").pictures
    first = pictures.add("m", 4.0, 0.01)
    assert pictures.add("m", 6.0, None) == first + 1
    pictures.add(None, 9.0, None)
    assert pictures.stats() == {"m": PictureStat(5.0, 0.01)}
    assert pictures.seconds("m") == 5.0 and pictures.seconds("none") is None
