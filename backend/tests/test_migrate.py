import json
import logging
import sqlite3
from pathlib import Path

from app.db import Database
from app.db.pictures import PictureStat
from app.models import Stars

# The schema every file had before v2, as app/db/__init__.py created it.
V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    content_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stars (
    session_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    item TEXT NOT NULL,
    PRIMARY KEY (session_id, kind, item)
);
CREATE TABLE IF NOT EXISTS notes (
    session_id INTEGER PRIMARY KEY,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id INTEGER,
    paragraph TEXT NOT NULL,
    user_text TEXT NOT NULL,
    seconds REAL NOT NULL DEFAULT 0,
    corrections_json TEXT
);
CREATE TABLE IF NOT EXISTS examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id INTEGER NOT NULL,
    expression TEXT NOT NULL,
    user_text TEXT NOT NULL,
    coach_text TEXT NOT NULL,
    seconds REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id INTEGER NOT NULL,
    paragraph TEXT NOT NULL,
    user_text TEXT NOT NULL,
    feedback_json TEXT NOT NULL,
    seconds REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS topic_days (
    day TEXT PRIMARY KEY,
    topics_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS image_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    seconds REAL,
    cost REAL
);
CREATE TABLE IF NOT EXISTS model_pins (
    source TEXT NOT NULL,
    model TEXT NOT NULL,
    pinned_at TEXT NOT NULL,
    PRIMARY KEY (source, model)
);
CREATE TABLE IF NOT EXISTS model_lists (
    source TEXT PRIMARY KEY,
    list_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


ARTICLE = {
    "title": "First",
    "body": "Para one.\n\nPara two here.\n\n  Para three.  ",
    "questions": [{"text": "Why?", "evidence": ["Para one."]}],
    "sources": [{"title": "A page", "url": "https://example.com"}],
    "translation": [{"en": "Para one.", "ko": "하나다."}, {"en": "Not in the body.", "ko": "없다."}],
}
FIRST_PHRASES = ["on the fence", "a moving target", "play the devil's advocate", "cut corners", "hit the ground running"]
SECOND_PHRASES = ["play devil's advocate", "spill the beans", "break the ice", "call it a day", "miss the boat"]


def expression(phrase: str, old: bool = False) -> dict:
    """An expression as v1 kept it; the oldest sessions had no synonyms or Korean."""
    item = {"phrase": phrase, "meaning": f"means {phrase}", "usage_note": "note", "examples": [f"{phrase}, really."]}
    return item if old else {**item, "synonyms": ["plainly"], "korean": "한국어"}


def word(i: int, **pictures) -> dict:
    return {"word": f"word{i}", "pos": "noun", "definition": f"def {i}", "example": f"ex {i}", "synonyms": [f"same {i}"],
            "korean": f"단어 {i}", "scene": f"scene {i}", "caption": f"caption {i}", **pictures}


def make_v1(path: Path, images_dir: Path) -> None:
    """Two sessions (11 and 12) the way v1 stored them, with everything that hung off them, and three picture files:
    two the first session's words show, one left behind by a deleted session. One word points at a file that is gone."""
    images_dir.mkdir(parents=True, exist_ok=True)
    for name in ("11-0-aaaa.png", "11-0-example.png", "17-0-old.png"):
        (images_dir / name).write_bytes(name.encode())
    first = {"topic": "A", "expressions": [expression(p) for p in FIRST_PHRASES], "article": ARTICLE,
             "vocabulary": [word(0, image="11-0-aaaa.png", example_image="11-0-example.png"), word(1, image="missing.png"), word(2)]}
    second = {"topic": "B", "expressions": [expression(p, old=True) for p in SECOND_PHRASES],
              "article": {**ARTICLE, "title": "Second", "body": "Only one."}, "vocabulary": [{"word": "old", "pos": "verb", "definition": "d", "example": "e"}]}
    with sqlite3.connect(path) as conn:
        conn.executescript(V1_SCHEMA)
        conn.executemany(
            "INSERT INTO sessions (id, created_at, topic, title, content_json) VALUES (?, ?, ?, ?, ?)",
            [(11, "2026-09-10T01:00:00+00:00", "A", "First", json.dumps(first)), (12, "2026-09-11T01:00:00+00:00", "B", "Second", json.dumps(second))],
        )
        conn.executemany("INSERT INTO stars VALUES (?, ?, ?)", [(11, "expression", "a moving target"), (11, "word", "word2"), (12, "expression", "gone phrase")])
        conn.execute("INSERT INTO notes VALUES (11, 'my note')")
        corrections = [{"kind": "phrasing", "word": "as long", "heard": "as / long", "fix": "keep it together"},
                       {"kind": "pronunciation", "word": "one", "heard": "on", "fix": "wʌn", "at": 1}]
        conn.executemany(
            "INSERT INTO readings (id, created_at, session_id, paragraph, user_text, seconds, corrections_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "2026-09-10T02:00:00+00:00", 11, "Para one.", "para one", 3, json.dumps(corrections)),
             (2, "2026-09-10T02:01:00+00:00", 11, "Para  two\nhere.", "para two", 4, None),
             (3, "2026-09-10T02:02:00+00:00", 11, "A paragraph that was never there.", "x", 1, "[]")],
        )
        conn.execute(
            "INSERT INTO summaries (id, created_at, session_id, paragraph, user_text, feedback_json, seconds) VALUES (1, '2026-09-10T03:00:00+00:00', 11, 'Para three.', 'it ends', ?, 9)",
            (json.dumps({"missed": [], "fixes": [{"said": "a", "better": "b", "why": "old field"}], "summary": "s"}),),
        )
        conn.executemany(
            "INSERT INTO examples (id, created_at, session_id, expression, user_text, coach_text, seconds) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "2026-09-10T04:00:00+00:00", 11, "On the fence", "I am on the fence", "Nice.", 5),
             (2, "2026-09-10T04:01:00+00:00", 11, "word1", "a word1 here", "Good.", 2),
             (3, "2026-09-10T04:02:00+00:00", 11, "never taught", "x", "y", 1)],
        )
        conn.executemany("INSERT INTO image_stats (created_at, model, seconds, cost) VALUES (?, ?, ?, ?)", [("t1", "m", 5.0, 0.01), ("t2", "m", 7.0, None)])
        conn.execute("INSERT INTO model_lists VALUES ('claude', ?)", (json.dumps({"at": 1000.0, "options": [{"id": "opus", "efforts": ["low"]}]}),))
        conn.execute("INSERT INTO topic_days VALUES ('2026-10-23', ?)", (json.dumps(["T1", "T2"]),))
        conn.executemany("INSERT INTO settings VALUES (?, ?)", [("SUMMARY_MODEL", "sonnet"), ("VOICE_PROVIDER", "gemini")])
        conn.execute("INSERT INTO model_pins VALUES ('openrouter_images', 'm', 't')")


def migrated(tmp_path) -> Database:
    path, images = tmp_path / "s.db", tmp_path / "images"
    make_v1(path, images)
    return Database(path, images)


def test_a_v1_file_is_backed_up_and_comes_up_as_v2_with_everything_in_rows(tmp_path):
    db = migrated(tmp_path)
    [backup] = tmp_path.glob("s.db.bak-v1-*")
    assert sqlite3.connect(backup).execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2  # the copy is the v1 file
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert names >= {"paragraphs", "vocabulary", "expressions", "session_expressions", "pictures"}
    assert not {n for n in names if n.endswith("_v1")} and not names & {"stars", "notes", "image_stats"}
    [s2, s1] = db.sessions.list_all()
    assert (s1.id, s2.id) == (11, 12)  # ids survive: the address /s/11 still opens it
    got = db.sessions.get(11)
    assert [p.text for p in got.content.article.paragraphs] == ["Para one.", "Para two here.", "Para three."]
    # One corpus row per normalized phrase: the shared one reads as the later session worded it.
    assert [e.phrase for e in got.content.expressions] == [*FIRST_PHRASES[:2], "play devil's advocate", *FIRST_PHRASES[3:]]
    assert got.content.article.translation[0].en == "Para one." and len(got.content.article.translation) == 1
    assert db.expressions.count() == 9  # ten taught, one phrase shared by the two sessions
    assert db.sessions.get_note(11).text == "my note"
    assert db.sessions.get_stars(11) == Stars(expressions=[got.content.expressions[1].id], words=[got.content.vocabulary[2].id])
    assert db.sessions.get_stars(12) == Stars()
    old = db.sessions.get(12).content
    assert old.expressions[0].id == got.content.expressions[2].id  # "play devil's advocate" is the same corpus row
    assert (old.expressions[1].synonyms, old.expressions[1].korean, old.vocabulary[0].synonyms) == ([], None, [])


def test_reopening_a_migrated_file_changes_nothing(tmp_path):
    db = migrated(tmp_path)
    again = Database(db.path, db.images_dir)
    assert again.sessions.get(11) == db.sessions.get(11)
    assert len(list(tmp_path.glob("s.db.bak-v1-*"))) == 1


def test_pictures_become_rows_and_files_are_renamed_by_id(tmp_path):
    db = migrated(tmp_path)
    word = db.sessions.get(11).content.vocabulary[0]
    assert word.image != word.example_image
    for name in (word.image, word.example_image):
        assert (tmp_path / "images" / name).is_file()
    assert (tmp_path / "images" / word.image).read_bytes() == b"11-0-aaaa.png"
    assert not (tmp_path / "images" / "11-0-aaaa.png").exists()
    assert db.pictures.stats() == {"m": PictureStat(6.0, 0.01)}  # measured history kept; carried-over pictures have no model
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pictures").fetchone()[0] == 4


def test_a_missing_picture_file_leaves_the_word_bare(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        db = migrated(tmp_path)
    assert db.sessions.get(11).content.vocabulary[1].image is None
    assert "pictures_missing=1" in caplog.text and "pictures_renamed=2" in caplog.text


def test_an_unmatched_reading_is_dropped_with_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        db = migrated(tmp_path)
    paragraphs = db.sessions.get(11).content.article.paragraphs
    readings = db.records.list_readings(11)
    assert [(r.id, r.paragraph_id) for r in readings] == [(2, paragraphs[1].id), (1, paragraphs[0].id)]  # whitespace aside, "Para two here."
    assert [c.word for c in readings[1].corrections] == ["one"]  # the pause findings v1 read past are gone
    assert readings[0].corrections is None
    assert "readings_dropped=1" in caplog.text and "A paragraph that was never there." in caplog.text
    [summary] = db.records.list_summaries(11)
    assert (summary.paragraph_id, summary.feedback.fixes[0].better) == (paragraphs[2].id, "b")


def test_examples_find_their_expression_by_key_or_their_word(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        db = migrated(tmp_path)
    content = db.sessions.get(11).content
    examples = db.records.list_examples(11)
    assert [(x.id, x.expression_id, x.vocabulary_id) for x in examples] == [(1, content.expressions[0].id, None), (2, None, content.vocabulary[1].id)]
    assert "examples_dropped=1" in caplog.text


def test_model_lists_topic_days_and_settings_keep_their_values(tmp_path):
    db = migrated(tmp_path)
    cached = db.caches.get_model_list("claude")
    assert (cached.fetched_at, cached.options) == (1000.0, [{"id": "opus", "efforts": ["low"]}])
    assert db.caches.get_daily_topics("2026-10-23") == ["T1", "T2"]
    assert db.settings.load() == {"SUMMARY_MODEL": "sonnet", "VOICE_PROVIDER": "gemini"}  # nothing is dropped any more
    assert db.pins.pinned("openrouter_images") == ["m"]


def test_orphan_files_are_counted_and_left_alone(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        migrated(tmp_path)
    assert (tmp_path / "images" / "17-0-old.png").is_file()
    assert "orphan_files=1" in caplog.text


def test_a_new_session_after_migration_gets_the_next_id(tmp_path):
    from tests.conftest import sample_draft

    db = migrated(tmp_path)
    assert db.sessions.create(sample_draft(), []).id == 13
