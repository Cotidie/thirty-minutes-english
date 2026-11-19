# 크레딧 기록 묶기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 태스크를 이 세션에서 직접 실행하고, 끝에 새 서브에이전트 리뷰를 한 번만 한다 (사용자가 정한 방식). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 크레딧 기록이 같은 날, 같은 항목, 같은 내용, 같은 부호의 줄을 한 줄(횟수, 합계)로 묶어 최근 묶음 10개를 보인다.

**Architecture:** `CreditRepo.history`가 셈에 드는 줄을 최근 것부터 읽어 Python에서 (보는 사람 시간대의 날짜, kind, detail, 부호)로 묶는다. 두 GET 경로가 `tz` 쿼리를 `Zone` 의존성으로 받아 `history`를 부른다. 프런트는 두 호출에 브라우저 시간대를 붙이고 `CreditLine`이 `×N`을 보인다.

**Tech Stack:** Python 3, FastAPI, pydantic, SQLite, zoneinfo, pytest, React 19, TypeScript, vitest.

**Spec:** `docs/superpowers/specs/2026-11-19-credit-history-groups-design.md`

## Global Constraints

- 브랜치 `feat/credit-history-groups`. `main`에 `--ff-only`로 합치고 `scripts/bump-version patch`. push와 배포는 사용자가 말할 때만.
- 심볼을 고치기 전에 GitNexus `impact`, 커밋 전에 `detect-changes --scope all`. HIGH 이상은 보고한다.
- 커밋 메시지는 제목과 본문뿐, `Co-Authored-By` 없음. 새 의존성, 새 셸 스크립트 없음. DB 스키마 변경 없음.
- 이벤트는 그대로다 (`credits` 이벤트가 오면 같은 GET을 다시 읽는다).
- 테스트: 백엔드 `cd backend && .venv/bin/pytest -q`(기준 687 passed), 프런트 `cd frontend && npx vitest run`(기준 542), `npx tsc -b --noEmit`, `npm run lint`(기존 경고 23개). 결과를 읽은 뒤 커밋한다.
- 대화문 채우기(`korean_dialogues --apply`)가 운영 backend 컨테이너에서 도는 중일 수 있다. 끝나기 전에는 배포(컨테이너 재시작)하지 않는다.

## Review Focus

1. 같은 날 지급 +500과 회수 −100 → 두 줄로 남는다. (Task 1 `test_history_keeps_different_details_and_signs_apart`)
2. UTC로는 이틀에 걸친 두 줄이 한국 시간으로는 같은 날 → `Asia/Seoul`에서 한 줄, UTC에서 두 줄. (Task 1 `test_history_counts_days_in_the_given_zone`)
3. 모르는 `tz` 이름(`Not/AZone`, `../etc`) → 200, UTC로 묶음. (Task 1 `test_an_unknown_time_zone_falls_back_to_utc`)
4. 풀린 hold(셈에 안 드는 줄) → 묶음에도 들어가지 않는다. `COUNTS`를 그대로 쓴다. (Task 1 `test_history_leaves_out_rows_that_do_not_count`)
5. 한 번뿐인 줄 → "×1"을 붙이지 않는다. (Task 2 `shows a group's count only when there is more than one`)

---

### Task 1: 서버가 기록을 묶는다

**Files:**
- Modify: `backend/app/models.py` (`CreditEntry.count`)
- Modify: `backend/app/db/credits.py` (`CreditRepo.history`, private `_grouped`, `_day`)
- Modify: `backend/app/api/deps.py` (`Zone`)
- Modify: `backend/app/api/credits.py` (`my_credits`), `backend/app/api/accounts.py` (`account_credits`)
- Test: `backend/tests/test_credits.py`, `backend/tests/test_admin.py`

**Interfaces:**
- Produces:
  - `CreditEntry.count: int = 1` (docstring: "How many rows of one day, kind, detail and sign this line sums; `at` is the newest.").
  - `CreditRepo.history(self, user_id: int, zone: ZoneInfo, limit: int = 10) -> list[CreditEntry]`: `SELECT at, amount, kind, detail FROM credits WHERE user_id = ? AND {COUNTS} ORDER BY id DESC`, 그다음 `_grouped(rows, zone)[:limit]`.
  - `_grouped(rows, zone) -> list[CreditEntry]`: 키 `(_day(at, zone), kind, detail, amount > 0)`; 처음 본 줄(가장 최근)이 묶음의 `at`; `amount` 합, `count` 증가; dict 삽입 순서 그대로.
  - `_day(at: str, zone: ZoneInfo) -> date`: `datetime.fromisoformat(at).astimezone(zone).date()`.
  - `deps.zone_of(tz: str | None = None) -> ZoneInfo`: `ZoneInfo(tz)`, 없거나 `ZoneInfoNotFoundError`/`ValueError`면 `ZoneInfo("UTC")`. `Zone = Annotated[ZoneInfo, Depends(zone_of)]` (쿼리 이름 `tz`).
  - `my_credits(db, me, zone: Zone)`는 `recent=db.credits.history(me.id, zone)`, `account_credits(user_id, db, zone: Zone)`는 `db.credits.history(..., zone)`.

- [ ] **Step 1: impact** — `CreditEntry`, `my_credits`, `account_credits`.

- [ ] **Step 2: 실패하는 테스트** (`backend/tests/test_credits.py`, import에 `from zoneinfo import ZoneInfo`):

```python
SEOUL, UTC_ZONE = ZoneInfo("Asia/Seoul"), ZoneInfo("UTC")


def add_row(db, user, amount, kind, detail, at, state="settled"):
    """A row written at `at`, as a charge or a grant from then would have left it."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO credits (user_id, at, amount, kind, detail, granted_by, state) VALUES (?, ?, ?, ?, ?, NULL, ?)",
            (user.id, at, amount, kind, detail, state),
        )


def lines(entries):
    return [(e.at.isoformat(), e.amount, e.kind, e.detail, e.count) for e in entries]


def test_history_groups_a_day_s_rows_of_one_kind_and_detail(store):
    mina = add_user(store, "mina@example.com")
    for at in ("2026-11-17T01:00:00+00:00", "2026-11-17T02:00:00+00:00", "2026-11-17T03:00:00+00:00"):
        add_row(store, mina, -5, "read_aloud_token", None, at)
    assert lines(store.credits.history(mina.id, SEOUL)) == [("2026-11-17T03:00:00+00:00", -15, "read_aloud_token", None, 3)]


def test_history_keeps_different_details_and_signs_apart(store):
    mina = add_user(store, "mina@example.com")
    add_row(store, mina, -200, "session", "Trams", "2026-11-17T01:00:00+00:00")
    add_row(store, mina, -200, "session", "Ferries", "2026-11-17T02:00:00+00:00")
    add_row(store, mina, 500, "grant", None, "2026-11-17T03:00:00+00:00")
    add_row(store, mina, -100, "grant", None, "2026-11-17T04:00:00+00:00")
    assert [(e.amount, e.kind, e.detail, e.count) for e in store.credits.history(mina.id, SEOUL)] == [
        (-100, "grant", None, 1), (500, "grant", None, 1), (-200, "session", "Ferries", 1), (-200, "session", "Trams", 1),
    ]


def test_history_counts_days_in_the_given_zone(store):
    mina = add_user(store, "mina@example.com")
    add_row(store, mina, -5, "read_aloud_token", None, "2026-11-16T20:00:00+00:00")  # Nov 17, 05:00 in Seoul
    add_row(store, mina, -5, "read_aloud_token", None, "2026-11-17T01:00:00+00:00")
    assert [e.count for e in store.credits.history(mina.id, SEOUL)] == [2]
    assert [e.count for e in store.credits.history(mina.id, UTC_ZONE)] == [1, 1]


def test_history_is_newest_group_first_and_stops_at_the_limit(store):
    mina = add_user(store, "mina@example.com")
    for day in range(1, 13):
        add_row(store, mina, -5, "speech", None, f"2026-11-{day:02d}T03:00:00+00:00")
        add_row(store, mina, -5, "speech", None, f"2026-11-{day:02d}T04:00:00+00:00")
    groups = store.credits.history(mina.id, SEOUL)
    assert [e.at.day for e in groups] == list(range(12, 2, -1)) and {e.count for e in groups} == {2}
    assert len(store.credits.history(mina.id, SEOUL, limit=3)) == 3


def test_history_leaves_out_rows_that_do_not_count(store):
    mina = add_user(store, "mina@example.com")
    add_row(store, mina, -5, "read_aloud_token", None, "2026-11-17T01:00:00+00:00")
    add_row(store, mina, -5, "read_aloud_token", None, "2026-11-17T02:00:00+00:00", state="released")
    assert [e.count for e in store.credits.history(mina.id, SEOUL)] == [1]


def test_my_credits_group_the_history_in_my_time_zone(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    mina = add_user(db, "mina@example.com")
    add_row(db, mina, -5, "read_aloud_token", None, "2026-11-16T20:00:00+00:00")
    add_row(db, mina, -5, "read_aloud_token", None, "2026-11-17T01:00:00+00:00")
    client = client_of(app, db, mina)
    assert [(e["amount"], e["count"]) for e in client.get("/api/me/credits?tz=Asia/Seoul").json()["recent"]] == [(-10, 2)]
    assert [e["count"] for e in client.get("/api/me/credits").json()["recent"]] == [1, 1]


def test_an_unknown_time_zone_falls_back_to_utc(tmp_path):
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    mina = add_user(db, "mina@example.com")
    add_row(db, mina, -5, "read_aloud_token", None, "2026-11-16T20:00:00+00:00")
    add_row(db, mina, -5, "read_aloud_token", None, "2026-11-17T01:00:00+00:00")
    client = client_of(app, db, mina)
    for tz in ("Not/AZone", "../etc/passwd", ""):
        res = client.get("/api/me/credits", params={"tz": tz})
        assert res.status_code == 200 and [e["count"] for e in res.json()["recent"]] == [1, 1]
```

`state="released"`는 `credits.state`의 실제 값 중 셈에 안 드는 것을 쓴다 (스키마의 CHECK를 보고 맞춘다).

`backend/tests/test_admin.py`의 기존 history 테스트 아래에:

```python
def test_the_admin_reads_an_account_s_history_grouped_in_their_time_zone(accounts):
    admin, _, user = accounts
    admin.post(f"/api/accounts/{user.id}/credits", json={"amount": 500})
    admin.post(f"/api/accounts/{user.id}/credits", json={"amount": 500})
    history = admin.get(f"/api/accounts/{user.id}/credits", params={"tz": "Asia/Seoul"}).json()
    assert [(e["amount"], e["kind"], e["count"]) for e in history] == [(1000, "grant", 2)]
```

- [ ] **Step 3: 실패 확인** — `cd backend && .venv/bin/pytest -q tests/test_credits.py tests/test_admin.py 2>&1 | grep -E "FAILED|passed|failed"`. Expected: 새 테스트 8개 FAIL (`history` 없음, `count` 없음). 단 `test_an_unknown_time_zone_falls_back_to_utc`는 `recent`가 낱줄을 돌려주므로 지금도 통과할 수 있다 (회귀 방지용).

- [ ] **Step 4: 구현** — 위 Interfaces대로.

- [ ] **Step 5: 통과 확인** — `cd backend && .venv/bin/pytest -q tests/test_credits.py tests/test_admin.py tests/test_speech.py 2>&1 | grep -E "FAILED|passed|failed"`. Expected: 실패 없음.

- [ ] **Step 6: 커밋** — `detect-changes` 후 `git commit -m "feat: the credit history groups a day's rows of one kind, detail and sign, counted in the reader's time zone"`.

---

### Task 2: 브라우저가 시간대를 보내고 횟수를 보인다

**Files:**
- Modify: `frontend/src/types.ts` (`CreditEntry.count?: number`)
- Modify: `frontend/src/api.ts` (`myCredits`, `accountCredits`, private `timeZoneQuery`)
- Modify: `frontend/src/components/CreditsPill.tsx` (`CreditLine`)
- Test: `frontend/src/api.test.ts`, `frontend/src/components/CreditsPill.test.tsx`

**Interfaces:**
- Consumes: `count`가 든 응답 (Task 1).
- Produces: `api.myCredits()`는 `/api/me/credits?tz=<브라우저 시간대>`, `api.accountCredits(id)`는 `/api/accounts/${id}/credits?tz=<…>`. 시간대는 `Intl.DateTimeFormat().resolvedOptions().timeZone`, `encodeURIComponent`. 함수 시그니처는 그대로.
- `CreditLine`: `count`가 1보다 크면 라벨 뒤에 `<span className="credit-count"> ×{count}</span>`, 그 뒤에 기존 detail.

- [ ] **Step 1: 실패하는 테스트**

`frontend/src/api.test.ts`:

```ts
test('the credit history asks for days in the browser time zone', async () => {
  answer(200, { balance: 0, prices: {}, recent: [] })
  await api.myCredits()
  const zone = encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone)
  expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`/api/me/credits?tz=${zone}`)
  answer(200, [])
  await api.accountCredits(2)
  expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`/api/accounts/2/credits?tz=${zone}`)
})
```

`frontend/src/components/CreditsPill.test.tsx`:

```tsx
test("shows a group's count only when there is more than one", async () => {
  has(340, [
    { at: '2026-11-17T03:00:00Z', amount: -15, kind: 'read_aloud_token', detail: null, count: 3 },
    { at: '2026-11-17T02:00:00Z', amount: -10, kind: 'practice_feedback', detail: 'mitigate', count: 2 },
    { at: '2026-11-17T01:00:00Z', amount: -200, kind: 'session', detail: 'Trams', count: 1 },
  ])
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  const rows = within(screen.getByRole('dialog', { name: 'Credits' })).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('Read aloud ×3')
  expect(rows[0]).toHaveTextContent('−15')
  expect(rows[1]).toHaveTextContent('Practice feedback ×2 · mitigate')
  expect(rows[2]).not.toHaveTextContent('×')
})
```

- [ ] **Step 2: 실패 확인** — `cd frontend && npx vitest run src/api.test.ts src/components/CreditsPill.test.tsx 2>&1 | grep -E "×|Tests "`. Expected: 두 테스트 FAIL.

- [ ] **Step 3: 구현** — 위 Interfaces대로. `credit-count`는 `credit-what`과 같은 색, 굵기만 조금 가볍게(`var(--muted)`).

- [ ] **Step 4: 통과 확인** — `npx vitest run`, `npx tsc -b --noEmit`, `npm run lint`. Expected: 실패 없음, 경고 23개 그대로.

- [ ] **Step 5: 커밋** — `detect-changes` 후 `git commit -m "feat: the credit lists send the browser's time zone and show how many rows a line groups"`.

---

### Task 3: 마무리

- [ ] 전체 백엔드와 프런트 테스트, 새 서브에이전트 리뷰 한 번, 고칠 것은 테스트 먼저.
- [ ] spec 상태를 "구현됨"으로, `--ff-only` 합치기, `scripts/bump-version patch`.
- [ ] push와 배포는 사용자가 말할 때. 배포 전에 대화문 채우기가 끝났는지 확인한다.
