# SQLite 스키마 v2 + Expression corpus 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sessions.db`를 참조 중심 스키마 v2로 옮기고, 표현을 corpus 테이블에서 고르게 한다.

**Architecture:** 생성기는 `Draft`(기사+어휘)만 쓴다. 저장 시 단락·어휘는 행이 되고 표현 5개는 `expressions` corpus에서 뽑아 `session_expressions`로 연결된다. 그림·단락·표현·단어는 전부 FK로 가리키고, v1 파일은 시작 시 한 번 마이그레이션한다.

**Tech Stack:** Python 3 / FastAPI / Pydantic v2 / `sqlite3`(SQLite ≥ 3.37, STRICT) / pytest. React 19 / TypeScript / vitest.

**Spec:** `docs/superpowers/specs/2026-10-25-sqlite-schema-redesign-design.md`

## Global Constraints

- 모든 테이블 `STRICT`. JSON은 `TEXT` 컬럼, 이름은 내용(`synonyms`, `corrections`), `_json` 접미사 금지. boolean은 `INTEGER` 0/1.
- 연결마다 `PRAGMA foreign_keys = ON`. 스키마 버전 `PRAGMA user_version = 2`.
- `EXPRESSION_COUNT = 5`, `VOCABULARY_COUNT = 10` (`app/generation/generator.py`).
- 단락 나누기: `re.split(r"\n\s*\n", body)`, `strip()`, 빈 것 제외. 프론트와 같은 규칙이었음 (`ArticleTab.tsx:26`).
- 그림 파일 = `images/{pictures.id}.png`. API의 `image`/`example_image`는 그 파일명.
- `expressions.key = app.generation.exclusions.key(phrase)`. `setting ∈ {casual, workplace, discussion, NULL}`.
- v1 백업 파일명 `sessions.db.bak-v1-YYYY-MM-DD`.
- 커밋 메시지: 소문자 `feat:`/`refactor:`/`test:` 접두, Co-Authored-By 없음.
- GitNexus (`CLAUDE.md`): 심볼 편집 전 `node .gitnexus/run.cjs impact "<Symbol>" --direction upstream --repo .`, 커밋 전 `node .gitnexus/run.cjs detect-changes --scope all --repo .`. 계획 시점 결과: `Article`·`SessionContent`·`VocabularyItem`(백엔드·프론트 둘 다) **HIGH**(직접 참조 15~25, 전부 모델 소비자·테스트), `Database`·`PictureLog` MEDIUM, 나머지 LOW. HIGH 심볼은 Task 1·8·9에서 바꾸며, 그 작업의 테스트가 소비자 전부를 덮는다.
- 테스트 상태: Task 1~6 사이 `tests/test_api.py`는 빨간 상태를 허용한다(API가 Task 7에서 맞춰짐). 각 Task는 자기가 이름 댄 테스트 파일만 녹색으로 만든다. Task 7부터 `uv run pytest` 전체 녹색, Task 9부터 `npm test` 전체 녹색.

## Review Focus

1. corpus가 비었거나 5개 미만일 때: 표현 0~4개인 세션이 저장되고 Expressions 탭이 안내문을 보인다 (Task 2 `test_pick_returns_what_there_is`, Task 9 빈 상태 테스트).
2. 마이그레이션에서 단락 텍스트가 어떤 단락과도 안 맞는 reading: 버려지고 경고 로그, 나머지는 산다 (Task 4 `test_an_unmatched_reading_is_dropped_with_a_warning`).
3. 마이그레이션에서 vocabulary가 가리키는 그림 파일이 디스크에 없음: FK NULL, 나머지 그림은 rename (Task 4 `test_a_missing_picture_file_leaves_the_word_bare`).
4. 그 세션이 가르치지 않은 표현으로 예문 저장 요청: 404, 아무것도 안 저장 (Task 7 `test_an_example_for_an_expression_not_in_the_session_is_404`).
5. 다시 그리기 중 세션이 지워짐: 404, 새 파일이 남지 않음 (Task 7 `test_redraw_after_the_session_went_away_leaves_no_file`).

---

### Task 1: 모델, 스키마 v2, Database, 작은 repo들

**Files:**
- Create: `backend/app/db/schema.py`, `backend/app/db/stages.py`, `backend/tests/test_schema.py`
- Modify: `backend/app/models.py`, `backend/app/db/__init__.py`, `backend/app/db/pictures.py`, `backend/app/db/caches.py`, `backend/app/config/catalog.py:180-210`
- Test: `backend/tests/test_schema.py`, `backend/tests/test_catalog.py`, `backend/tests/test_settings.py`

**Interfaces:**
- Produces `app/models.py`:
  - `Paragraph(id: int, text: str)`; `Article(title, paragraphs: list[Paragraph], questions: list[Question], sources: list[Source] = [], translation: list[SentencePair] = [])` (`body` 삭제, `keep_only_sentences_found_in_the_body` 검증은 `ArticleDraft`로 이동)
  - `ArticleDraft(title, body, questions, sources, translation)` 기존 Article 그대로. `VocabularyDraft` = 기존 VocabularyItem에서 `image`/`example_image` 뺀 것. `Draft(topic, article: ArticleDraft, vocabulary: list[VocabularyDraft])`
  - `Expression(id: int, phrase, meaning, synonyms: list[str] = [], usage_note, examples: list[str], korean: str | None = None, setting: str | None = None)`
  - `VocabularyItem(id: int, ...기존 필드, image: str | None, example_image: str | None)`
  - `SessionContent(topic, expressions: list[Expression], article: Article, vocabulary: list[VocabularyItem])`, `Session`, `SessionSummary` 그대로
  - `Stars(expressions: list[int] = [], words: list[int] = [])`
  - `Reading(id, created_at, paragraph_id: int, user_text, seconds, corrections: list[Correction] | None)`; `Summary(id, created_at, paragraph_id, user_text, feedback, seconds)`; `Example(id, created_at, expression_id: int | None, vocabulary_id: int | None, user_text, coach_text, seconds)`
- Produces `app/db/schema.py`: `VERSION = 2`, `SCHEMA: str` (설계 문서의 DDL + 인덱스 그대로), `create(conn: sqlite3.Connection) -> None` (SCHEMA 실행 + `PRAGMA user_version = 2`)
- Produces `app/db/__init__.py`: `Database(path: Path | str, images_dir: Path | None = None)`; `connect() -> sqlite3.Connection` (row_factory=Row, `PRAGMA foreign_keys = ON`); 속성 `sessions, expressions, records, pictures, stages, caches, pins, settings`. 새 파일(user_version 0, `sessions` 테이블 없음) → `schema.create`. v1 파일 → Task 4의 `migrate_v1` (이 Task에서는 `NotImplementedError`를 내는 자리만).
- Produces `app/db/pictures.py`: `PictureRepo.add(model: str | None, seconds: float | None, cost: float | None) -> int`; `stats() -> dict[str, PictureStat]` (`model IS NULL` 제외, 최근 20장); `seconds(model: str) -> float | None`
- Produces `app/db/stages.py`: `StageRepo.add(stage: Stage, seconds: float) -> None`; `recent(stage: Stage, n: int = 5) -> list[float]` (최신 n개, 오래된 것 먼저)
- Produces `app/db/caches.py`: `ModelList(fetched_at: float, options: list[dict])` dataclass; `get_model_list(source) -> ModelList | None`; `set_model_list(source, fetched_at: float, options: list[dict]) -> None`; `get_daily_topics`/`set_daily_topics` 시그니처 그대로, 컬럼 `topics`
- `app/db/pins.py`, `settings.py` 변경 없음

- [ ] **Step 1: impact.** `Article`, `SessionContent`, `VocabularyItem`(`--file-path backend/app/models.py`), `Database`, `PictureRepo`, `CacheRepo`. HIGH 경고 확인, 직접 참조 목록을 이 Task의 테스트 범위와 대조.
- [ ] **Step 2: `tests/test_schema.py` 작성 (실패)**

```python
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
```

- [ ] **Step 3: 실행, 실패 확인.** `cd backend && uv run pytest tests/test_schema.py -v` → ImportError/AttributeError.
- [ ] **Step 4: 구현.** `schema.py`(설계 문서 DDL 복사, 인덱스 9개), `models.py`(위 모델. `Draft`가 `keep_only_sentences_found_in_the_body` 보유), `Database`(위), `PictureRepo`(`image_stats` → `pictures`), `StageRepo`, `CacheRepo`(`ModelList`). `_carry_over_costs`, `_drop_removed` 삭제. `SessionRepo`/`RecordRepo`는 import만 유지(Task 2·3).
- [ ] **Step 5: `catalog.py` 맞춤.** `cached["at"]` → `cached.fetched_at`, `cached["options"]` → `cached.options`, `set_model_list(source, self._clock(), [asdict(o) ...])`.
- [ ] **Step 6: 테스트 맞춤.** `test_catalog.py`: `test_costs_kept_before_seconds_were_move_into_the_picture_stats` 삭제(레거시), `test_a_list_cached_by_an_older_version_still_reads`·`test_image_models_carry_what_a_picture_cost_and_took_here`는 `pictures.add`/`ModelList`로. `test_settings.py`는 그대로 통과해야 함.
- [ ] **Step 7: 실행.** `uv run pytest tests/test_schema.py tests/test_catalog.py tests/test_settings.py -v` → PASS.
- [ ] **Step 8: detect-changes, 커밋.** `git add backend/app/models.py backend/app/db backend/app/config/catalog.py backend/tests/test_schema.py backend/tests/test_catalog.py && git commit -m "feat: schema v2, strict tables with foreign keys, pictures and stage times as rows"`

---

### Task 2: SessionRepo와 ExpressionRepo

**Files:**
- Create: `backend/app/db/expressions.py`, `backend/tests/test_expressions.py`
- Modify: `backend/app/db/sessions.py`, `backend/tests/conftest.py`, `backend/tests/test_store.py`

**Interfaces:**
- Consumes Task 1 모델·`Database`.
- Produces `app/db/expressions.py`:
  - `ExpressionRepo.add(phrase: str, meaning: str, synonyms: list[str], examples: list[str], usage_note: str, korean: str | None, setting: str | None, source: str, added_at: datetime | None = None) -> int` (`key(phrase)`로 upsert: 같은 key면 내용 갱신, id 유지)
  - `get(expression_id: int) -> Expression | None`; `list_all() -> list[Expression]` (id 순); `count() -> int`
  - `pick(count: int, rng: random.Random) -> list[Expression]`: 설계 문서 "표현 선택 규칙". setting별로(NULL 포함) 섞은 뒤 돌아가며 뽑고, 안 배운 것이 모자라면 마지막으로 배운 시점 오름차순으로 채움. 중복 없음.
- Produces `app/db/sessions.py`:
  - `create(draft: Draft, expression_ids: Sequence[int]) -> Session`; `get(session_id) -> Session | None`; `exists`; `list_all`; `recent_topics(limit)` 그대로
  - `delete(session_id) -> list[int] | None`: 지운 세션의 vocabulary가 가리키던 picture id들(둘 다), 세션이 없으면 None
  - `used_words(limit_sessions: int = 40) -> tuple[str, ...]` (최신 세션부터, 중복 제거) — `used_items` 대체
  - `replace_picture(vocabulary_id: int, field: PictureField, picture_id: int, scene: Scene | None = None) -> int | None`: 이전 picture id(없으면 None); vocabulary 행이 없으면 `KeyError`. `scene`이 오면 `scene`·`caption`도 갱신. `BEGIN IMMEDIATE`.
  - `session_of_paragraph(paragraph_id: int) -> int | None`; `session_of_vocabulary(vocabulary_id: int) -> int | None`
  - `get_stars(session_id) -> Stars` / `set_stars(session_id, stars: Stars) -> Stars` (id 목록; 세션 밖 id는 무시), `get_note` / `set_note` (`sessions.note`)
  - `get`이 만드는 `VocabularyItem.image = f"{picture_id}.png"` (NULL → None). `Expression`은 `session_expressions.position` 순.
- Produces `tests/conftest.py`: `sample_draft(topic="Digital twins", title="Twins at Work") -> Draft` (기존 `sample_content`에서 expressions 제거, body는 단락 3개 `"One.\n\nTwo two.\n\nThree."` 형태), `seed_expressions(db: Database, n: int = 5, setting: str | None = None) -> list[int]`, fixture `draft`.

- [ ] **Step 1: impact.** `SessionRepo`, `Exclusions`(사용처 확인용).
- [ ] **Step 2: `tests/test_expressions.py` 작성 (실패)**

```python
def test_add_upserts_by_normalized_key_and_keeps_the_id(store):
    a = store.expressions.add("play the devil's advocate", "m", [], [], "n", None, "casual", "s")
    b = store.expressions.add("play devil's advocate", "m2", ["argue"], ["e"], "n2", "반론", "casual", "s")
    assert a == b and store.expressions.count() == 1
    assert store.expressions.get(a).meaning == "m2"

def test_pick_prefers_untaught_and_mixes_settings(store):
    ids = {r: [store.expressions.add(f"{r} {i}", "m", [], [], "n", None, r, "s") for i in range(3)] for r in ("casual", "workplace", None)}
    picked = store.expressions.pick(3, random.Random(1))
    assert {e.setting for e in picked} == {"casual", "workplace", None}

def test_pick_fills_from_the_longest_ago_taught_when_untaught_run_out(store):
    first = store.expressions.add("one", "m", [], [], "n", None, None, "s")
    second = store.expressions.add("two", "m", [], [], "n", None, None, "s")
    store.sessions.create(sample_draft(), [first])
    store.sessions.create(sample_draft(), [second])
    assert [e.id for e in store.expressions.pick(2, random.Random(0))] == [first, second]

def test_pick_returns_what_there_is(store):
    assert store.expressions.pick(5, random.Random(0)) == []
```

- [ ] **Step 3: `tests/test_store.py` 다시 쓰기 (실패).** 기존 테스트 이름을 유지하되 `sample_draft`·`seed_expressions`로. 새로 추가:

```python
def test_create_splits_paragraphs_links_expressions_in_order_and_get_puts_it_back(store):
    ids = seed_expressions(store, 5)
    session = store.sessions.create(sample_draft(), ids)
    got = store.sessions.get(session.id)
    assert [p.text for p in got.content.article.paragraphs] == ["One.", "Two two.", "Three."]
    assert [e.id for e in got.content.expressions] == ids
    assert [v.word for v in got.content.vocabulary] == [f"word{i}" for i in range(VOCABULARY_COUNT)]
    assert got.content.vocabulary[0].image is None

def test_replace_picture_returns_the_old_one_and_can_change_the_scene(store):
    session = store.sessions.create(sample_draft(), [])
    word = session.content.vocabulary[1]
    p1, p2 = store.pictures.add("m", 1, None), store.pictures.add("m", 1, None)
    assert store.sessions.replace_picture(word.id, "image", p1) is None
    assert store.sessions.replace_picture(word.id, "image", p2, Scene("new", "cap")) == p1
    again = store.sessions.get(session.id).content.vocabulary[1]
    assert (again.image, again.scene, again.caption) == (f"{p2}.png", "new", "cap")
    with pytest.raises(KeyError):
        store.sessions.replace_picture(999, "image", p1)

def test_delete_cascades_and_hands_back_the_picture_ids(store):
    session = store.sessions.create(sample_draft(), seed_expressions(store, 2))
    p = store.pictures.add("m", 1, None)
    store.sessions.replace_picture(session.content.vocabulary[0].id, "example_image", p)
    assert store.sessions.delete(session.id) == [p]
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM session_expressions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM expressions").fetchone()[0] == 2  # corpus stays
    assert store.sessions.delete(session.id) is None

def test_stars_are_ids_and_ignore_ids_from_other_sessions(store): ...
def test_used_words_lists_distinct_words_newest_first(store): ...
```

- [ ] **Step 4: 실행, 실패 확인.** `uv run pytest tests/test_expressions.py tests/test_store.py -v`
- [ ] **Step 5: 구현.** `expressions.py`, `sessions.py` 전면 재작성(`content_json` 흔적 없음, `OWNED_TABLES` 삭제), `conftest.py`.
- [ ] **Step 6: 실행.** 위 두 파일 PASS. `tests/test_schema.py tests/test_catalog.py tests/test_settings.py`도 여전히 PASS.
- [ ] **Step 7: detect-changes, 커밋.** `git commit -m "feat: sessions as rows, expressions picked from a corpus"`

---

### Task 3: RecordRepo

**Files:**
- Modify: `backend/app/db/records.py`, `backend/tests/test_store.py`

**Interfaces:**
- Produces `RecordRepo`:
  - `add_example(session_id: int, expression_id: int | None, vocabulary_id: int | None, user_text: str, coach_text: str, seconds: float) -> Example`: 표현이면 `(session_id, expression_id)`로 `session_expressions.id`를 찾고, 단어면 그 vocabulary가 그 세션 것인지 확인. 없으면 `KeyError`.
  - `list_examples(session_id) -> list[Example]` (만든 순)
  - `add_reading(paragraph_id: int, user_text: str, seconds: float, corrections: list[Correction]) -> Reading`; `list_readings(session_id) -> list[Reading]` (최신 먼저; `corrections` NULL → None, "phrasing" 필터 삭제)
  - `add_summary(paragraph_id: int, user_text: str, feedback: SummaryFeedback, seconds: float) -> Summary`; `list_summaries(session_id)` (만든 순)

- [ ] **Step 1: impact.** `RecordRepo`.
- [ ] **Step 2: 테스트 추가 (실패)** — `tests/test_store.py`:

```python
def test_examples_point_at_an_expression_or_a_word_of_the_session(store):
    session = store.sessions.create(sample_draft(), seed_expressions(store, 1))
    e, w = session.content.expressions[0], session.content.vocabulary[0]
    ex = store.records.add_example(session.id, e.id, None, "I said", "Coach said", 4)
    wx = store.records.add_example(session.id, None, w.id, "word use", "echo", 2)
    assert [(x.expression_id, x.vocabulary_id) for x in store.records.list_examples(session.id)] == [(e.id, None), (None, w.id)]
    with pytest.raises(KeyError):
        store.records.add_example(session.id, 999, None, "x", "y", 0)
    assert store.sessions.delete(session.id) is not None
    assert store.records.list_examples(session.id) == []

def test_readings_and_summaries_hang_off_a_paragraph_and_go_with_the_session(store): ...  # paragraph_id, 최신 먼저 / 만든 순, cascade
```

- [ ] **Step 3: 실행 실패 → 구현 → PASS.** `uv run pytest tests/test_store.py -v`
- [ ] **Step 4: detect-changes, 커밋.** `git commit -m "feat: practice records reference paragraphs, expressions and words by id"`

---

### Task 4: 마이그레이션 v1 → v2

**Files:**
- Create: `backend/app/db/migrate.py`, `backend/tests/test_migrate.py`
- Modify: `backend/app/db/__init__.py` (Task 1의 자리 채움)

**Interfaces:**
- Produces `app/db/migrate.py`:
  - `is_v1(conn) -> bool`: `user_version == 0`이고 `sessions.content_json` 컬럼이 있음
  - `backup(path: Path) -> Path`: `path.with_name(f"{path.name}.bak-v1-{date.today():%Y-%m-%d}")`로 복사
  - `migrate_v1(conn, images_dir: Path | None) -> Report`; `Report(sessions: int, expressions: int, pictures_renamed: int, pictures_missing: int, readings_dropped: int, summaries_dropped: int, examples_dropped: int, orphan_files: int)`. 설계 문서 "마이그레이션" 1~10 그대로: DB 변경은 한 트랜잭션, 파일 rename은 커밋 뒤, 버린 행마다 `log.warning`, `settings`는 손대지 않음.
- `Database.__init__`: `is_v1` → `backup` → `migrate_v1` → `log.info(report)`. 아니고 테이블 없음 → `schema.create`.
- 테스트 헬퍼 `make_v1(path: Path, images_dir: Path) -> None`: Task 1 이전의 v1 DDL(현재 `app/db/__init__.py`의 `SCHEMA`를 테스트 파일에 복사)로 세션 2개(표현 5개씩, 한 phrase는 관사만 다르게 겹침), stars, notes, readings(1개는 단락 불일치), summaries, examples(표현 1, 단어 1), image_stats 2행, model_lists(`{"at":..,"options":[..]}`), topic_days, 그림 파일 2개(1개는 파일 없음)를 만든다.

- [ ] **Step 1: impact.** `Database`.
- [ ] **Step 2: `tests/test_migrate.py` 작성 (실패)**

```python
def test_a_v1_file_is_backed_up_and_comes_up_as_v2_with_everything_in_rows(tmp_path):
    path, images = tmp_path / "s.db", tmp_path / "images"
    make_v1(path, images)
    db = Database(path, images)
    assert list(tmp_path.glob("s.db.bak-v1-*"))
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} >= {"paragraphs", "vocabulary", "expressions", "session_expressions", "pictures"}
        assert not {r[0] for r in conn.execute("SELECT name FROM sqlite_master")} & {"stars", "notes", "image_stats", "sessions_v1"}
    [s2, s1] = db.sessions.list_all()
    got = db.sessions.get(s1.id)
    assert len(got.content.article.paragraphs) == 3 and len(got.content.expressions) == 5
    assert db.expressions.count() == 9  # 10 taught, one phrase shared across the two sessions
    assert db.sessions.get_note(s1.id).text == "my note"
    assert db.sessions.get_stars(s1.id) == Stars(expressions=[got.content.expressions[1].id], words=[got.content.vocabulary[2].id])

def test_pictures_become_rows_and_files_are_renamed_by_id(tmp_path): ...   # {id}.png 존재, image_stats 2행이 pictures에 (파일 없음), model NULL
def test_a_missing_picture_file_leaves_the_word_bare(tmp_path): ...        # Report.pictures_missing == 1, image None
def test_an_unmatched_reading_is_dropped_with_a_warning(tmp_path, caplog): ...  # readings_dropped == 1, 나머지 reading의 paragraph_id가 맞는 단락
def test_examples_find_their_expression_by_key_or_their_word(tmp_path): ...
def test_model_lists_topic_days_and_settings_keep_their_values(tmp_path): ...  # ModelList.fetched_at, options; get_daily_topics; settings에 SUMMARY_MODEL이 남아 있음
def test_orphan_files_are_counted_and_left_alone(tmp_path): ...               # Report.orphan_files == 1, 파일명 그대로
```

- [ ] **Step 3: 실행 실패 → 구현 → PASS.** `uv run pytest tests/test_migrate.py tests/test_store.py tests/test_schema.py -v`
- [ ] **Step 4: 실제 파일로 예행.** `cp backend/data/sessions.db <scratchpad>/real.db && cp -r backend/data/images <scratchpad>/images && cd backend && uv run python -c "from app.db import Database; Database('<scratchpad>/real.db', '<scratchpad>/images')"`. 로그의 Report와 설계 문서 "검증" 숫자 대조: sessions 7, expressions 38, pictures_renamed 70, pictures_missing 0, orphan_files 40, readings/summaries/examples dropped 0. dropped가 0이 아니면 매칭 규칙을 고치고 다시 돈다 (백업 → 재시도).
- [ ] **Step 5: detect-changes, 커밋.** `git commit -m "feat: migrate a v1 database and its picture files to schema v2 on start"`

---

### Task 5: 생성기·배제 목록·JobRunner

**Files:**
- Modify: `backend/app/generation/generator.py`, `backend/app/generation/exclusions.py`, `backend/app/generation/jobs.py`, `backend/tests/test_generator.py`, `backend/tests/test_exclusions.py`, `backend/tests/fake_claude.py`(payload에서 expressions 제거)

**Interfaces:**
- `Generator.generate(topic, on_progress=None, exclude: Exclusions | None = None) -> Draft`. `SESSION_SCHEMA`·`PROMPT_TEMPLATE`에서 expressions 항목 삭제, 번호 1·2로. `EXPRESSION_COUNT`는 남김(선택 개수).
- `Exclusions(words: tuple[str, ...] = ())`; `thin`, `taught(words: list[str]) -> list[str]`; `check_items` 도구 인자 `{"words": list[str]}`.
- `JobRunner(sessions: SessionRepo, expressions: ExpressionRepo, stages: StageRepo, executor: Executor | None = None)`. `_stage_history` 삭제: `stage_expected_seconds`는 `stages.recent(stage)`의 median, 끝난 job은 단계마다 `stages.add`. `_run`: `used = Exclusions(self._sessions.used_words())`; 생성 후 `picked = self._expressions.pick(EXPRESSION_COUNT, random.Random())`; `self._sessions.create(draft, [e.id for e in picked])`.
- `_illustrate(job, illustrator, session: Session)`: Task 6의 Illustrator 시그니처에 맞춤 (이 Task에서는 호출부만 바꿔 두고 Task 6에서 통과).

- [ ] **Step 1: impact.** `ClaudeGenerator`, `Exclusions`, `JobRunner`.
- [ ] **Step 2: 테스트 맞춤 (실패).** `test_generator.py`: `test_a_full_session_fits_the_schema_the_model_answers_in`은 `sample_draft().model_dump()`; `test_past_items_go_to_a_check_tool_not_the_prompt`·`test_check_items_names_close_variants_of_taught_items`는 단어만. `test_exclusions.py`: 단어만. 추가:

```python
def test_the_prompt_asks_for_no_expressions():
    prompt = ClaudeGenerator(model="m").build_prompt("t")
    assert "expressions" not in prompt and "1. article" in prompt and "2. vocabulary" in prompt
```

- [ ] **Step 3: 실행 실패 → 구현 → PASS.** `uv run pytest tests/test_generator.py tests/test_exclusions.py tests/test_progress.py -v`
- [ ] **Step 4: detect-changes, 커밋.** `git commit -m "refactor: the generator writes the article and words; expressions come from the corpus"`

---

### Task 6: 그림 흐름

**Files:**
- Create: `backend/app/pictures/files.py`
- Modify: `backend/app/pictures/painters.py`, `backend/app/pictures/illustrator.py`, `backend/app/wiring.py`, `backend/tests/test_illustrator.py`

**Interfaces:**
- Produces `app/pictures/files.py`: `PictureFiles(dir: Path)`; `name(picture_id: int) -> str` (`f"{picture_id}.png"`); `path(picture_id) -> Path`; `write(picture_id, png: bytes) -> None` (mkdir); `remove(picture_id: int | None) -> None` (missing_ok)
- Produces `painters.py`: `Drawn(png: bytes, model: str, seconds: float | None, cost: float | None)` frozen dataclass; `OnPicture = Callable[[int, Drawn], None]`; `Painter.paint(prompts, on_drawn=None, on_picture=None) -> list[Drawn | None]`; `PictureStats` Protocol `seconds(model) -> float | None` (`PictureLog`·`NoLog.record` 삭제, `NoStats`). OpenRouter: 그림 없고 cost만 온 경우는 로그만 (행 없음). Comfy: 배치 시간/장수를 각 `Drawn.seconds`에.
- Produces `illustrator.py`: `Illustrator(painter: Painter, pictures: PictureRepo, files: PictureFiles, style: str = "photo")`; `count(vocabulary: list[VocabularyItem]) -> int`; `illustrate(job_id: str, vocabulary: list[VocabularyItem], on_drawn: OnDrawn | None, on_picture: Callable[[int, PictureField, int], None]) -> None` (index, field, picture_id); `redraw(item: VocabularyItem, scene: Scene, style: str = "") -> int`; `redraw_example(item, style="") -> int`; `expected_seconds`. `discard` 삭제(라우트가 `PictureFiles.remove`).
- `wiring.py`: `build_services(settings, agent_dirs, pictures: PictureRepo | None, files: PictureFiles | None, efforts_of, speech_dir)`; `_illustrator(settings, pictures, files)`.
- `jobs.py` `_illustrate`: `on_picture=lambda i, field, pid: self._sessions.replace_picture(session.content.vocabulary[i].id, field, pid)`.

- [ ] **Step 1: impact.** `Illustrator`, `PictureLog`, `OpenRouterPainter`, `ComfyPainter`, `build_services`.
- [ ] **Step 2: 테스트 맞춤 (실패).** `test_illustrator.py`의 fake painter가 `Drawn`을 돌려주게. 바뀌는 단언: 파일명이 `{id}.png`, `pictures` 행 수 = 그린 장수, `on_picture(i, field, pid)`. `test_redraw_...`: 새 id, 옛 파일은 호출자가 `files.remove`. `test_openrouter_times_each_picture_and_keeps_what_it_cost`·`test_comfy_shares_the_batch_time...`: `Drawn.seconds`/`cost` 단언. 추가:

```python
def test_each_drawn_picture_is_one_row_and_one_file_named_by_the_row(tmp_path):
    db = Database(tmp_path / "s.db")
    files = PictureFiles(tmp_path / "images")
    landed = []
    Illustrator(FakePainter(), db.pictures, files).illustrate("j", sample_vocabulary(), None, lambda i, f, pid: landed.append((i, f, pid)))
    ids = [pid for _, _, pid in landed]
    assert sorted((tmp_path / "images").iterdir()) == sorted(files.path(pid) for pid in ids)
    assert db.pictures.stats()["fake"].seconds is not None
```

- [ ] **Step 3: 실행 실패 → 구현 → PASS.** `uv run pytest tests/test_illustrator.py -v`
- [ ] **Step 4: detect-changes, 커밋.** `git commit -m "refactor: one pictures row per drawn picture, files named by it"`

---

### Task 7: API와 조립

**Files:**
- Modify: `backend/app/api/schemas.py`, `backend/app/api/records.py`, `backend/app/api/sessions.py`, `backend/app/api/deps.py`, `backend/app/main.py`, `backend/tests/test_api.py`, 그 외 `create_app(...)`을 부르는 테스트(`test_live.py`, `test_speech.py`, `test_assessor.py`, `test_summary_feedback.py`, `test_example_feedback.py`)

**Interfaces:**
- `schemas.py`: `ExampleRequest(session_id: int, expression_id: int | None = None, vocabulary_id: int | None = None, user_text, coach_text, seconds=0)` + `model_validator`: 둘 중 하나만. `ReadingRequest(paragraph_id: int, user_text, seconds=0, corrections: list[Correction] = [])`. `SummaryRequest(paragraph_id: int, user_text, feedback, seconds=0)`. `SummaryFeedbackRequest`·`ParagraphRequest`는 텍스트 그대로.
- `deps.py`: `require_paragraph(db, paragraph_id) -> None` (404). `Files = Annotated[PictureFiles, Depends(_files)]` (`app.state.files`).
- `records.py`: 예문 추가 시 `KeyError` → 404 `"not taught in this session"`.
- `sessions.py`: `delete_session`: `ids = db.sessions.delete(id)`; None → 404; 아니면 `files.remove` 각각. `redraw_picture`: `pid = illustrator.redraw(...)`; `previous = db.sessions.replace_picture(item.id, field, pid, scene)`; `KeyError` → `files.remove(pid)` 후 404; 성공 시 `files.remove(previous)`. 응답은 `db.sessions.get(...)`의 그 item.
- `main.py`: `create_app(db, services, executor=None, rebuild=None, env=None, image_dir=None, catalog=None)`: `app.state.files = PictureFiles(image_dir or db.path.parent / "images")`; `JobRunner(db.sessions, db.expressions, db.stages, executor)`. `default_app`: `Database(path, images_dir)`, `build_services(..., db.pictures, PictureFiles(image_dir), ...)`.

- [ ] **Step 1: impact.** `create_app`, `delete_session`, `redraw_picture`, `add_example`, `add_reading`, `add_summary`.
- [ ] **Step 2: `test_api.py` 맞춤 (실패).** fixture `client`가 `seed_expressions`로 corpus 5개를 심음. 바뀌는 단언: `test_list_and_get`(paragraphs·expressions id), `test_stars_endpoint...`(id), `test_examples_stack...`(`expression_id`/`vocabulary_id`), `test_readings_...`(`paragraph_id`), `test_second_generation_receives_items_from_the_first`(단어만), `test_a_word_can_be_redrawn...`(`{id}.png`, 옛 파일 삭제), `test_pictures_are_drawn_after_the_text...`(pictures 행), `test_stage_times_of_a_finished_run_become_the_next_estimate`(StageRepo 경유). 추가:

```python
def test_an_example_for_an_expression_not_in_the_session_is_404(client): ...
def test_deleting_a_session_removes_its_picture_files(tmp_path): ...
def test_redraw_after_the_session_went_away_leaves_no_file(tmp_path): ...   # illustrator fake가 그리는 동안 삭제 → 404, images/ 비어 있음
def test_a_session_with_an_empty_corpus_has_no_expressions(tmp_path): ...
def test_stage_estimates_survive_a_restart(tmp_path): ...                   # 같은 경로로 Database 두 번
```

- [ ] **Step 3: 실행 실패 → 구현 → 전체 PASS.** `cd backend && uv run pytest -q` 전체 녹색.
- [ ] **Step 4: 앱 기동 확인.** `uv run uvicorn app.main:app --port 8001` 후 `curl -s localhost:8001/api/sessions | head -c 200`, 종료.
- [ ] **Step 5: detect-changes, 커밋.** `git commit -m "feat: api speaks in paragraph, expression and word ids; deleting a session removes its pictures"`

---

### Task 8: 프론트: 단락 id

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/components/ArticleTab.tsx`, `Paragraph.tsx`, `ReadAloud.tsx`, `Summarize.tsx`, `SummaryTab.tsx`, `frontend/src/lib/useReadingMarks.ts`, 해당 `.test.tsx`

**Interfaces:**
- `types.ts`: `interface Paragraph { id: number; text: string }`; `Article.paragraphs: Paragraph[]` (`body` 삭제); `Reading.paragraph_id: number`, `Summary.paragraph_id: number` (`session_id`·`paragraph` 삭제).
- `api.ts`: `addReading({ paragraph_id, user_text, seconds, corrections })`, `addSummary({ paragraph_id, user_text, feedback, seconds })`. `startReadAloud(paragraph: string, ...)`, `startSummary(paragraph: string)`, `summaryFeedback(paragraph: string, ...)` 텍스트 그대로.
- `ArticleTab`: `article.paragraphs` 직접 사용, 쪼개기 삭제. `pairSentences(paragraphs.map(p => p.text), ...)`. `Paragraph` props: `paragraph: Paragraph`; `summaries.filter(s => s.paragraph_id === p.id)`; `saved={marks.get(p.id)}`.
- `useReadingMarks(sessionId): Map<number, Shown[]>`.
- `ReadAloud`/`Summarize`: `paragraph: Paragraph` prop; 라이브 호출엔 `paragraph.text`, 저장엔 `paragraph.id`.
- `SummaryTab`: 라벨 = `content.article.paragraphs.find(p => p.id === s.paragraph_id)?.text` 앞 4단어.

- [ ] **Step 1: impact.** `Article`·`Reading`·`Summary`(`--file-path frontend/src/types.ts`), `ArticleTab`, `useReadingMarks`.
- [ ] **Step 2: 테스트 맞춤 (실패).** fixture `body: '...'` → `paragraphs: [{id: 1, text: ...}, ...]`; `ArticleTab.test` 71행 reading 헬퍼 `paragraph_id`; `ReadAloud.test` 100·127행 `addReading` 단언 `{ paragraph_id: 1, ... }`; `Summarize.test` 32행 `addSummary` `{ paragraph_id, ... }`; `SummaryTab.test` 라벨 단언.
- [ ] **Step 3: 실행 실패 → 구현 → PASS.** `cd frontend && npm test -- ArticleTab ReadAloud Summarize SummaryTab useReadingMarks`
- [ ] **Step 4: `npx tsc -b`** 타입 오류 0 (Task 9 영역의 오류는 허용, 목록만 남김).
- [ ] **Step 5: detect-changes, 커밋.** `git commit -m "feat: the article comes as paragraphs with ids; readings and summaries point at them"`

---

### Task 9: 프론트: 표현·단어 id, 별, 예문, 빈 corpus

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/lib/useStars.ts`, `frontend/src/pages/SessionPage.tsx`, `frontend/src/components/ExpressionsTab.tsx`, `VocabularyTab.tsx`, `Practice.tsx`, `SummaryTab.tsx`, 해당 테스트

**Interfaces:**
- `types.ts`: `Expression.id: number`, `VocabularyItem.id: number`; `Stars { expressions: number[]; words: number[] }`; `Example { id, created_at, expression_id: number | null, vocabulary_id: number | null, user_text, coach_text, seconds }`; `PracticeTarget` + `id: number` (kind와 함께 어느 테이블인지 정해짐); `practiceExpression(e)`/`practiceWord(v)`가 id를 채움.
- `api.addExample({ session_id, expression_id?, vocabulary_id?, user_text, coach_text, seconds })`.
- `useStars.toggle(kind: StarKind, id: number)`. `SessionPage`: `onToggleStar={(id) => toggle('expressions', id)}`.
- `ExpressionsTab`: `examples.filter(e => e.expression_id === item.id)`, `starred.includes(item.id)`; `items.length === 0`이면 `<p className="empty">No expressions yet: the corpus is empty. Add expressions to it and start a new session.</p>`.
- `VocabularyTab`: `examples.filter(e => e.vocabulary_id === item.id)`, 별 id.
- `Practice`: `target.kind === 'expression' ? { expression_id: target.id } : { vocabulary_id: target.id }`.
- `SummaryTab`: starred by id; 예문 라벨 = `content.expressions`/`content.vocabulary`에서 id로 찾은 phrase/word.

- [ ] **Step 1: impact.** `Expression`·`VocabularyItem`·`Stars`·`Example`(`--file-path frontend/src/types.ts`), `useStars`, `Practice`.
- [ ] **Step 2: 테스트 맞춤 (실패).** `useStars.test`(id), `ExpressionsTab.test` 48·65행, `VocabularyTab.test` 예문 필터, `Practice.test` 70행 `addExample` 단언, `SummaryTab.test` 40·69행, `SessionPage.test` fixture에 id. 추가 `ExpressionsTab.test`: `it('says the corpus is empty when a session has no expressions', ...)`.
- [ ] **Step 3: 실행 실패 → 구현 → 전체 PASS.** `cd frontend && npm test && npx tsc -b && npm run lint`
- [ ] **Step 4: detect-changes, 커밋.** `git commit -m "feat: stars and practice sentences point at expressions and words by id"`

---

### Task 10: 끝맺음

**Files:**
- Modify: `docs/superpowers/specs/2026-10-25-sqlite-schema-redesign-design.md` (상태 줄), `README.md`(데이터 폴더 설명이 있으면 `images/{id}.png`·백업 파일 언급)

- [ ] **Step 1: 두 스위트.** `cd backend && uv run pytest -q`, `cd frontend && npm test` 모두 녹색.
- [ ] **Step 2: 실제 데이터로 끝까지.** Task 4 Step 4의 복사본이 아니라 `docker compose up --build` 또는 로컬 기동으로 진짜 `backend/data/sessions.db` 마이그레이션. 백업 파일 생김 확인. 브라우저에서: 세션 열기, 별·메모·읽기·요약·예문 저장, 다시 그리기, 세션 하나 삭제 후 `backend/data/images` 파일 수 감소 확인. 문제가 있으면 백업으로 되돌리고(`cp sessions.db.bak-v1-* sessions.db`, 그림 파일명은 Report 로그로 되돌림) 고친다.
- [ ] **Step 3: 설계 문서 상태 줄을 "구현 완료 (날짜)"로.** detect-changes, 커밋 `git commit -m "docs: mark the schema v2 design as implemented"`.
- [ ] **Step 4: 브랜치 마무리.** `superpowers:finishing-a-development-branch`. main 병합 후 `scripts/bump-version patch` (minor로 올릴지는 owner가 정한다. `CLAUDE.md` Versioning).
