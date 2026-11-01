# 크레딧 트랜잭션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 태스크를 이 세션에서 직접 실행하고, 끝에 새 서브에이전트 리뷰를 한 번만 한다 (사용자가 정한 방식). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 크레딧을 쓰는 모든 기능을 "완수해야 차감"으로 바꾼다. 오류나 미완수는 0, 사용자가 멈춘 세션 생성은 절반이다.

**Architecture:** 차감은 `hold`(잔액에서 잡아 둠)로 시작해 `settle` 또는 `release`로 끝난다. 동기 경로는 `deps.paid` 문맥 관리자, 브라우저가 이어받는 음성 경로는 `deps.browser_round`와 hold 확인 REST, 세션 job은 `on_finished` 콜백이 그 끝을 맡는다. 앱 시작 때 남은 hold를 되돌려 프로세스 사망을 복구한다.

**Tech Stack:** FastAPI, SQLite 3.35+ (`RETURNING`, `DROP COLUMN`), React 19, vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-01-credit-transactions-design.md`. 결과표가 합격 기준이다.

## Global Constraints

- 브랜치 `feat/credit-transactions`에서 작업한다 (이 문서가 이미 그 위에 있다). `main`에는 `--ff-only`로 합치고, 그 뒤 `scripts/bump-version patch`만 쓴다. minor나 major는 올리지 않는다.
- 심볼을 고치기 전에 GitNexus `impact`(`node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .`), 커밋 전에 `node .gitnexus/run.cjs detect-changes --scope all --repo .`. `risk: UNKNOWN`은 텍스트 검색으로 확인한다. `deps.charge`는 CRITICAL이다 (유료 경로 9개가 직접 부른다). 전부 교체하고 전부 테스트로 고정한다.
- 커밋 메시지는 제목과 본문뿐이다. `Co-Authored-By`를 넣지 않는다.
- 새 Python 의존성도 npm 의존성도 없다. 새 셸 스크립트를 만들지 않는다.
- 가격과 기한은 `backend/app/credits.py`에만 적는다. 프런트는 `GET /api/me/credits`의 `prices`로 받고 숫자를 하드코딩하지 않는다.
- 운영자(`is_admin`)의 hold는 `None`이다. 행을 쓰지 않는다. `CreditRepo`의 `settle`, `release`, `await_browser`는 `None`을 받으면 아무 일도 하지 않는다.
- 검사 순서: 로그인(401), 세션 접근권과 만든 사람(404, 403), 기능이 켜져 있는지(503), hold(402).
- 402의 `detail`은 정확히 `Not enough credits: this needs {price} and you have {balance}.`이다.
- 409의 `detail`은 정확히 `This session is still being drawn. Cancel it on the progress bar: the session goes and half the price stays charged.`이다.
- 이벤트 발행은 `CreditRepo`만 한다. 잔액이 바뀌는 `grant`, `hold`, `release`, `give_back`, `as_kind`가 있는 `settle`이 커밋 뒤에 `AccountChange.CREDITS`를 발행한다. 잔액이 그대로인 `settle`, `confirm`, `await_browser`, 그리고 앱 시작 때의 `release_abandoned`는 발행하지 않는다.
- 코드와 주석, 테스트 이름, 화면 문구는 영어다. 함수 하나는 한 추상화 수준만 말한다 (`/home/humanoid/CLAUDE.md`).
- 백엔드 테스트: `cd backend && .venv/bin/pytest -q` (전체 약 3분 30초). 프런트: `cd frontend && npx vitest run` 과 `npx tsc -b --noEmit`. 시작 기준선은 백엔드 502 passed, 프런트 52 files / 431 tests passed다.
- 테스트는 따로 돌리고 결과를 읽은 뒤에 커밋한다. `;`로 잇거나 `tail -1`로 자르지 않는다.
- 운영 서버에서 Create session을 누르지 않는다. 실제 흐름 확인은 임시 백엔드로 한다. 비밀값을 출력하지 않는다.

## Review Focus

1. 일이 끝난 뒤 늦게 온 취소: 200이 그대로 나가고 세션이 남는다. (Task 4)
2. job이 실패했고 세션이 저장된 경우의 삭제: 409가 아니라 204이고 차감이 없다. (Task 4)
3. 기한이 지난 뒤 온 확인: 404이고 차감이 되살아나지 않는다. (Task 3)
4. 잔액 300에서 세션 두 개를 동시에 시작: 둘째는 `have 100`인 402, 첫째가 실패하면 300으로 돌아온다. (Task 4)
5. 운영자의 음성 회: 응답의 `hold`가 null이고 브라우저는 확인도 되돌림도 보내지 않는다. 운영자의 취소도 세션을 지운다. (Task 3, 4, 5)

---

### Task 1: 스키마 v14와 hold 원장

**Files:**
- Modify: `backend/app/credits.py`, `backend/app/db/schema.py`, `backend/app/db/credits.py`
- Test: `backend/tests/test_credits.py`, `backend/tests/test_schema.py`

**Interfaces:**
- Produces, in `app/credits.py`: `PRICES["session_cancelled"] == 100`, `CONFIRM_WINDOW = timedelta(minutes=3)`, `REPORT_WINDOW = timedelta(minutes=30)`.
- Produces, in `app/db/credits.py`:
  ```python
  class NotEnoughCredits(Exception):  # .need: int, .have: int

  class CreditRepo:
      def hold(self, user: User, kind: str, detail: str | None = None) -> int | None: ...
      def settle(self, hold: int | None, as_kind: str | None = None) -> None: ...
      def release(self, hold: int | None) -> None: ...
      def await_browser(self, hold: int | None, window: timedelta) -> None: ...
      def confirm(self, hold: int, user_id: int, window: timedelta) -> bool: ...
      def give_back(self, hold: int, user_id: int) -> bool: ...
      def release_abandoned(self) -> None: ...
  ```
- `charge`와 `refund`는 Task 4까지 그대로 둔다. 경로가 아직 쓴다.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_credits.py`에 더한다. `from datetime import timedelta`, `from app.credits import CONFIRM_WINDOW, PRICES, REPORT_WINDOW`, `from app.db.credits import NotEnoughCredits`를 가져온다.

```python
def funded(store, amount: int):
    mina = add_user(store, "mina@example.com")
    store.credits.grant(mina.id, amount, by=mina.id)
    return mina


def kinds(store, user) -> list[str]:
    return [e.kind for e in store.credits.recent(user.id)]


def test_a_hold_takes_the_price_at_once_and_reads_like_a_charge(store):
    mina = funded(store, 15)
    store.credits.hold(mina, "redraw", "sprawl")
    assert store.credits.balance(mina.id) == 5
    entry = store.credits.recent(mina.id)[0]
    assert (entry.amount, entry.kind, entry.detail) == (-10, "redraw", "sprawl")


def test_a_hold_the_balance_cannot_cover_says_what_is_missing_and_leaves_no_row(store):
    mina = funded(store, 3)
    with pytest.raises(NotEnoughCredits) as refused:
        store.credits.hold(mina, "redraw")
    assert (refused.value.need, refused.value.have) == (10, 3)
    assert kinds(store, mina) == ["grant"]


def test_a_settled_hold_stays_and_a_released_one_is_as_if_it_never_was(store):
    mina = funded(store, 30)
    store.credits.settle(store.credits.hold(mina, "redraw"))
    store.credits.release(store.credits.hold(mina, "redraw"))
    assert store.credits.balance(mina.id) == 20
    assert kinds(store, mina) == ["redraw", "grant"]


def test_a_release_cannot_undo_what_was_settled(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "redraw")
    store.credits.settle(hold)
    store.credits.release(hold)
    assert store.credits.balance(mina.id) == 0


def test_settling_as_a_cancelled_session_takes_half_and_keeps_the_topic(store):
    mina = funded(store, 200)
    store.credits.settle(store.credits.hold(mina, "session", "Trams"), as_kind="session_cancelled")
    assert store.credits.balance(mina.id) == 100
    entry = store.credits.recent(mina.id)[0]
    assert (entry.amount, entry.kind, entry.detail) == (-100, "session_cancelled", "Trams")
    assert PRICES["session_cancelled"] == 100


def test_the_admin_holds_nothing_and_every_step_on_that_does_nothing(store):
    boss = add_user(store, "boss@example.com", admin=True)
    hold = store.credits.hold(boss, "session", "Trams")
    assert hold is None
    store.credits.await_browser(hold, CONFIRM_WINDOW)
    store.credits.settle(hold)
    store.credits.release(hold)
    assert store.credits.recent(boss.id) == []


def test_two_holds_at_once_on_one_price_worth_of_balance_let_only_one_through(store):
    mina = funded(store, 10)
    results: list[str] = []
    gate = threading.Barrier(2)

    def go():
        gate.wait()
        try:
            store.credits.hold(mina, "redraw")
            results.append("held")
        except NotEnoughCredits:
            results.append("refused")

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["held", "refused"]
    assert store.credits.balance(mina.id) == 0


def test_a_browser_hold_stops_counting_when_its_window_passes(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(hold, timedelta(seconds=-1))
    assert store.credits.balance(mina.id) == 10
    assert kinds(store, mina) == ["grant"]
    assert store.credits.confirm(hold, mina.id, REPORT_WINDOW) is False
    assert store.credits.give_back(hold, mina.id) is False
    assert store.credits.balance(mina.id) == 10


def test_a_confirmed_round_is_paid_and_can_be_given_back_once(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(hold, CONFIRM_WINDOW)
    assert store.credits.confirm(hold, mina.id, REPORT_WINDOW) is True
    assert store.credits.balance(mina.id) == 0
    assert store.credits.give_back(hold, mina.id) is True
    assert store.credits.balance(mina.id) == 10
    assert store.credits.give_back(hold, mina.id) is False


def test_a_confirmed_round_is_final_once_the_report_window_passes(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(hold, CONFIRM_WINDOW)
    assert store.credits.confirm(hold, mina.id, timedelta(seconds=-1)) is True
    assert store.credits.give_back(hold, mina.id) is False
    assert store.credits.balance(mina.id) == 0


def test_nobody_else_can_confirm_or_give_back_a_hold(store):
    mina = funded(store, 10)
    other = add_user(store, "other@example.com")
    hold = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(hold, CONFIRM_WINDOW)
    assert store.credits.confirm(hold, other.id, REPORT_WINDOW) is False
    assert store.credits.give_back(hold, other.id) is False
    assert store.credits.balance(mina.id) == 0


def test_the_browser_cannot_touch_what_the_server_is_still_working_on(store):
    mina = funded(store, 10)
    hold = store.credits.hold(mina, "redraw")
    assert store.credits.confirm(hold, mina.id, REPORT_WINDOW) is False
    assert store.credits.give_back(hold, mina.id) is False
    assert store.credits.balance(mina.id) == 0


def test_a_released_hold_keeps_its_number_so_a_late_report_cannot_touch_the_next(store):
    mina = funded(store, 20)
    first = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(first, CONFIRM_WINDOW)
    assert store.credits.give_back(first, mina.id) is True
    second = store.credits.hold(mina, "practice_voice")
    store.credits.await_browser(second, CONFIRM_WINDOW)
    assert second != first
    assert store.credits.give_back(first, mina.id) is False
    assert store.credits.balance(mina.id) == 10


def test_holds_a_dead_process_left_are_released_and_settled_rows_stay(store):
    mina = funded(store, 30)
    store.credits.settle(store.credits.hold(mina, "redraw"))
    store.credits.hold(mina, "redraw")
    store.credits.release_abandoned()
    assert store.credits.balance(mina.id) == 20


def test_only_what_changes_the_balance_tells_the_account_to_read_it_again(store, recorder):
    mina = add_user(store, "mina@example.com")
    boss = add_user(store, "boss@example.com", admin=True)
    store.credits.grant(mina.id, 10, by=boss.id)
    hold = store.credits.hold(mina, "speech")
    store.credits.settle(hold)
    assert recorder.published == [(mina.id, AccountChange.CREDITS)] * 2
    store.credits.release(store.credits.hold(mina, "speech"))
    store.credits.hold(boss, "speech")
    assert recorder.published == [(mina.id, AccountChange.CREDITS)] * 4
```

`backend/tests/test_schema.py`에 더한다. conftest에서 `add_user`도 가져온다.

```python
def as_v13(path) -> None:
    """Rewrites a current file the way v13 kept it: a ledger of final rows."""
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("ALTER TABLE credits DROP COLUMN state")
        conn.execute("ALTER TABLE credits DROP COLUMN open_until")
        conn.execute("PRAGMA user_version = 13")
    conn.close()


def test_v13_brings_its_ledger_along_with_every_row_settled(tmp_path):
    path = tmp_path / "s.db"
    db = Database(path)
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, 50, by=mina.id)
    as_v13(path)
    db = Database(path)
    assert db.credits.balance(mina.id) == 50
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == schema.VERSION == 14
        assert [tuple(row) for row in conn.execute("SELECT state, open_until FROM credits")] == [("settled", None)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_credits.py tests/test_schema.py`
Expected: FAIL with `ImportError` on `CONFIRM_WINDOW`.

- [ ] **Step 3: Add the schema step in `backend/app/db/schema.py`**

`VERSION = 14`. `CREDITS` 상수는 고치지 않는다 (v13 업그레이드가 쓴다). `CREDITS` 뒤에 더하고 `SCHEMA` 끝에 `+ CREDIT_HOLDS`를 붙인다.

```python
# Added in v14: a charge is held while its work runs, then settled or released. `open_until` is
# how long the browser may still report on a round it opened by itself.
CREDIT_HOLDS = """
ALTER TABLE credits ADD COLUMN state TEXT NOT NULL DEFAULT 'settled' CHECK (state IN ('held', 'settled', 'released'));
ALTER TABLE credits ADD COLUMN open_until TEXT;
"""
```

`upgrade`에 `if version < 14: _credit_holds(conn)`를 더한다. `_credit_holds`는 `_credits`처럼 `conn.commit()`, `conn.execute("BEGIN")`, `_run(conn, CREDIT_HOLDS)`, `conn.execute("PRAGMA user_version = 14")` 순서다. 두 열이 함께 생기거나 함께 안 생겨야 한다.

- [ ] **Step 4: Add the prices and windows in `backend/app/credits.py`**

`PRICES`에 `"session_cancelled": 100`을 `"session"` 다음에 넣는다. `timedelta` 상수 둘을 주석과 함께 더한다.

```python
# How long the browser has to say a round connected: Gemini's two-minute window, its setup wait, and a margin.
CONFIRM_WINDOW = timedelta(minutes=3)
# How long after that it may still report the round dropped: the life of Gemini's token.
REPORT_WINDOW = timedelta(minutes=30)
```

- [ ] **Step 5: Implement the ledger in `backend/app/db/credits.py`**

- 세는 조건은 한 곳에 둔다. `?`에 지금 시각을 넣는다. `balance`와 `recent`가 쓴다.
  ```python
  _COUNTS = "(state = 'settled' OR (state = 'held' AND (open_until IS NULL OR open_until > ?)))"
  ```
- 시각은 지금처럼 `datetime.now(UTC).isoformat()` 문자열이다. `_now()`와 `_after(window)` 도우미를 둔다.
- `_add_row`에 `state: str = "settled"` 인자를 더하고 새 행의 id를 돌려준다.
- `hold`: 운영자는 `None`. 아니면 `BEGIN IMMEDIATE`, `_balance`, 모자라면 `NotEnoughCredits(price, balance)`, 아니면 `_add_row(..., state="held")`, 커밋 뒤 발행.
- 상태 전이는 `WHERE`가 지킨다. 각 메서드는 `UPDATE ... RETURNING user_id`로 일어났는지 안다.
  | 메서드 | 조건 | 바꾸는 값 | 발행 |
  |---|---|---|---|
  | `settle(hold)` | `id = ? AND state = 'held'` | `state = 'settled'` | 없음 |
  | `settle(hold, as_kind)` | 같음 | 위에 더해 `kind = as_kind`, `amount = -PRICES[as_kind]` | 있음 |
  | `release` | 같음 | `state = 'released'` | 있음 |
  | `await_browser` | 같음 | `open_until = _after(window)` | 없음 |
  | `confirm` | `id = ? AND user_id = ? AND state = 'held' AND open_until > ?` | `state = 'settled'`, `open_until = _after(window)` | 없음 |
  | `give_back` | `id = ? AND user_id = ? AND state IN ('held', 'settled') AND open_until > ?` | `state = 'released'` | 있음 |
  | `release_abandoned` | `state = 'held'` | `state = 'released'` | 없음 |

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest -q tests/test_credits.py tests/test_schema.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/credits.py backend/app/db/schema.py backend/app/db/credits.py backend/tests/test_credits.py backend/tests/test_schema.py
git commit -m "feat: a charge can be held, then settled or released"
```

---

### Task 2: 동기 유료 경로는 끝나야 값을 치른다

**Files:**
- Modify: `backend/app/api/deps.py`, `backend/app/api/coaches.py`, `backend/app/api/sessions.py`
- Test: `backend/tests/test_credits.py`, `backend/tests/test_speech.py`

**Interfaces:**
- Consumes: Task 1의 `CreditRepo.hold`, `settle`, `release`, `NotEnoughCredits`.
- Produces, in `app/api/deps.py`:
  ```python
  def held_or_402(db: Database, me: User, kind: str, detail: str | None = None) -> int | None: ...

  @contextmanager
  def paid(db: Database, me: User, kind: str, detail: str | None = None) -> Iterator[None]: ...
  ```
- `deps.charge`는 음성 경로와 세션 생성이 아직 쓴다. Task 4에서 지운다.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_credits.py`에서 `test_feedback_costs_10_and_a_failing_coach_keeps_the_charge`와 `test_a_new_picture_costs_10_names_the_word_and_a_failed_drawing_keeps_the_charge`를 아래로 바꾼다.

```python
def test_feedback_costs_10_and_a_failing_coach_takes_nothing(tmp_path):
    db, mina, me = paid_world(tmp_path, 25, example_coach=Coach())
    assert me.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 200
    assert db.credits.balance(mina.id) == 15
    me.app.state.services.example_coach = Coach(fail=True)
    assert me.post("/api/example/feedback", json=FEEDBACK_BODY).status_code == 502
    assert db.credits.balance(mina.id) == 15
    assert [(e.kind, e.detail) for e in db.credits.recent(mina.id)] == [("practice_feedback", "mitigate"), ("grant", None)]


class CrashingCoach:
    """Fails the way nothing in the route expects."""

    def feedback(self, *args):
        raise KeyError("candidates")


def test_an_error_no_route_expects_takes_nothing_either(tmp_path):
    db, mina, me = paid_world(tmp_path, 25, example_coach=CrashingCoach(), summary_coach=CrashingCoach())
    with pytest.raises(KeyError):
        me.post("/api/example/feedback", json=FEEDBACK_BODY)
    with pytest.raises(KeyError):
        me.post("/api/summary/feedback", json=PARAGRAPH | {"user_text": "It is words."})
    assert db.credits.balance(mina.id) == 25


def test_a_summary_coach_that_fails_takes_nothing(tmp_path):
    class Down:
        def feedback(self, paragraph, user_text):
            raise GenerationError("down")

    db, mina, me = paid_world(tmp_path, 25, summary_coach=Down())
    assert me.post("/api/summary/feedback", json=PARAGRAPH | {"user_text": "It is words."}).status_code == 502
    assert db.credits.balance(mina.id) == 25


def test_a_new_picture_costs_10_names_the_word_and_a_failed_drawing_takes_nothing(tmp_path):
    db, mina, me = paid_world(tmp_path, 220)
    sid = me.post("/api/sessions", json={"topic": "Trams"}).json()["session_id"]
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 503
    assert db.credits.balance(mina.id) == 20
    services = me.app.state.services
    services.illustrator, services.scene_writer = Drawer(db), object()
    word = me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).json()["word"]
    assert (db.credits.balance(mina.id), db.credits.recent(mina.id)[0].kind, db.credits.recent(mina.id)[0].detail) == (10, "redraw", word)
    services.illustrator = Drawer(db, fail=True)
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 502
    assert db.credits.balance(mina.id) == 10
    services.illustrator = Drawer(db)
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 200
    assert db.credits.balance(mina.id) == 0
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 402
    assert me.post(f"/api/sessions/{sid}/pictures/99", json={"face": "example"}).status_code == 404


def test_a_picture_for_a_session_deleted_while_drawing_takes_nothing(tmp_path):
    db, mina, me = paid_world(tmp_path, 210)
    sid = me.post("/api/sessions", json={"topic": "Trams"}).json()["session_id"]

    class DeletesFirst(Drawer):
        def redraw_example(self, item):
            db.sessions.delete(sid)
            return super().redraw_example(item)

    services = me.app.state.services
    services.illustrator, services.scene_writer = DeletesFirst(db), object()
    assert me.post(f"/api/sessions/{sid}/pictures/0", json={"face": "example"}).status_code == 404
    assert db.credits.balance(mina.id) == 10
```

`backend/tests/test_speech.py`에 더한다.

```python
def test_a_sentence_the_voice_could_not_read_takes_nothing(tmp_path):
    db = Database(tmp_path / "s.db")
    speaker = Speaker(CountingVoice(fail=True), tmp_path / "speech")
    app = create_app(db, Services(FakeGenerator(), speaker=speaker), InlineExecutor())
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, 1, by=mina.id)
    assert client_of(app, db, mina).post("/api/speech", json={"text": "It was flawed."}).status_code == 502
    assert db.credits.balance(mina.id) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_credits.py tests/test_speech.py`
Expected: the new tests FAIL on the balance after a 502.

- [ ] **Step 3: Add `held_or_402` and `paid` in `backend/app/api/deps.py`**

`held_or_402`는 `db.credits.hold`를 부르고 `NotEnoughCredits`를 지금의 402 문구로 바꾼다 (`e.need`, `e.have`). `charge`는 Task 4까지 그대로 둔다.

```python
@contextmanager
def paid(db: Database, me: User, kind: str, detail: str | None = None) -> Iterator[None]:
    """The block's work is paid for only if it ends normally; any exception gives the price back.
    A failure of the ledger itself is logged, not raised: the row goes back when the app next starts."""
    hold = held_or_402(db, me, kind, detail)
    try:
        yield
    except BaseException:
        _quietly(db.credits.release, hold)
        raise
    _quietly(db.credits.settle, hold)
```

`_quietly(step, hold)`는 `sqlite3.Error`만 잡아 `log.exception`으로 남긴다. 이 파일에 `log = logging.getLogger(__name__)`을 더한다.

- [ ] **Step 4: Move the routes onto `paid`**

- `summary_feedback`, `example_feedback`: `charge(...)`와 `try` 블록을 `with paid(db, me, kind, detail):` 안의 `try`로 바꾼다. 503 검사는 그 앞에 둔다.
- `speech`: 응답을 만드는 부분을 private `_read_aloud(speaker, text) -> Response`로 뺀다 (`GenerationError`를 `failed`로 바꾸는 것까지). 캐시에 있으면 그대로 부르고, 없으면 `with paid(db, me, "speech", " ".join(body.text.split())[:40]):` 안에서 부른다.
- `redraw_picture`: 검사들 뒤의 그리기와 저장(`api/sessions.py:173-189`)을 private `_draw_again(db, illustrator, writer, files, item, face) -> VocabularyItem`로 뺀다. 경로는 `with paid(db, me, "redraw", item.word): return _draw_again(...)`만 남긴다.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest -q tests/test_credits.py tests/test_speech.py tests/test_session_access.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/coaches.py backend/app/api/sessions.py backend/tests/test_credits.py backend/tests/test_speech.py
git commit -m "feat: a paid request that fails takes nothing"
```

---

### Task 3: 음성 경로의 hold와 브라우저 보고

**Files:**
- Modify: `backend/app/api/deps.py`, `backend/app/api/coaches.py`, `backend/app/api/credits.py`, `backend/app/api/schemas.py`
- Test: `backend/tests/test_credits.py`

**Interfaces:**
- Consumes: Task 1의 `await_browser`, `confirm`, `give_back`, `CONFIRM_WINDOW`, `REPORT_WINDOW`. Task 2의 `held_or_402`.
- Produces:
  ```python
  def browser_round(db: Database, me: User, kind: str, detail: str | None, start: Callable[[], dict]) -> dict: ...  # app/api/deps.py
  ```
  - `LiveSession.hold: int | None = None`, `AssessorSession.hold: int | None = None`.
  - `POST /api/me/credits/holds/{hold}/confirm` 204 또는 404.
  - `DELETE /api/me/credits/holds/{hold}` 204 또는 404.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_credits.py` 끝에 더한다. `VOICE_ROUTES`가 `WORD`와 `PARAGRAPH`를 읽으므로 그 아래여야 한다. `from app.net import HttpError`를 가져온다.

```python
class DownRound:
    def start(self, *args, **values) -> dict:
        raise HttpError(502, "down")


class DownAssessor:
    def session(self) -> dict:
        raise HttpError(502, "down")


VOICE_ROUTES = [("/api/example/sessions", WORD), ("/api/summary/sessions", PARAGRAPH), ("/api/read-aloud/sessions", PARAGRAPH)]


@pytest.mark.parametrize("path,body", VOICE_ROUTES)
def test_a_voice_round_the_provider_refuses_takes_nothing(tmp_path, path, body):
    agents = {"example": DownRound(), "read-aloud": DownRound()}
    db, mina, me = paid_world(tmp_path, 10, agents=agents, transcriber=DownRound())
    assert me.post(path, json=body).status_code == 502
    assert db.credits.balance(mina.id) == 10


def test_an_assessor_token_the_provider_refuses_takes_nothing(tmp_path):
    db, mina, me = paid_world(tmp_path, 5, assessor=DownAssessor())
    assert me.get("/api/assessor/token").status_code == 502
    assert db.credits.balance(mina.id) == 5


@pytest.mark.parametrize("path,body", VOICE_ROUTES)
def test_a_voice_round_hands_over_its_hold_which_the_browser_settles_or_gives_back(tmp_path, path, body):
    agents = {"example": LiveRound(), "read-aloud": LiveRound()}
    db, mina, me = paid_world(tmp_path, 10, agents=agents, transcriber=LiveRound())
    hold = me.post(path, json=body).json()["hold"]
    assert db.credits.balance(mina.id) == 0
    assert me.post(f"/api/me/credits/holds/{hold}/confirm").status_code == 204
    assert db.credits.balance(mina.id) == 0
    assert me.delete(f"/api/me/credits/holds/{hold}").status_code == 204
    assert db.credits.balance(mina.id) == 10
    assert me.delete(f"/api/me/credits/holds/{hold}").status_code == 404


def test_the_assessor_token_carries_its_hold_too(tmp_path):
    db, mina, me = paid_world(tmp_path, 5, assessor=Assessor())
    hold = me.get("/api/assessor/token").json()["hold"]
    assert me.delete(f"/api/me/credits/holds/{hold}").status_code == 204
    assert db.credits.balance(mina.id) == 5


def test_a_round_never_confirmed_comes_back_and_a_late_confirm_cannot_revive_it(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.deps.CONFIRM_WINDOW", timedelta(seconds=-1))
    db, mina, me = paid_world(tmp_path, 10, agents={"example": LiveRound()})
    hold = me.post("/api/example/sessions", json=WORD).json()["hold"]
    assert db.credits.balance(mina.id) == 10
    assert me.post(f"/api/me/credits/holds/{hold}/confirm").status_code == 404
    assert db.credits.balance(mina.id) == 10


def test_nobody_else_can_report_on_my_hold(tmp_path):
    db, mina, me = paid_world(tmp_path, 10, agents={"example": LiveRound()})
    hold = me.post("/api/example/sessions", json=WORD).json()["hold"]
    other = client_of(me.app, db, add_user(db, "other@example.com"))
    assert other.post(f"/api/me/credits/holds/{hold}/confirm").status_code == 404
    assert other.delete(f"/api/me/credits/holds/{hold}").status_code == 404
    assert db.credits.balance(mina.id) == 0


def test_the_browser_cannot_give_back_what_the_server_is_working_on(tmp_path):
    db, mina, me = paid_world(tmp_path, 10)
    hold = db.credits.hold(mina, "redraw")
    assert me.delete(f"/api/me/credits/holds/{hold}").status_code == 404
    assert db.credits.balance(mina.id) == 0


def test_the_admins_round_has_no_hold(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator(), agents={"example": LiveRound()}), InlineExecutor())
    assert admin_client(app).post("/api/example/sessions", json=WORD).json()["hold"] is None
```

`test_each_coach_takes_its_own_price_and_then_refuses`, `test_the_assessor_token_costs_5`, `test_hearing_the_coach_is_charged_each_time`는 고치지 않고 그대로 통과해야 한다. hold는 잔액에서 빠지고 내역에 보이기 때문이다.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_credits.py`
Expected: the new tests FAIL with `KeyError: 'hold'` or on the balance after a 502.

- [ ] **Step 3: Implement `browser_round` in `backend/app/api/deps.py`**

`held_or_402`, `start()`를 부르고 어떤 예외든 되돌린 뒤 다시 던진다. 성공하면 `db.credits.await_browser(hold, CONFIRM_WINDOW)`를 부르고 `{**session, "hold": hold}`를 돌려준다. 독스트링: `A round the browser opens by itself: the price stays held until it says the round connected.` `CONFIRM_WINDOW`는 함수 안에서 모듈 전역으로 읽어야 monkeypatch가 듣는다.

- [ ] **Step 4: Move the voice routes onto `browser_round`**

`backend/app/api/coaches.py`의 `start_read_aloud`(`"read_aloud_voice"`, detail None), `start_summary`(`"summary_voice"`, None), `start_example`(`"practice_voice"`, `body.word`), `assessor_token`(`"read_aloud_token"`, None). 제공자 호출과 `HttpError`를 `failed`로 바꾸는 부분은 `start` 콜러블 안에 둔다. `start_summary`와 `assessor_token`은 `start_live`처럼 private 도우미(`_start_transcriber`, `_assessor_session`)를 둔다.

- [ ] **Step 5: Add the schema fields and the two routes**

`backend/app/api/schemas.py`의 `LiveSession`, `AssessorSession`에 `hold: int | None = None`을 더한다. `backend/app/api/credits.py`에 경로 둘을 더한다. `db.credits.confirm(hold, me.id, REPORT_WINDOW)`와 `db.credits.give_back(hold, me.id)`가 False면 `HTTPException(404, "hold not found")`, 아니면 `Response(status_code=204)`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest -q tests/test_credits.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/coaches.py backend/app/api/credits.py backend/app/api/schemas.py backend/tests/test_credits.py
git commit -m "feat: a voice round stays held until the browser says it connected"
```

---

### Task 4: 세션 job의 값, 취소, 재시작

**Files:**
- Modify: `backend/app/generation/jobs.py`, `backend/app/pictures/illustrator.py`, `backend/app/api/sessions.py`, `backend/app/api/schemas.py`, `backend/app/api/deps.py`, `backend/app/db/credits.py`, `backend/app/main.py`
- Test: `backend/tests/test_jobs.py`, `backend/tests/test_illustrator.py`, `backend/tests/test_credits.py`

**Interfaces:**
- Consumes: `held_or_402`, `CreditRepo.settle(hold, as_kind)`, `release`, `release_abandoned`.
- Produces:
  ```python
  # app/generation/jobs.py
  class Job:  # 새 필드: spent: bool = False, pictures_missing: bool = False
  class JobRunner:
      def start(self, topic, generator, illustrator=None, created_by=None, on_finished: Callable[[Job], None] | None = None) -> Job: ...
      def drawing(self, session_id: int) -> bool: ...
  # app/pictures/illustrator.py
  class Illustrator:
      def illustrate(...) -> int: ...  # 그리지 못한 장수
  ```
  - `JobStatus.spent: bool`.
- Removes: `CreditRepo.charge`, `CreditRepo.refund`, `deps.charge`, `start`의 `on_lost`, `JobRunner._tell_if_lost`.

- [ ] **Step 1: Write the failing job tests**

`backend/tests/test_jobs.py`의 255행 이후 `lost` 테스트들을 고친다. 모두 `on_finished=finished.append`를 쓴다.

| 지금 테스트 | 바꿀 이름 | 단언 |
|---|---|---|
| `test_a_job_that_dies_of_anything_is_failed_and_reported_lost` | `test_a_job_that_dies_of_anything_is_failed_and_reported` | `finished == [job]` |
| `test_a_failure_the_generator_reports_is_lost_too` | `test_a_failure_the_generator_reports_is_reported_too` | `finished == [job]` |
| `test_a_refund_that_fails_does_not_take_the_job_down` | `test_telling_of_the_end_can_fail_without_taking_the_job_down` | `job.status == "failed"` |
| `test_a_job_the_executor_refuses_is_failed_and_reported_lost` | `test_a_job_the_executor_refuses_is_failed_and_reported` | `finished == [job]` |

나머지 넷은 지우고 아래로 바꾼다.

```python
class Draws:
    """Stands in for the illustrator: `during` runs while it draws, then it fails or reports what did not come back."""

    def __init__(self, missing=0, error=None, during=None):
        self.missing, self.error, self.during = missing, error, during

    def expected_seconds(self, count):
        return None

    def count(self, words, scenes):
        return 1

    def illustrate(self, job_id, words, on_done, on_picture, scenes, on_figure):
        if self.during:
            self.during(job_id, on_picture)
        on_done(1)
        if self.error:
            raise self.error
        return self.missing


def test_every_finished_job_is_reported_once(tmp_path):
    db = Database(tmp_path / "s.db")
    finished = []
    job = runner_over(db).start("Trams", Recording(), on_finished=finished.append)
    assert job.status == "done" and job.spent is True and finished == [job]


def test_a_job_cancelled_in_the_queue_calls_nothing_and_has_spent_nothing(tmp_path):
    db = Database(tmp_path / "s.db")

    class Queue:
        def submit(self, fn, /, *args):
            self.waiting = (fn, args)

    queue = Queue()
    runner = JobRunner(db.sessions, db.expressions, db.stages, queue)
    generator, finished = Recording(), []
    job = runner.start("Trams", generator, on_finished=finished.append)
    runner.close(job.id)
    fn, args = queue.waiting
    fn(*args)
    assert job.status == "cancelled" and job.spent is False
    assert generator.excluded == [] and finished == [job]


def test_a_cancel_before_the_session_is_saved_has_spent_claude(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    finished = []

    class CancelsItself:
        """With InlineExecutor the job runs inside start(), so the one open job is this one."""

        def generate(self, topic, on_progress=None, exclude=None):
            runner.close(runner.open()[0].id)
            on_progress(Progress(Stage.SEARCHING, 1))  # raises Cancelled
            return sample_draft()

    job = runner.start("Trams", CancelsItself(), on_finished=finished.append)
    assert job.status == "cancelled" and job.session_id is None and job.spent is True
    assert finished == [job]


def test_a_cancel_the_generator_never_hears_of_saves_nothing(tmp_path):
    db = Database(tmp_path / "s.db")
    runner = runner_over(db)

    class FinishesAnyway:
        def generate(self, topic, on_progress=None, exclude=None):
            runner.close(runner.open()[0].id)
            return sample_draft()

    job = runner.start("Trams", FinishesAnyway())
    assert job.status == "cancelled" and job.session_id is None


def test_a_cancel_while_the_pictures_are_drawn_deletes_the_session_and_its_files(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    files = PictureFiles(db.images_dir)
    finished, saved = [], {}

    def landing_then_cancelling(job_id, on_picture):
        picture_id = db.pictures.add(None, None, None)
        files.write(picture_id, b"PNG")
        on_picture(0, "example_image", picture_id)
        saved["session"] = runner.get(job_id).session_id
        runner.close(job_id)

    job = runner.start("Trams", Recording(), Draws(during=landing_then_cancelling), on_finished=finished.append)
    assert job.status == "cancelled" and job.session_id is None and job.spent is True
    assert db.sessions.get(saved["session"]) is None
    assert list(db.images_dir.iterdir()) == []
    assert finished == [job]


def test_a_cancel_after_the_last_progress_report_still_counts(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)

    class CancelsLast(Draws):
        def illustrate(self, job_id, words, on_done, on_picture, scenes, on_figure):
            on_done(1)
            runner.close(job_id)
            return 0

    job = runner.start("Trams", Recording(), CancelsLast())
    assert job.status == "cancelled" and job.session_id is None


def test_a_job_that_dies_after_its_session_is_saved_is_failed_and_keeps_it(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    finished = []
    job = runner_over(db).start("Trams", Recording(), Draws(error=OSError("No space left on device")), on_finished=finished.append)
    assert job.status == "failed" and "No space left" in job.error
    assert job.session_id is not None and db.sessions.get(job.session_id) is not None
    assert finished == [job]


@pytest.mark.parametrize(
    "draws,missing",
    [(Draws(), False), (Draws(missing=2), True), (Draws(error=GenerationError("openrouter down")), True)],
)
def test_a_job_knows_whether_every_picture_came_back(tmp_path, draws, missing):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    job = runner_over(db).start("Trams", Recording(), draws)
    assert job.status == "done" and job.pictures_missing is missing


def test_drawing_names_only_a_running_job_that_saved_that_session(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    runner = runner_over(db)
    seen = {}

    def look(job_id, on_picture):
        sid = runner.get(job_id).session_id
        seen.update(sid=sid, during=runner.drawing(sid), other=runner.drawing(sid + 1))

    runner.start("Trams", Recording(), Draws(during=look))
    assert seen["during"] is True and seen["other"] is False
    assert runner.drawing(seen["sid"]) is False
```

`import pytest`를 파일 맨 위에 더한다. `backend/tests/test_illustrator.py`에 더한다.

```python
def test_illustrate_says_how_many_pictures_did_not_come_back(tmp_path):
    words = sample_draft().vocabulary
    short, _, _ = illustrator_for(tmp_path / "short", FakePainter(blank={1, 3}))
    assert short.illustrate("j", words, None, landing([])) == 2
    whole, _, _ = illustrator_for(tmp_path / "whole")
    assert whole.illustrate("j", words, None, landing([])) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_jobs.py tests/test_illustrator.py`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'on_finished'`.

- [ ] **Step 3: Implement the runner in `backend/app/generation/jobs.py` and `backend/app/pictures/illustrator.py`**

- `Illustrator.illustrate`는 `paint`가 돌려준 목록에서 `None`을 세어 돌려준다. 기존 로그는 그대로다.
- `Job`에 두 필드를 더한다.
- `on_lost`를 `on_finished`로, `_tell_if_lost`를 `_tell_finished`로 바꾼다. 조건 없이 부르고 예외는 지금처럼 로그만 남긴다. `start`의 `except` 분기도 같다.
- `_run`은 이 순서만 말한다.
  ```python
  def _run(self, job, generator, illustrator, on_finished):
      self._generate(job, generator, illustrator)
      self._discard_if_cancelled(job)
      self._tell_finished(job, on_finished)
  ```
- `_generate`: `try` 첫 줄에서 `job.status == "cancelled"`이면 `return`. `generator.generate` 바로 앞에서 `job.spent = True`. `if illustrator:` 블록 뒤, `job.finish()` 앞에서 `if job.status == "cancelled": raise Cancelled`.
- `_illustrate`: `job.pictures_missing = bool(illustrator.illustrate(...))`. `except GenerationError`에서도 `True`로 한다.
- `_discard_if_cancelled(job)`: 취소됐고 `session_id`가 있으면 `self._sessions.delete(session_id)`, 돌려받은 picture id마다 `self._sources.drop` (`_sources`가 None이면 건너뛴다), 예외는 `log.exception`, 끝에 `job.session_id = None`.
- `drawing(session_id)`: 잠금 안에서 `status == "running"`이고 `session_id`가 같은 job이 있는지.

- [ ] **Step 4: Run the job tests to verify they pass**

Run: `cd backend && .venv/bin/pytest -q tests/test_jobs.py tests/test_illustrator.py`
Expected: PASS.

- [ ] **Step 5: Write the failing session billing tests**

`backend/tests/test_credits.py`에 더한다. `from tests.test_api import DeferredExecutor`도 가져온다. `test_a_failed_generation_gives_the_200_back_as_a_refund`는 `test_a_failed_generation_costs_nothing`으로 이름을 바꾸고 마지막 단언을 `[e.kind for e in db.credits.recent(mina.id)] == ["grant"]`로 고친다. `test_the_admins_failed_generation_writes_no_refund`는 `test_the_admins_failed_generation_writes_nothing`으로 이름만 바꾼다.

```python
class Pictures:
    """Stands in for the illustrator: `during` runs while it draws, then it fails or reports what did not come back."""

    def __init__(self, missing=0, error=None, during=None):
        self.missing, self.error, self.during = missing, error, during

    def expected_seconds(self, count):
        return None

    def count(self, words, scenes):
        return 1

    def illustrate(self, job_id, words, on_drawn, on_picture, scenes, on_figure):
        if self.during:
            self.during(job_id)
        on_drawn(1)
        if self.error:
            raise self.error
        return self.missing


def make_session(me) -> dict:
    return me.post("/api/sessions", json={"topic": "Trams"}).json()


def queued_world(tmp_path, balance: int, generator=None):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    executor = DeferredExecutor()
    app = create_app(db, Services(generator or FakeGenerator()), executor)
    mina = add_user(db, "mina@example.com")
    db.credits.grant(mina.id, balance, by=mina.id)
    return db, mina, client_of(app, db, mina), executor


def test_a_session_with_every_picture_costs_200_and_stays(tmp_path):
    db, mina, me = paid_world(tmp_path, 250, illustrator=Pictures())
    job = make_session(me)
    assert job["status"] == "done" and db.credits.balance(mina.id) == 50
    assert me.get(f"/api/sessions/{job['session_id']}").status_code == 200


@pytest.mark.parametrize(
    "pictures,status",
    [
        (Pictures(missing=1), "done"),
        (Pictures(error=GenerationError("openrouter down")), "done"),
        (Pictures(error=OSError("No space left on device")), "failed"),
    ],
)
def test_a_session_short_of_what_it_promised_stays_and_costs_nothing(tmp_path, pictures, status):
    db, mina, me = paid_world(tmp_path, 200, illustrator=pictures)
    job = make_session(me)
    assert job["status"] == status and job["session_id"] is not None
    assert db.credits.balance(mina.id) == 200
    assert [e.kind for e in db.credits.recent(mina.id)] == ["grant"]
    assert me.get(f"/api/sessions/{job['session_id']}").status_code == 200


def test_cancelling_while_the_pictures_are_drawn_deletes_the_session_and_costs_half(tmp_path):
    db, mina, me = paid_world(tmp_path, 200)
    me.app.state.services.illustrator = Pictures(during=lambda job_id: me.delete(f"/api/jobs/{job_id}"))
    job = make_session(me)
    assert job["status"] == "cancelled" and job["session_id"] is None
    assert me.get("/api/sessions").json() == []
    assert db.credits.balance(mina.id) == 100
    entry = db.credits.recent(mina.id)[0]
    assert (entry.amount, entry.kind, entry.detail) == (-100, "session_cancelled", "Trams")


def test_cancelling_after_claude_was_called_costs_half_even_before_the_session_is_saved(tmp_path):
    db, mina, me = paid_world(tmp_path, 200)

    class CancelsWhileWriting(FakeGenerator):
        def generate(self, topic, on_progress=None, exclude=None):
            me.delete(f"/api/jobs/{me.get('/api/jobs').json()[0]['id']}")
            return super().generate(topic, on_progress, exclude)  # its progress report raises Cancelled

    me.app.state.services.generator = CancelsWhileWriting()
    assert make_session(me)["status"] == "cancelled"
    assert db.credits.balance(mina.id) == 100


def test_cancelling_a_job_still_in_the_queue_costs_nothing(tmp_path):
    db, mina, me, executor = queued_world(tmp_path, 200)
    job = make_session(me)
    assert me.get(f"/api/jobs/{job['id']}").json()["spent"] is False
    me.delete(f"/api/jobs/{job['id']}")
    executor.run()
    assert db.credits.balance(mina.id) == 200


def test_the_second_session_at_once_is_refused_and_the_firsts_failure_gives_all_back(tmp_path):
    db, mina, me, executor = queued_world(tmp_path, 300, FailingGenerator())
    make_session(me)
    second = me.post("/api/sessions", json={"topic": "Boats"})
    assert second.status_code == 402
    assert second.json()["detail"] == "Not enough credits: this needs 200 and you have 100."
    executor.run()
    assert db.credits.balance(mina.id) == 300


def test_a_cancel_after_the_job_is_done_is_too_late(tmp_path):
    db, mina, me = paid_world(tmp_path, 200)
    job = make_session(me)
    assert me.delete(f"/api/jobs/{job['id']}").json()["status"] == "done"
    assert db.credits.balance(mina.id) == 0
    assert me.get(f"/api/sessions/{job['session_id']}").status_code == 200


def test_the_admins_cancelled_session_goes_too_and_writes_nothing(tmp_path):
    db = Database(tmp_path / "s.db")
    seed_expressions(db, EXPRESSION_COUNT)
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    admin = admin_client(app)
    app.state.services.illustrator = Pictures(during=lambda job_id: admin.delete(f"/api/jobs/{job_id}"))
    assert make_session(admin)["status"] == "cancelled"
    assert admin.get("/api/sessions").json() == []
    assert db.credits.recent(db.accounts.by_email("admin@example.com").id) == []


def test_a_session_still_being_drawn_cannot_be_deleted(tmp_path):
    db, mina, me = paid_world(tmp_path, 200)
    answers = []

    def try_to_delete(job_id):
        sid = me.get(f"/api/jobs/{job_id}").json()["session_id"]
        answers.append(me.delete(f"/api/sessions/{sid}"))

    me.app.state.services.illustrator = Pictures(during=try_to_delete)
    job = make_session(me)
    assert answers[0].status_code == 409
    assert answers[0].json()["detail"] == "This session is still being drawn. Cancel it on the progress bar: the session goes and half the price stays charged."
    assert job["status"] == "done" and db.credits.balance(mina.id) == 0
    assert me.delete(f"/api/sessions/{job['session_id']}").status_code == 204
    assert db.credits.balance(mina.id) == 0  # a finished session stays paid for


def test_a_session_whose_job_failed_can_be_deleted_and_stays_free(tmp_path):
    db, mina, me = paid_world(tmp_path, 200, illustrator=Pictures(error=OSError("disk")))
    job = make_session(me)
    assert me.delete(f"/api/sessions/{job['session_id']}").status_code == 204
    assert db.credits.balance(mina.id) == 200


def test_a_restart_gives_back_what_the_dead_process_held(tmp_path):
    db, mina, _ = paid_world(tmp_path, 200)
    db.credits.hold(mina, "session", "Trams")
    assert db.credits.balance(mina.id) == 0
    create_app(db, Services(FakeGenerator()), InlineExecutor())
    assert db.credits.balance(mina.id) == 200
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_credits.py`
Expected: the new tests FAIL. 경로가 아직 `on_lost`를 넘기므로 `TypeError`도 난다.

- [ ] **Step 7: Bill the job in `backend/app/api/sessions.py`**

```python
def _bill_session(db: Database, hold: int | None, job: Job) -> None:
    """Paid in full only with every picture on it; half when its maker stopped it after Claude was called; else nothing."""
    if job.status == "done" and not job.pictures_missing:
        db.credits.settle(hold)
    elif job.status == "cancelled" and job.spent:
        db.credits.settle(hold, as_kind="session_cancelled")
    else:
        db.credits.release(hold)
```

- `create_session`: `hold = held_or_402(db, me, "session", topic)`, `on_finished=lambda job: _bill_session(db, hold, job)`. `PRICES` import가 더 쓰이지 않으면 지운다.
- `delete_session`: `jobs: Jobs` 인자를 더하고, `require_creator` 다음에 `jobs.drawing(session_id)`이면 위의 409를 던진다.
- `status_of`: `spent=job.spent`. `backend/app/api/schemas.py`의 `JobStatus`에 `spent: bool`.

- [ ] **Step 8: Release what a dead process left, and remove the old charge**

- `backend/app/main.py`의 `create_app`에서 `app.state.db = db` 다음에 `db.credits.release_abandoned()`. 주석: `# Nothing can still be working on a hold when the app starts; these were left by the process before.`
- `deps.charge`, `PRICES` import, `CreditRepo.charge`, `CreditRepo.refund`를 지운다.
- `backend/tests/test_credits.py`에서 지운 메서드를 쓰는 테스트를 지운다: `test_a_charge_takes_the_price_and_names_what_it_was_for`, `test_a_charge_the_balance_cannot_cover_leaves_no_row`, `test_the_admin_is_never_charged_and_nothing_is_written`, `test_a_refund_is_a_positive_row_of_its_own_kind`, `test_two_charges_at_once_on_one_price_worth_of_balance_let_only_one_through`, `test_every_row_tells_the_account_to_read_its_credits_again`. `test_my_credits_show_the_balance_the_prices_and_the_last_charges`의 `db.credits.charge(mina, "redraw", "sprawl")`는 `db.credits.settle(db.credits.hold(mina, "redraw", "sprawl"))`로 바꾼다.

- [ ] **Step 9: Run the whole backend suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: 전부 PASS, 실패 0. `test_api.py`의 `test_a_cancelled_job_stops_and_saves_nothing`과 `test_a_session_still_goes_out_when_the_pictures_fail`은 고치지 않고 통과해야 한다.

- [ ] **Step 10: Commit**

```bash
git add backend
git commit -m "feat: a session is paid for only when finished, half when its maker stops it"
```

---

### Task 5: 브라우저 전송 계층

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/lib/live/transport.ts`, `frontend/src/lib/live/geminiWebsocket.ts`, 그리고 `tsc`가 가리키는 테스트 픽스처
- Test: `frontend/src/lib/live/geminiWebsocket.test.ts`

**Interfaces:**
- Consumes: Task 3의 hold 경로.
- Produces:
  ```ts
  // types.ts
  interface LiveSession { url: string; setup: Record<string, unknown>; hold: number | null }
  interface AssessorSession { token: string; region: string; word_score: number; hold: number | null }
  // api.ts: neither rejects, and neither sends the user to the login page
  confirmHold(hold: number): Promise<unknown>
  giveBackHold(hold: number): Promise<unknown>
  // lib/live/transport.ts
  interface LiveConnection { ...; giveBack(): void }  // the round did not deliver; safe to call twice
  interface LiveOptions { ...; signal?: AbortSignal }
  ```

- [ ] **Step 1: Write the failing tests**

`frontend/src/lib/live/geminiWebsocket.test.ts` 맨 위에 api를 막고, `openRound`의 `start`에 `hold: null`을 더하고, `connectGemini`, `LiveOptions`, `api`를 가져온다. `beforeEach`에서 두 mock을 비운다.

```ts
vi.mock('../../api', () => ({ api: { confirmHold: vi.fn(async () => undefined), giveBackHold: vi.fn(async () => undefined) } }))

const HOLD = 31
const options = (over: Partial<LiveOptions> = {}): LiveOptions => ({
  start: vi.fn(async () => ({ url: 'wss://live', setup: {}, hold: HOLD })),
  audio: { srcObject: null, play: async () => undefined } as unknown as HTMLAudioElement,
  onEvent: () => undefined,
  onDisconnect: () => undefined,
  ...over,
})

/** A socket whose server turns the setup down. */
class RefusingSocket extends FakeSocket {
  send() {
    queueMicrotask(() => this.reply({ error: { message: 'no' } }))
  }
}

const microphoneAnswers = (getUserMedia: () => Promise<unknown>) =>
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true })

describe('what a round pays', () => {
  it('asks for the microphone before it asks for a token', async () => {
    const order: string[] = []
    microphoneAnswers(async () => {
      order.push('microphone')
      return { getTracks: () => [] }
    })
    await connectGemini(options({ start: async () => (order.push('token'), { url: 'wss://live', setup: {}, hold: HOLD }) }))
    expect(order).toEqual(['microphone', 'token'])
  })

  it('takes no token when the microphone is refused', async () => {
    microphoneAnswers(async () => {
      throw new Error('Permission denied')
    })
    const opts = options()
    await expect(connectGemini(opts)).rejects.toThrow('Permission denied')
    expect(opts.start).not.toHaveBeenCalled()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('confirms once the setup is answered', async () => {
    await connectGemini(options())
    expect(api.confirmHold).toHaveBeenCalledExactlyOnceWith(HOLD)
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('gives the price back when the setup is refused', async () => {
    vi.stubGlobal('WebSocket', RefusingSocket)
    await expect(connectGemini(options())).rejects.toThrow('no')
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(HOLD)
    expect(api.confirmHold).not.toHaveBeenCalled()
  })

  it('gives the price back when the connection drops, once however often it is asked', async () => {
    const onDisconnect = vi.fn()
    const round = await connectGemini(options({ onDisconnect }))
    FakeSocket.last.close(1006, '')
    round.giveBack()
    expect(onDisconnect).toHaveBeenCalledOnce()
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(HOLD)
  })

  it('keeps the price when the round ends on purpose', async () => {
    const round = await connectGemini(options())
    round.close()
    await settle()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('reports nothing once the round is disposed, as Retry does', async () => {
    const round = await connectGemini(options())
    round.dispose()
    await settle()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })

  it('takes no token when it is abandoned at the microphone', async () => {
    const leaving = new AbortController()
    microphoneAnswers(async () => {
      leaving.abort()
      return { getTracks: () => [{ stop: () => undefined }] }
    })
    const opts = options({ signal: leaving.signal })
    await expect(connectGemini(opts)).rejects.toThrow()
    expect(opts.start).not.toHaveBeenCalled()
  })

  it('gives the price back when it is abandoned while the token comes', async () => {
    const leaving = new AbortController()
    const start = vi.fn(async () => {
      leaving.abort()
      return { url: 'wss://live', setup: {}, hold: HOLD }
    })
    await expect(connectGemini(options({ start, signal: leaving.signal }))).rejects.toThrow()
    expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(HOLD)
    expect(api.confirmHold).not.toHaveBeenCalled()
  })

  it('sends nothing for the admin, whose round has no hold', async () => {
    const start = async () => ({ url: 'wss://live', setup: {}, hold: null })
    const round = await connectGemini(options({ start }))
    FakeSocket.last.close(1006, '')
    round.giveBack()
    expect(api.confirmHold).not.toHaveBeenCalled()
    expect(api.giveBackHold).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/live/geminiWebsocket.test.ts`
Expected: the new tests FAIL. `order`는 `['token', 'microphone']`이고 `confirmHold`는 불리지 않는다.

- [ ] **Step 3: Add the types and the two reports**

`types.ts`에 위의 두 필드. `api.ts`에는 `request`를 쓰지 않는 private 도우미를 둔다. `request`는 401에서 로그인 화면으로 보내고 오류를 던지는데, 이 두 호출은 그래서는 안 된다.

```ts
/** A word to the server about a round's price; the round goes on whether or not it arrives. */
function report(path: string, method: string): Promise<unknown> {
  return fetch(path, { method, keepalive: true }).catch(() => undefined)
}
```

`confirmHold`는 `report(`/api/me/credits/holds/${hold}/confirm`, 'POST')`, `giveBackHold`는 `report(`/api/me/credits/holds/${hold}`, 'DELETE')`다. `transport.ts`에 위의 두 필드를 더한다.

- [ ] **Step 4: Split the round in `frontend/src/lib/live/geminiWebsocket.ts`**

`GeminiRound.open`을 둘로 나눈다. `prepare()`는 지금의 `getUserMedia`부터 `audio.play()`까지다. `open(url, setup)`은 `new WebSocket(url)`부터 끝까지다. `hold: number | null = null` 필드를 더한다. `join`은 이렇게 된다.

```ts
async function join(round: GeminiRound, opts: LiveOptions): Promise<LiveConnection> {
  try {
    await round.prepare()
    stopIfLeft(opts.signal)
    const session = await opts.start()
    round.hold = session.hold
    stopIfLeft(opts.signal)
    await round.open(session.url, session.setup)
    stopIfLeft(opts.signal)
  } catch (e) {
    round.giveBack()
    round.dispose()
    throw e
  }
  round.confirm()
  return round
}
```

- `stopIfLeft(signal)`: `signal?.aborted`이면 `new Error('The round was left before it connected')`을 던진다.
- `giveBack()`: `hold`가 null이 아니면 `api.giveBackHold`를 부르고 `hold`를 null로 한다.
- `confirm()`: `hold`가 null이 아니면 `api.confirmHold`를 부른다. `hold`는 그대로 둔다. 끊김 보고에 쓴다.
- `onClose`의 비정상 분기에서 `dispose` 앞에 `this.giveBack()`을 부른다. `disposed`로 시작하는 분기와 `finalized` 분기는 부르지 않는다.
- 파일 맨 위 설명에 마이크를 먼저 받는 이유를 한 줄 더한다: 거부된 회는 토큰을 쓰지 않는다.

- [ ] **Step 5: Run the tests and the type check**

Run: `cd frontend && npx vitest run src/lib/live/geminiWebsocket.test.ts`
Expected: PASS.

Run: `cd frontend && npx tsc -b --noEmit`
Expected: `hold`와 `giveBack`이 빠진 테스트 픽스처만 오류다 (`ReadAloud.test.tsx`, `Practice.test.tsx`, `Summarize.test.tsx`). 이 셋은 Task 6과 7이 고친다. 다른 오류가 있으면 여기서 고친다.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts frontend/src/lib/live
git commit -m "feat: a live round asks for the microphone first and reports how it went"
```

---

### Task 6: 연결 중 떠남과 회의 실패 (`useLiveRound`, Practice, Summarize)

**Files:**
- Modify: `frontend/src/lib/useLiveRound.ts`, `frontend/src/components/Summarize.tsx`
- Test: `frontend/src/components/Practice.test.tsx`, `frontend/src/components/Summarize.test.tsx`

**Interfaces:**
- Consumes: Task 5의 `LiveConnection.giveBack`, `LiveOptions.signal`.
- Produces: `LiveRound.giveBack(): void`.

- [ ] **Step 1: Write the failing tests**

두 테스트 파일의 `connection`에 `giveBack: vi.fn()`을 더한다. Practice의 `beforeEach`에서 `connection.giveBack.mockClear()`, Summarize의 테스트 시작에서도 같다. `frontend/src/components/Practice.test.tsx`의 `describe('Practice')`에 더한다.

```tsx
const left = (call = 0) => connect.mock.calls[call][1].signal!.aborted

async function beginRound() {
  await userEvent.click(screen.getByRole('button', { name: /^Practice/ }))
  act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
}

it('gives the voice back when the feedback fails', async () => {
  vi.mocked(api.exampleFeedback).mockRejectedValue(new Error('feedback failed: down'))
  renderPractice()
  await beginRound()
  act(() => emit({ type: 'session.input_transcript.delta', delta: 'The dam mitigate the flood.' }))
  act(() => emit({ type: 'session.output_transcript.delta', delta: 'Got it.' }))
  expect(await screen.findByText('feedback failed: down')).toBeInTheDocument()
  expect(connection.giveBack).toHaveBeenCalledOnce()
})

it('gives the voice back when the reader spoke and the coach never answered', async () => {
  renderPractice()
  await beginRound()
  act(() => emit({ type: 'session.input_transcript.delta', delta: 'The dam mitigate the flood.' }))
  act(() => emit({ type: 'session.closed', usage: { seconds: 9 } }))
  expect(connection.giveBack).toHaveBeenCalledOnce()
})

it('keeps the voice when the reader said nothing', async () => {
  renderPractice()
  await beginRound()
  act(() => emit({ type: 'session.closed', usage: { seconds: 9 } }))
  expect(connection.giveBack).not.toHaveBeenCalled()
})

it('keeps the voice when the coach answered', async () => {
  renderPractice()
  await sayAndHear()
  expect(connection.giveBack).not.toHaveBeenCalled()
})

it('abandons a round still connecting when it is discarded or retried', async () => {
  connect.mockImplementationOnce(() => new Promise(() => undefined))
  connect.mockImplementationOnce(() => new Promise(() => undefined))
  renderPractice()
  await userEvent.click(screen.getByRole('button', { name: /^Practice/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(left(0)).toBe(true)
  expect(left(1)).toBe(false)
  await userEvent.click(screen.getByRole('button', { name: 'Discard' }))
  expect(left(1)).toBe(true)
})

it('gives back and drops a connection that arrives after the round was left', async () => {
  let arrive!: (c: LiveConnection) => void
  connect.mockImplementationOnce(() => new Promise((resolve) => (arrive = resolve)))
  renderPractice()
  await userEvent.click(screen.getByRole('button', { name: /^Practice/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Discard' }))
  await act(async () => arrive(connection))
  expect(connection.giveBack).toHaveBeenCalledOnce()
  expect(connection.dispose).toHaveBeenCalledOnce()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('shows nothing of a round that failed after it was left', async () => {
  let refuse!: (e: Error) => void
  connect.mockImplementationOnce(() => new Promise((_, reject) => (refuse = reject)))
  renderPractice()
  await userEvent.click(screen.getByRole('button', { name: /^Practice/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await act(async () => refuse(new Error('The round was left before it connected')))
  expect(screen.queryByText('The round was left before it connected')).not.toBeInTheDocument()
})

it('after Retry, an old feedback failing touches only the old round', async () => {
  const old = { ...connection, giveBack: vi.fn() }
  const fresh = { ...connection, giveBack: vi.fn() }
  connect.mockImplementationOnce(async (_t, opts) => ((emit = opts.onEvent), old))
  connect.mockImplementationOnce(async (_t, opts) => ((emit = opts.onEvent), fresh))
  let fail!: (e: Error) => void
  vi.mocked(api.exampleFeedback).mockImplementationOnce(() => new Promise((_, reject) => (fail = reject)))
  renderPractice()
  await beginRound()
  act(() => emit({ type: 'session.input_transcript.delta', delta: 'The dam mitigate the flood.' }))
  act(() => emit({ type: 'session.output_transcript.delta', delta: 'Got it.' }))
  await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await act(async () => fail(new Error('feedback failed: down')))
  expect(old.giveBack).toHaveBeenCalledOnce()
  expect(fresh.giveBack).not.toHaveBeenCalled()
  expect(screen.queryByText('feedback failed: down')).not.toBeInTheDocument()
})
```

`frontend/src/components/Summarize.test.tsx`에 더한다. 첫 테스트(`keeps the paragraph in view...`)의 끝에 `expect(connection.giveBack).not.toHaveBeenCalled()`도 더한다. 그 테스트는 `vi.useFakeTimers`를 켜므로 새 테스트 시작에서 `vi.useRealTimers()`와 `connection.giveBack.mockClear()`를 부른다.

```tsx
it('gives the voice back when the judgment fails', async () => {
  vi.useRealTimers()
  connection.giveBack.mockClear()
  vi.mocked(api.summaryFeedback).mockRejectedValue(new Error('feedback failed: down'))
  render(
    <Paragraph
      paragraph={{ id: 4, text: paragraph }}
      pieces={[{ text: paragraph, start: 0, ko: null }]}
      spans={[]}
      summaries={[]}
      saved={[]}
      onSummary={vi.fn()}
      active={false}
      onStart={vi.fn()}
      onEnd={vi.fn()}
    />,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Summarize' }))
  act(() => emit({ type: 'session.started', session: { id: 'live_1' } }))
  act(() => emit({ type: 'session.input_transcript.delta', delta: said }))
  await userEvent.click(screen.getByRole('button', { name: 'Done' }))
  act(() => emit({ type: 'session.closed', usage: { seconds: 20 } }))
  expect(await screen.findByText(/feedback failed: down/)).toBeInTheDocument()
  expect(connection.giveBack).toHaveBeenCalledOnce()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/Practice.test.tsx src/components/Summarize.test.tsx`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement in `frontend/src/lib/useLiveRound.ts`**

- 회마다 `AbortController`를 `leaving` ref에 둔다. private `abandon()`은 그것을 중단하고 비운다. `start`, `dismiss`, 언마운트 정리에서 부른다.
- `start`: `signal`을 `connect`에 넘긴다. `onEvent`와 `onDisconnect`는 `signal.aborted`이면 바로 돌아간다. `await` 뒤에 `signal.aborted`이면 `conn.giveBack()`, `conn.dispose()`, `return`. `catch`에서 `signal.aborted`이면 화면을 건드리지 않는다.
- `takeTurn`: 시작할 때 `const conn = connRef.current`로 잡는다. `catch`에서 `conn?.giveBack()`을 부르고, `connRef.current === conn`일 때만 `apply`로 오류를 보인다.
- `onEvent`: `apply` 다음, 지금의 이른 `return` 앞에서 본다. `session.closed`이고 `handlers.current.onTurn`이 있고 `turn.current === 'open'`이고 `latest.current?.user.trim()`이 비어 있지 않으면 `connRef.current?.giveBack()`. 새 타이머는 두지 않는다.
- `LiveRound`에 `giveBack()`을 더한다: `connRef.current?.giveBack()`.

- [ ] **Step 4: Report the failed judgment in `frontend/src/components/Summarize.tsx`**

`useSummary`의 `.catch`를 `(e: Error) => { if (!live) return; setFailure(e.message); round.giveBack() }`로 바꾼다.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/Practice.test.tsx src/components/Summarize.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/useLiveRound.ts frontend/src/components/Summarize.tsx frontend/src/components/Practice.test.tsx frontend/src/components/Summarize.test.tsx
git commit -m "feat: a round left or failed before it delivered gives its price back"
```

---

### Task 7: Read aloud

**Files:**
- Modify: `frontend/src/components/ReadAloud.tsx`
- Test: `frontend/src/components/ReadAloud.test.tsx`, `frontend/src/components/ArticleTab.test.tsx`

**Interfaces:**
- Consumes: Task 5의 `api.confirmHold`, `api.giveBackHold`, `AssessorSession.hold`, `LiveConnection.giveBack`, `LiveOptions.signal`.
- Produces: `export const COACH_TIMEOUT_MS` (테스트가 쓴다).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/ReadAloud.test.tsx`를 준비한다.
- `session`에 `hold: 31`. `vi.mock('../api')`에 `confirmHold: vi.fn()`, `giveBackHold: vi.fn()`. `connection`에 `giveBack: vi.fn()`.
- `const getUserMedia = vi.mocked(navigator.mediaDevices.getUserMedia)`.
- `beforeEach`에서 `getUserMedia`, `api.confirmHold`, `api.giveBackHold`, `connection.giveBack`을 `mockClear`한다.
- `import { cleanup }`과 `COACH_TIMEOUT_MS`를 가져온다.
- `frontend/src/components/ArticleTab.test.tsx:14`의 token mock에 `hold: null`을 더한다.

`fails before touching the microphone when the assessor is off`는 아래 `releases the microphone when the assessor is off`로 바꾼다. 나머지는 `describe('ReadAloud round')`에 더한다.

```tsx
it('asks for the microphone before it asks for the token', async () => {
  renderIdle()
  await startRound()
  expect(getUserMedia.mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.assessorToken).mock.invocationCallOrder[0])
})

it('takes no token when the microphone is refused', async () => {
  getUserMedia.mockRejectedValueOnce(new Error('Permission denied'))
  renderIdle()
  await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
  expect(await screen.findByText('Permission denied')).toBeInTheDocument()
  expect(api.assessorToken).not.toHaveBeenCalled()
  expect(api.giveBackHold).not.toHaveBeenCalled()
})

it('releases the microphone when the assessor is off', async () => {
  vi.mocked(api.assessorToken).mockRejectedValueOnce(new Error('Read aloud is off: set AZURE_SPEECH_KEY in Settings'))
  renderIdle()
  await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
  expect(await screen.findByText('Read aloud is off: set AZURE_SPEECH_KEY in Settings')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Could not start')
  expect(startAssessor).not.toHaveBeenCalled()
  expect(track.stop).toHaveBeenCalled()
})

it('confirms once Azure is listening', async () => {
  renderIdle()
  await startRound()
  expect(api.confirmHold).toHaveBeenCalledExactlyOnceWith(31)
  expect(api.giveBackHold).not.toHaveBeenCalled()
})

it('gives the price back when Azure will not start', async () => {
  startAssessor.mockRejectedValueOnce(new Error('no route to Azure'))
  renderIdle()
  await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
  expect(await screen.findByText('no route to Azure')).toBeInTheDocument()
  expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(31)
  expect(api.confirmHold).not.toHaveBeenCalled()
})

it('gives the price back when Azure fails during the round', async () => {
  renderIdle()
  await startRound()
  act(() => startAssessor.mock.calls[0][0].onError('Connection closed'))
  expect(screen.getByText('Assessor: Connection closed')).toBeInTheDocument()
  expect(api.giveBackHold).toHaveBeenCalledExactlyOnceWith(31)
})

it('takes no token when the page is left at the microphone prompt', async () => {
  let allow!: (m: MediaStream) => void
  getUserMedia.mockImplementationOnce(() => new Promise((resolve) => (allow = resolve)))
  renderIdle()
  await userEvent.click(screen.getByRole('button', { name: 'Read aloud' }))
  cleanup()
  await act(async () => allow(microphone))
  expect(api.assessorToken).not.toHaveBeenCalled()
  expect(track.stop).toHaveBeenCalled()
})

/** A finished reading's mark clicked, with fake timers on from then and the coach's call open. */
async function callTheCoach() {
  renderIdle()
  await startRound()
  act(() => segment([berified], 'berified'))
  vi.useFakeTimers({ shouldAdvanceTime: true })
  await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
  await vi.waitFor(() => expect(connect).toHaveBeenCalled())
  await act(() => vi.advanceTimersByTimeAsync(1))
}

it('gives the coach back when it never says a word', async () => {
  try {
    await callTheCoach()
    await act(() => vi.advanceTimersByTimeAsync(COACH_TIMEOUT_MS + 1))
    expect(connection.giveBack).toHaveBeenCalledOnce()
    expect(connection.close).toHaveBeenCalled()
  } finally {
    vi.useRealTimers()
  }
})

it('keeps the coach price once it has spoken', async () => {
  try {
    await callTheCoach()
    act(() => emit({ type: 'session.output_transcript.delta', delta: 'You said /b/.' }))
    await act(() => vi.advanceTimersByTimeAsync(COACH_TIMEOUT_MS + 1))
    expect(connection.giveBack).not.toHaveBeenCalled()
    expect(connection.close).toHaveBeenCalled()
  } finally {
    vi.useRealTimers()
  }
})

it('a second click abandons a call still connecting', async () => {
  connect.mockImplementationOnce(() => new Promise(() => undefined))
  renderIdle()
  await startRound()
  act(() => segment([berified], 'berified'))
  await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
  await waitFor(() => expect(connect).toHaveBeenCalledOnce())
  await userEvent.click(screen.getByRole('button', { name: 'verified: b for v' }))
  await waitFor(() => expect(connect).toHaveBeenCalledTimes(2))
  expect(connect.mock.calls[0][1].signal!.aborted).toBe(true)
  expect(connect.mock.calls[1][1].signal!.aborted).toBe(false)
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/ReadAloud.test.tsx`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement the reading in `frontend/src/components/ReadAloud.tsx`**

`start`의 순서는 마이크, 토큰, Azure, 확인이다.
- `mounted` ref를 둔다. 정리 `useEffect`의 몸체에서 `true`, 정리 함수에서 `false`로 한다 (StrictMode가 효과를 두 번 돌린다).
- `microphone`과 `hold`를 `try` 바깥에 `let`으로 둔다. `getUserMedia` 뒤에 `mounted`가 false면 트랙을 멈추고 돌아간다. `Round` 객체는 지금처럼 토큰 뒤에 만든다 (`Judge`가 `word_score`를 쓴다).
- 토큰 뒤에 `hold = session.hold`.
- `startAzureAssessor` 뒤에 `mounted`가 false면 `round.assessor`를 멈추고 트랙을 멈춘 뒤 `giveBack(hold)` 후 돌아간다. 아니면 `hold`가 있을 때 `api.confirmHold(hold)`, `setPhase('listening')`.
- `onError`: `setError` 뒤에 `giveBack(hold)`.
- `catch`: `microphone`의 트랙을 멈추고, `endRound()`, `giveBack(hold)`, 지금처럼 `setError`와 `setPhase('failed')`.
- private 도우미 `giveBack(hold: number | null)`: null이 아니면 `void api.giveBackHold(hold)`.

- [ ] **Step 4: Implement the coach call**

- `Call`에 `spoke: boolean`을 더한다 (처음 `false`).
- `speak`: `hangUp()` 다음에 이전 `AbortController`(`calling` ref)를 중단하고 새로 만들어 `signal`을 `connectReadAloud`에 넘긴다. 정리 함수에서도 중단한다. `await` 뒤에 `signal.aborted`이면 `coach.giveBack()`, `coach.dispose()`, `return`. `catch`에서 `signal.aborted`이면 오류를 보이지 않는다. 그 onEvent는 `session.output_transcript.delta`에서 `callRef.current`의 `spoke`를 켠다.
- `linger`의 타이머: `if (!call.spoke) call.coach.giveBack()` 다음에 `call.coach.close()`.
- `COACH_TIMEOUT_MS`를 `export`한다.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/ReadAloud.test.tsx src/components/ArticleTab.test.tsx src/components/Paragraph.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ReadAloud.tsx frontend/src/components/ReadAloud.test.tsx frontend/src/components/ArticleTab.test.tsx
git commit -m "feat: Read aloud takes the microphone first and gives back what it did not deliver"
```

---

### Task 8: 취소와 삭제의 화면

**Files:**
- Modify: `frontend/src/lib/progress.ts`, `frontend/src/components/GenerationProgress.tsx`, `frontend/src/pages/HomePage.tsx`, `frontend/src/components/CreditsPill.tsx`, 그리고 `JobStatus` 픽스처 (`GenerationProgress.test.tsx`, `TopicsPanel.test.tsx`, `progress.test.ts`, `useTopics.test.ts`, `HomePage.test.tsx` 중 `tsc`가 가리키는 것)
- Test: `frontend/src/components/GenerationProgress.test.tsx`, `frontend/src/pages/HomePage.test.tsx`, `frontend/src/components/CreditsPill.test.tsx`

**Interfaces:**
- Consumes: Task 4의 `JobStatus.spent`, `PRICES["session_cancelled"]`.
- Produces: `JobStatus.spent: boolean` in `lib/progress.ts`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/GenerationProgress.test.tsx`: `base`에 `spent: false`. credits를 막는다.

```tsx
vi.mock('../lib/credits', async (original) => ({ ...(await original<typeof import('../lib/credits')>()), useCredits: vi.fn() }))

const PRICES = { session_cancelled: 100 }

beforeEach(() => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(500, PRICES))
})

it('costs nothing to stop before Claude is called', () => {
  render(<GenerationProgress job={base} onClose={() => undefined} onOpen={() => undefined} />)
  const cancel = screen.getByRole('button', { name: 'Cancel' })
  expect(cancel).not.toHaveTextContent('100')
  expect(cancel).not.toHaveAttribute('title')
})

it('names what stopping costs once Claude is working', () => {
  render(<GenerationProgress job={{ ...base, spent: true }} onClose={() => undefined} onOpen={() => undefined} />)
  const cancel = screen.getByRole('button', { name: 'Cancel' })
  expect(cancel).toHaveTextContent('100')
  expect(cancel).toHaveAttribute('title', 'Stops now. 100 credits stay charged.')
})

it('says the session goes once it is saved', () => {
  render(<GenerationProgress job={{ ...base, spent: true, stage: 'illustrating', session_id: 21 }} onClose={() => undefined} onOpen={() => undefined} />)
  const cancel = screen.getByRole('button', { name: 'Cancel and delete' })
  expect(cancel).toHaveTextContent('100')
  expect(cancel).toHaveAttribute('title', 'Stops now. The session is deleted and 100 credits stay charged.')
})

it('tells the admin, who pays nothing, only that the session goes', () => {
  vi.mocked(useCredits).mockReturnValue(creditsOf(null, PRICES))
  render(<GenerationProgress job={{ ...base, spent: true, stage: 'illustrating', session_id: 21 }} onClose={() => undefined} onOpen={() => undefined} />)
  const cancel = screen.getByRole('button', { name: 'Cancel and delete' })
  expect(cancel).not.toHaveTextContent('100')
  expect(cancel).toHaveAttribute('title', 'Stops now. The session is deleted.')
})

it('asks nothing of a failed job, whatever it spent', () => {
  render(<GenerationProgress job={{ ...base, spent: true, status: 'failed', session_id: 21 }} onClose={() => undefined} onOpen={() => undefined} />)
  const close = screen.getByRole('button', { name: 'Close' })
  expect(close).not.toHaveTextContent('100')
  expect(close).not.toHaveAttribute('title')
})
```

`frontend/src/pages/HomePage.test.tsx`에 더한다.

```tsx
test('a session that cannot be deleted yet stays and says why', async () => {
  const why = 'This session is still being drawn. Cancel it on the progress bar: the session goes and half the price stays charged.'
  vi.mocked(api.listSessions).mockResolvedValue([MINE])
  vi.mocked(api.deleteSession).mockRejectedValue(new Error(why))
  open()
  await userEvent.click(await screen.findByRole('button', { name: 'Delete My trams' }))
  expect(await screen.findByText(why)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /My trams/ })).toBeInTheDocument()
})
```

`frontend/src/components/CreditsPill.test.tsx`에는 내역의 `session_cancelled` 행이 `Cancelled session`으로 보이는 테스트를 그 파일의 기존 패턴으로 더한다.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/GenerationProgress.test.tsx src/pages/HomePage.test.tsx src/components/CreditsPill.test.tsx`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement the screens**

- `lib/progress.ts`: `spent: boolean`에 주석 `/** Claude has been called, so stopping now costs half. */`.
- `GenerationProgress.tsx`: `const price = useCredits().cost('session_cancelled')`. 실행 중일 때만 글자와 설명이 바뀐다. 글자는 `session_id`가 있으면 `Cancel and delete`, 없으면 `Cancel`. `spent`이면 `<Price amount={price} />`. `title`은 private 함수 `stopNote(job, price)`가 만든다.
  | `session_id` | `spent` | `price > 0` | `title` |
  |---|---|---|---|
  | 있음 | | 예 | `Stops now. The session is deleted and {price} credits stay charged.` |
  | 있음 | | 아니오 | `Stops now. The session is deleted.` |
  | 없음 | 예 | 예 | `Stops now. {price} credits stay charged.` |
  | 그 밖 | | | `title` 없음 |
- `HomePage.tsx`: `remove`를 `try`로 감싸고 실패 문구를 `removeError` 상태에 둔다. 다음 시도 때 비운다. `loadError` 바로 아래에 `<p className="error">`로 보인다.
- `CreditsPill.tsx`: `KIND_LABELS`에 `session_cancelled: 'Cancelled session'`. `refund`는 과거 행 때문에 남긴다.

- [ ] **Step 4: Run the whole frontend suite and the type check**

Run: `cd frontend && npx vitest run`
Expected: 전부 PASS, 실패 0.

Run: `cd frontend && npx tsc -b --noEmit`
Expected: 오류 없음. 남은 `JobStatus` 픽스처 오류는 `spent: false`를 더해 고친다.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: Cancel says what stopping costs, and a session being drawn says why it stays"
```

---

### Task 9: 문서, 실제 흐름, 리뷰, 병합

**Files:**
- Modify: `docs/superpowers/specs/2026-11-01-credits-design.md`, `docs/superpowers/specs/2026-11-01-credit-transactions-design.md`, `README.md`

- [ ] **Step 1: Correct the credits design**

`docs/superpowers/specs/2026-11-01-credits-design.md`에서 어긋난 내용을 고치고 지운다. 내용을 둘로 유지하지 않는다.

| 행 | 지금 | 바꿀 내용 |
|---|---|---|
| 19 | 서버가 그 기능을 시작하는 순간 차감한다 | 시작할 때 잡아 두고, 완수하면 확정한다. `2026-11-01-credit-transactions-design.md` 참조 |
| 25 | 세션 생성의 환불 | 행을 지운다 |
| 31-42 가격표 | | `세션 취소 (Claude를 부른 뒤) \| DELETE /api/jobs/{id} \| 100` 행을 더한다 |
| 53 | 차감은 한 트랜잭션 | 잡아 두기는 한 트랜잭션 (`BEGIN IMMEDIATE`) |
| 55 | 차감 뒤 제공자 호출이 실패해도(502) 돌려주지 않는다. 세션 생성만 예외다. | 이 두 문장을 지운다 |
| 57 | 세션 생성 규칙 전체 | 요청 시점에 200을 잡아 두고 job을 시작한다. 끝난 뒤의 값은 트랜잭션 설계의 결과표를 따른다 |
| 72, 80 | 스키마 설명, `kind` 목록 | 열은 v14에서 늘었다고 적고 `session_cancelled`를 더한다. `refund`는 과거 행이라고 적는다 |
| 118, 120 | 제공자 실패에 차감이 남는다, 저장 뒤 실패와 취소는 환불 없음 | 지운다 |

`2026-11-01-credit-transactions-design.md`의 상태를 `구현됨 (날짜)`으로 바꾼다.

- [ ] **Step 2: Add a sentence to `README.md:87`**

그 항목 끝에 더한다: `A feature that fails or does not finish costs nothing. A session its maker cancels after generation began costs half, and is deleted.`

- [ ] **Step 3: Run the real flow on a temporary backend**

운영 서버와 운영 DB를 쓰지 않는다. 임시 `DB_PATH`와 일부러 틀린 Gemini, Azure 키로 백엔드와 프런트를 띄운다. 비밀값을 출력하지 않는다. 일반 계정에 충전한 뒤 확인한다.
1. 문장 듣기, Practice 시작, Read aloud 시작이 502를 보이고 잔액이 그대로다.
2. 브라우저에서 마이크를 거부하면 `/api/assessor/token`과 `/api/example/sessions` 요청이 나가지 않는다.
3. 생성이 도는 동안 백엔드 프로세스를 죽였다 다시 띄우면 `GET /api/me/credits`의 잔액이 돌아온다.

Expected: 셋 다 그대로. 어긋나면 고치고 해당 태스크의 테스트를 더한다.

- [ ] **Step 4: Run both suites separately and read the results**

Run: `cd backend && .venv/bin/pytest -q`
Expected: 전부 PASS.

Run: `cd frontend && npx vitest run`
Expected: 전부 PASS.

Run: `cd frontend && npx tsc -b --noEmit`
Expected: 오류 없음.

- [ ] **Step 5: Commit the docs**

```bash
node .gitnexus/run.cjs detect-changes --scope all --repo .
git add docs README.md
git commit -m "docs: the credits design follows the transaction rules"
```

- [ ] **Step 6: Final review by one fresh subagent**

전체 브랜치(`git diff main...HEAD`)를 설계 문서의 결과표와 맞춰 보게 한다. 결론을 주지 말고 코드와 표만 준다. 나온 문제를 고치고 Step 4를 다시 돈다.

- [ ] **Step 7: Merge**

```bash
git switch main
git merge --ff-only feat/credit-transactions
scripts/bump-version patch
```

push와 배포는 사용자가 말할 때만 한다. 배포 전에는 돌고 있는 생성이 없는지 확인한다: `docker compose logs backend --since 10m | grep -c 'POST /api/sessions HTTP'`와 `GET /api/jobs`. 스키마 v14 업그레이드는 시작할 때 `sessions.db.bak-v13-DATE`를 자동으로 남긴다.
