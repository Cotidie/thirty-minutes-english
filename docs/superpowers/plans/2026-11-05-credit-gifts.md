# 크레딧 선물 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 태스크를 이 세션에서 직접 실행하고, 끝에 새 서브에이전트 리뷰를 한 번만 한다 (사용자가 정한 방식). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 일반 사용자가 크레딧 패널에서 username으로 받는 사람을 찾고, 액수를 쓰고, 확인 모달에서 한 번 더 누르면 자기 크레딧이 그 사람에게 넘어간다.

**Architecture:** 백엔드는 `CreditRepo.gift`가 한 트랜잭션에서 보낸 사람의 `gift_sent` 줄과 받는 사람의 `gift_received` 줄을 쓰고, 커밋 뒤 두 계정에 `AccountChange.CREDITS`를 publish한다. `POST /api/me/credits/gifts`가 누가 누구에게 보낼 수 있는지 검사하고 저장소를 부른다. 프런트엔드는 새 `GiftCredits` 컴포넌트가 검색, 액수, 확인을 맡고, `CreditsPill`이 패널 안에서 기록 화면과 선물 화면을 바꾸며, 선물 요청이 도는 동안 패널이 닫히지 않게 막는다.

**Tech Stack:** Python 3, FastAPI, pydantic, SQLite, pytest, React 19, TypeScript, vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-05-credit-gifts-design.md`

## Global Constraints

- 브랜치 `feat/credit-gifts`에서 작업한다 (`git switch -c feat/credit-gifts`, spec 커밋 `aa26e6c` 위에서). `main`에는 `--ff-only`로 합치고, 그 뒤 `scripts/bump-version patch`만 쓴다. minor나 major는 올리지 않는다. push와 배포는 사용자가 말할 때만 한다.
- 심볼을 고치기 전에 GitNexus `impact`(`node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .` 또는 MCP `impact`), 커밋 전에 `node .gitnexus/run.cjs detect-changes --scope all --repo .`. HIGH 이상은 보고한다. `risk: UNKNOWN`은 텍스트 검색으로 확인한다. 색인이 `0e3c82a`에 머물러 있으므로 시작할 때 `node .gitnexus/run.cjs analyze --index-only`.
- 커밋 메시지는 제목과 본문뿐이다. `Co-Authored-By`를 넣지 않는다.
- 새 Python, npm 의존성이 없다. 새 셸 스크립트를 만들지 않는다. DB 스키마가 바뀌지 않는다 (`credits.kind`에는 CHECK가 없다).
- 이벤트는 저장소(`backend/app/db`)만, 커밋 뒤에 publish한다. 경로는 publish하지 않는다. 브라우저에서 새 `EventSource`를 열지 않는다. 받는 사람과 보낸 사람의 화면은 기존 `CreditsProvider`(`useAccountResource('credits', ...)`)가 새로 읽는다.
- 코드, 주석, 테스트 이름, 화면 문구는 영어다. 함수 하나는 한 추상화 수준만 말한다 (`/home/humanoid/CLAUDE.md`).
- 화면 문구는 아래 그대로 쓴다. `N`은 숫자, `X`는 username이다.
  - 패널 버튼: "Gift credits". 선물 화면의 돌아가기: "Back".
  - 검색칸 label: "Gift credits to", placeholder: "their username".
  - 고른 뒤 제목: "Gift to X". 숫자 칸 label: "Credits to gift". 잔액 줄: "You have N.".
  - 보내기 버튼: 값이 맞으면 "Gift N credits"(N이 1이면 "Gift 1 credit"), 아니면 "Gift credits".
  - 확인 제목: "Gift N credits to X?"(N이 1이면 "Gift 1 credit to X?"). 본문: "You will have M left. A gift cannot be taken back." 버튼: "Cancel", "Gift".
  - 기록 줄: `gift_sent`는 "Gift to X", `gift_received`는 "Gift from X".
  - 검색 결과가 없을 때: `SharePanel`의 세 문구 그대로 ("No one goes by a name like that.", "The search did not go through. Type again to retry.", "Looking…").
- 서버 문구: "The admin has no credits to give."(400), "account not found"(404), "You cannot gift credits to yourself."(400), "The admin is not charged, so there is nothing to add to."(400), "Not enough credits: this needs N and you have M."(402).
- 백엔드 테스트: `cd backend && .venv/bin/pytest -q` (약 5분). 프런트: `cd frontend && npx vitest run`, `npx tsc -b --noEmit`, `npm run lint`. 시작 기준선(2026-11-05, `aa26e6c`)은 백엔드 634 passed, 프런트 53 files / 497 tests passed다.
- 테스트는 따로 돌리고 결과를 읽은 뒤에 커밋한다. `;`로 잇거나 `tail -1`로 자르지 않는다. 실패 이름은 `grep -E "FAILED|passed|failed"`로 남긴다.
- 운영 서버에서 Create session을 누르지 않는다. 비밀값을 출력하지 않는다.

## 계획에서 정한 것 (spec이 빌더에게 맡긴 것)

- 검색 결과는 react-aria `ComboBox`/`Popover`를 쓰지 않고 패널 안의 평범한 목록(`<ul aria-label="Matches">` 안의 `<button>`)으로 그린다. portal이 없으므로 결과를 눌러도 `useCloseOnLeave`가 패널을 닫지 않는다.
- 확인 모달은 패널 DOM 안에 `role="alertdialog"` 카드로 그리고, CSS로 패널 위를 덮는다 (`position: absolute; inset: 0`, 패널은 이미 `position: fixed`). portal을 쓰지 않으므로 같은 이유로 패널이 닫히지 않는다. 카드가 뜨면 "Cancel"에 focus를 둔다. 되돌릴 수 없는 동작이므로 Enter가 바로 보내지 않게 한다.
- 요청이 도는 동안은 `CreditsPill`이 `useCloseOnLeave(open && !sending, ...)`로 Escape와 바깥 누르기를 끄고, 크레딧 버튼을 다시 눌러도 닫지 않는다.
- 1일 때 단수("1 credit")를 쓴다. spec의 예는 200뿐이다.
- `SharePanel`의 `emptySaying`을 `frontend/src/lib/usePeopleNamed.ts`의 `nobodySaying`으로 옮겨 두 곳이 같이 쓴다.
- 402 문구는 `backend/app/api/deps.py`의 새 `short_of_credits`가 만든다. `held_or_402`와 선물 경로가 같이 쓴다.

## Review Focus

1. 같은 사람이 탭 두 개에서 동시에 보내거나, 선물과 세션 생성이 동시에 들어옴: 잔액이 0 밑으로 가지 않고 한쪽만 통과한다. (Task 1의 `test_two_gifts_at_once_on_one_gift_worth_of_balance_let_only_one_through`)
2. 요청이 도는 동안 Escape, 패널 바깥 누르기, 크레딧 버튼 다시 누르기: 패널이 열린 채로 남고, 답이 오면 기록 화면으로 돌아간다. (Task 4의 `the panel stays open while a gift is on its way`)
3. 검색 결과에서 이름을 누름: 패널이 닫히지 않고 액수 화면으로 넘어간다. (Task 4의 같은 테스트가 이 경로를 지난다)
4. 숫자 칸에 " 200 ", "1e2", "1.5", "-3", "0", 잔액보다 큰 값: 앞뒤 공백만 허용하고 나머지는 버튼이 꺼진다. (Task 3의 `giftable` 테스트)
5. 확인 카드가 열린 사이 잔액이 줄어듦 (다른 탭에서 세션 생성): 서버의 402 문구가 카드 안에 남고 카드는 닫히지 않는다. (Task 3의 `a refused gift keeps the question open with the reason`)

---

### Task 1: 저장소의 선물

**Files:**
- Modify: `backend/app/db/credits.py` (`CreditRepo`에 `gift` 추가)
- Test: `backend/tests/test_credits.py`

**Interfaces:**
- Consumes: 기존 `_balance`, `_release_expired`, `_add_row`, `NotEnoughCredits(need, have)`, `self._db.account_changes.publish(user_id, AccountChange.CREDITS)`.
- Produces: `CreditRepo.gift(self, sender: User, recipient: User, amount: int) -> None`. 잔액이 모자라면 `NotEnoughCredits(amount, balance)`를 던지고 아무 줄도 쓰지 않는다.

- [ ] **Step 1: 시작 준비**

Run: `git switch -c feat/credit-gifts`, 그다음 `node .gitnexus/run.cjs analyze --index-only`.
Expected: 새 브랜치로 바뀌고, 색인이 `aa26e6c` 이후로 갱신된다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`backend/tests/test_credits.py` 끝에 더한다. `funded`, `add_user`, `recorder`, `store`는 이미 있다.

```python
def test_a_gift_moves_credits_and_each_side_reads_who_it_was(store):
    mina = funded(store, 300)
    jun = add_user(store, "jun@example.com")
    store.credits.gift(mina, jun, 200)
    assert (store.credits.balance(mina.id), store.credits.balance(jun.id)) == (100, 200)
    sent, received = store.credits.recent(mina.id)[0], store.credits.recent(jun.id)[0]
    assert (sent.amount, sent.kind, sent.detail) == (-200, "gift_sent", "jun")
    assert (received.amount, received.kind, received.detail) == (200, "gift_received", "mina")
    with store.connect() as conn:
        givers = [row[0] for row in conn.execute("SELECT granted_by FROM credits WHERE kind LIKE 'gift_%' ORDER BY id")]
    assert givers == [mina.id, mina.id]


def test_a_gift_beyond_the_balance_moves_nothing(store):
    mina = funded(store, 150)
    jun = add_user(store, "jun@example.com")
    with pytest.raises(NotEnoughCredits) as refused:
        store.credits.gift(mina, jun, 200)
    assert (refused.value.need, refused.value.have) == (200, 150)
    assert (store.credits.balance(mina.id), store.credits.balance(jun.id)) == (150, 0)
    assert store.credits.recent(jun.id) == []


def test_credits_held_for_running_work_cannot_be_gifted(store):
    mina = funded(store, 250)
    jun = add_user(store, "jun@example.com")
    store.credits.hold(mina, "session", "Trams")
    with pytest.raises(NotEnoughCredits) as refused:
        store.credits.gift(mina, jun, 100)
    assert (refused.value.need, refused.value.have) == (100, 50)


def test_two_gifts_at_once_on_one_gift_worth_of_balance_let_only_one_through(store):
    mina = funded(store, 200)
    jun = add_user(store, "jun@example.com")
    results: list[str] = []
    gate = threading.Barrier(2)

    def go():
        gate.wait()
        try:
            store.credits.gift(mina, jun, 200)
            results.append("given")
        except NotEnoughCredits:
            results.append("refused")

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["given", "refused"]
    assert (store.credits.balance(mina.id), store.credits.balance(jun.id)) == (0, 200)


def test_a_gift_tells_both_accounts_to_read_their_credits_again(store, recorder):
    mina = funded(store, 300)
    jun = add_user(store, "jun@example.com")
    recorder.published.clear()
    store.credits.gift(mina, jun, 50)
    assert recorder.published == [(mina.id, AccountChange.CREDITS), (jun.id, AccountChange.CREDITS)]
```

- [ ] **Step 3: 실패를 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_credits.py -q -k gift`
Expected: 5 failed, `AttributeError: 'CreditRepo' object has no attribute 'gift'`.

- [ ] **Step 4: `CreditRepo.gift(self, sender: User, recipient: User, amount: int) -> None`을 `backend/app/db/credits.py`에 쓴다**

`hold`를 impact로 먼저 확인하고(읽기만 한다), 그 바로 아래에 둔다. `hold`와 같은 순서다: `BEGIN IMMEDIATE`, `_release_expired(conn)`, `_balance(conn, sender.id)`가 `amount`보다 작으면 `NotEnoughCredits(amount, balance)`. 그다음 `_add_row(conn, sender.id, -amount, "gift_sent", recipient.username, sender.id)`와 `_add_row(conn, recipient.id, amount, "gift_received", sender.username, sender.id)`. `with` 블록을 나온 뒤(커밋 뒤) 보낸 사람, 받는 사람 순서로 `AccountChange.CREDITS`를 publish한다. docstring은 두 줄이 함께 들어가거나 함께 안 들어간다는 것과, hold에 잡힌 크레딧은 줄 수 없다는 것을 말한다.

- [ ] **Step 5: 통과를 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_credits.py -q`
Expected: 모두 passed.

- [ ] **Step 6: 커밋**

detect-changes를 돌린 뒤:

```bash
git add backend/app/db/credits.py backend/tests/test_credits.py
git commit -m "feat: an account can gift credits to another in one transaction"
```

---

### Task 2: 선물 경로

**Files:**
- Modify: `backend/app/api/schemas.py` (`GiftRequest` 추가)
- Modify: `backend/app/api/deps.py` (`short_of_credits` 추가, `held_or_402`가 그것을 씀)
- Modify: `backend/app/api/credits.py` (`POST /credits/gifts`)
- Test: `backend/tests/test_credits.py`

**Interfaces:**
- Consumes: Task 1의 `CreditRepo.gift(sender, recipient, amount)`, `db.accounts.get(user_id) -> User | None`.
- Produces: `POST /api/me/credits/gifts`, 본문 `{"to": int, "amount": int}`, 성공 시 204. `short_of_credits(e: NotEnoughCredits) -> HTTPException`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_credits.py` 끝에 더한다.

```python
def gift_world(tmp_path):
    """mina with 300 credits and jun with none, and the app they use."""
    db = Database(tmp_path / "s.db")
    app = create_app(db, Services(FakeGenerator()), InlineExecutor())
    mina = funded(db, 300)
    jun = add_user(db, "jun@example.com")
    return db, app, mina, jun


def test_a_gift_through_the_route_answers_204_and_moves_the_credits(tmp_path):
    db, app, mina, jun = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": jun.id, "amount": 200})
    assert answer.status_code == 204
    assert (db.credits.balance(mina.id), db.credits.balance(jun.id)) == (100, 200)


def test_a_gift_to_oneself_is_refused(tmp_path):
    db, app, mina, _ = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": mina.id, "amount": 50})
    assert (answer.status_code, answer.json()["detail"]) == (400, "You cannot gift credits to yourself.")
    assert db.credits.balance(mina.id) == 300


def test_a_gift_to_the_admin_is_refused(tmp_path):
    db, app, mina, _ = gift_world(tmp_path)
    boss = add_user(db, "boss@example.com", admin=True)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": boss.id, "amount": 50})
    assert (answer.status_code, answer.json()["detail"]) == (400, "The admin is not charged, so there is nothing to add to.")
    assert db.credits.balance(mina.id) == 300


def test_the_admin_has_no_credits_to_give(tmp_path):
    db, app, _, jun = gift_world(tmp_path)
    answer = admin_client(app).post("/api/me/credits/gifts", json={"to": jun.id, "amount": 50})
    assert (answer.status_code, answer.json()["detail"]) == (400, "The admin has no credits to give.")
    assert db.credits.balance(jun.id) == 0


def test_a_gift_to_no_account_is_not_found(tmp_path):
    db, app, mina, _ = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": 999, "amount": 50})
    assert (answer.status_code, answer.json()["detail"]) == (404, "account not found")


@pytest.mark.parametrize("amount", [0, -5])
def test_a_gift_of_nothing_or_less_is_not_a_gift(tmp_path, amount):
    db, app, mina, jun = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": jun.id, "amount": amount})
    assert answer.status_code == 422
    assert (db.credits.balance(mina.id), db.credits.balance(jun.id)) == (300, 0)


def test_a_gift_beyond_the_balance_says_what_it_needs(tmp_path):
    db, app, mina, jun = gift_world(tmp_path)
    answer = client_of(app, db, mina).post("/api/me/credits/gifts", json={"to": jun.id, "amount": 500})
    assert (answer.status_code, answer.json()["detail"]) == (402, "Not enough credits: this needs 500 and you have 300.")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_credits.py -q`
Expected: 이 단계에서 더한 8개(parametrize 2개 포함)만 failed, 나머지는 passed. 경로가 없으므로 404/405가 나와 상태 코드 단언에서 실패한다.

- [ ] **Step 3: `GiftRequest`를 `backend/app/api/schemas.py`의 `GrantRequest` 아래에 둔다**

```python
class GiftRequest(BaseModel):
    """Credits the one who asks hands to another account."""

    to: int
    amount: int = Field(ge=1)
```

- [ ] **Step 4: `short_of_credits(e: NotEnoughCredits) -> HTTPException`을 `backend/app/api/deps.py`에 두고 `held_or_402`가 쓰게 한다**

`held_or_402`를 impact로 먼저 확인한다. 돌려주는 값은 지금 `held_or_402`가 만드는 것과 같다: `HTTPException(status_code=402, detail=f"Not enough credits: this needs {e.need} and you have {e.have}.")`. `held_or_402`는 `raise short_of_credits(e) from None`이 된다.

- [ ] **Step 5: `POST /credits/gifts`를 `backend/app/api/credits.py`에 쓴다**

`def gift_credits(body: GiftRequest, db: Db, me: Me) -> Response`, `@router.post("/credits/gifts", status_code=204)`. 검사 순서와 문구는 Global Constraints의 서버 문구 그대로다: 보낸 사람이 관리자(400) → `db.accounts.get(body.to)`가 없음(404) → 자기 자신(400) → 받는 사람이 관리자(400) → `db.credits.gift(me, recipient, body.amount)`, `NotEnoughCredits`는 `raise short_of_credits(e) from None`. 성공하면 `Response(status_code=204)`. 함수 본문이 검사 넷과 저장소 호출로 길어지면, 누가 누구에게 보낼 수 있는지를 `_recipient_for(db, me, to) -> User` 같은 private helper로 뺀다. 경로는 publish하지 않는다.

- [ ] **Step 6: 통과를 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_credits.py tests/test_accounts.py -q`
Expected: 모두 passed. 기존 402 문구 테스트도 그대로 통과한다.

- [ ] **Step 7: 커밋**

detect-changes를 돌린 뒤:

```bash
git add backend/app/api/schemas.py backend/app/api/deps.py backend/app/api/credits.py backend/tests/test_credits.py
git commit -m "feat: POST /api/me/credits/gifts hands credits to another account"
```

---

### Task 3: 선물 화면 컴포넌트

**Files:**
- Create: `frontend/src/components/GiftCredits.tsx`
- Create: `frontend/src/components/GiftCredits.test.tsx`
- Modify: `frontend/src/components/CreditsPill.css` (선물 화면과 확인 카드 모양)
- Modify: `frontend/src/api.ts` (`giftCredits`)
- Modify: `frontend/src/lib/usePeopleNamed.ts` (`nobodySaying` 추가)
- Modify: `frontend/src/components/SharePanel.tsx` (`emptySaying`을 지우고 `nobodySaying`을 씀)

**Interfaces:**
- Consumes: Task 2의 `POST /api/me/credits/gifts`. 기존 `usePeopleNamed(text): PeopleNamed`, `ApiError`.
- Produces:
  - `api.giftCredits(to: number, amount: number): Promise<void>`
  - `nobodySaying(found: PeopleNamed): string`
  - `giftable(text: string, balance: number): number | null`
  - `GiftCredits({ balance, onClose, onSending }: { balance: number; onClose: () => void; onSending: (sending: boolean) => void })`. `onClose`는 Back을 눌렀을 때와 선물이 성공했을 때 불린다. `onSending(true)`는 요청을 보낼 때, `onSending(false)`는 답이 왔을 때 (성공이든 실패든) 불린다. 성공이면 `onSending(false)` 다음에 `onClose()`다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`frontend/src/components/GiftCredits.test.tsx`:

```tsx
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { ApiError, api } from '../api'
import { GiftCredits, giftable } from './GiftCredits'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { findPeople: vi.fn(), giftCredits: vi.fn() },
}))

beforeEach(() => {
  vi.mocked(api.findPeople).mockReset().mockResolvedValue([{ id: 3, username: 'minji' }])
  vi.mocked(api.giftCredits).mockReset().mockResolvedValue(undefined)
})

function setup(balance = 240) {
  const onClose = vi.fn()
  const onSending = vi.fn()
  render(<GiftCredits balance={balance} onClose={onClose} onSending={onSending} />)
  return { onClose, onSending }
}

async function askToGift(amount: string) {
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'min')
  await userEvent.click(await screen.findByRole('button', { name: 'minji' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Credits to gift' }), amount)
  await userEvent.click(screen.getByRole('button', { name: `Gift ${amount} credits` }))
}

test('only a whole number from 1 to the balance can be gifted', () => {
  expect(giftable('200', 240)).toBe(200)
  expect(giftable(' 240 ', 240)).toBe(240)
  expect(giftable('1', 240)).toBe(1)
  for (const text of ['', '0', '-3', '1.5', '1e2', 'abc', '241']) expect(giftable(text, 240)).toBeNull()
})

test('a name found and an amount typed ask once, then the gift goes', async () => {
  const { onClose, onSending } = setup()
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'min')
  await userEvent.click(await screen.findByRole('button', { name: 'minji' }))
  expect(screen.getByRole('heading', { name: 'Gift to minji' })).toBeInTheDocument()
  expect(screen.getByText('You have 240.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Gift credits' })).toBeDisabled()
  await userEvent.type(screen.getByRole('textbox', { name: 'Credits to gift' }), '200')
  await userEvent.click(screen.getByRole('button', { name: 'Gift 200 credits' }))
  const ask = screen.getByRole('alertdialog', { name: 'Gift 200 credits to minji?' })
  expect(ask).toHaveTextContent('You will have 40 left. A gift cannot be taken back.')
  expect(within(ask).getByRole('button', { name: 'Cancel' })).toHaveFocus()
  await userEvent.click(within(ask).getByRole('button', { name: 'Gift' }))
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  expect(api.giftCredits).toHaveBeenCalledTimes(1)
  expect(api.giftCredits).toHaveBeenCalledWith(3, 200)
  expect(onSending.mock.calls).toEqual([[true], [false]])
})

test('one credit reads as one credit', async () => {
  setup()
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'min')
  await userEvent.click(await screen.findByRole('button', { name: 'minji' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Credits to gift' }), '1')
  await userEvent.click(screen.getByRole('button', { name: 'Gift 1 credit' }))
  expect(screen.getByRole('alertdialog', { name: 'Gift 1 credit to minji?' })).toBeInTheDocument()
})

test('Cancel sends nothing and keeps the amount', async () => {
  setup()
  await askToGift('200')
  await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  expect(api.giftCredits).not.toHaveBeenCalled()
  expect(screen.getByRole('textbox', { name: 'Credits to gift' })).toHaveValue('200')
})

test('a refused gift keeps the question open with the reason', async () => {
  vi.mocked(api.giftCredits).mockRejectedValue(new ApiError(402, 'Not enough credits: this needs 200 and you have 150.'))
  const { onClose, onSending } = setup()
  await askToGift('200')
  const ask = screen.getByRole('alertdialog')
  await userEvent.click(within(ask).getByRole('button', { name: 'Gift' }))
  expect(await within(ask).findByRole('alert')).toHaveTextContent('Not enough credits: this needs 200 and you have 150.')
  expect(within(ask).getByRole('button', { name: 'Cancel' })).toBeEnabled()
  expect(onClose).not.toHaveBeenCalled()
  expect(onSending.mock.calls).toEqual([[true], [false]])
})

test('while the gift is on its way neither button can be pressed', async () => {
  let land = () => {}
  vi.mocked(api.giftCredits).mockReturnValue(new Promise<void>((resolve) => (land = resolve)))
  const { onClose } = setup()
  await askToGift('200')
  const ask = screen.getByRole('alertdialog')
  await userEvent.click(within(ask).getByRole('button', { name: 'Gift' }))
  expect(within(ask).getByRole('button', { name: 'Gift' })).toBeDisabled()
  expect(within(ask).getByRole('button', { name: 'Cancel' })).toBeDisabled()
  land()
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
})

test('a name nobody has says so', async () => {
  vi.mocked(api.findPeople).mockResolvedValue([])
  setup()
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'zz')
  expect(await screen.findByText('No one goes by a name like that.')).toBeInTheDocument()
})

test('Back leaves without a gift', async () => {
  const { onClose } = setup()
  await userEvent.click(screen.getByRole('button', { name: 'Back' }))
  expect(onClose).toHaveBeenCalledTimes(1)
  expect(api.giftCredits).not.toHaveBeenCalled()
})
```

`askToGift`는 복수형 이름의 버튼을 누르므로, 1을 다루는 `one credit reads as one credit`는 그 helper를 쓰지 않는다.

- [ ] **Step 2: 실패를 확인한다**

Run: `cd frontend && npx vitest run src/components/GiftCredits.test.tsx`
Expected: FAIL, `GiftCredits.tsx`를 찾지 못한다는 import 오류.

- [ ] **Step 3: `api.giftCredits`와 `nobodySaying`을 더하고 `SharePanel`을 옮긴다**

`emptySaying`을 impact로 먼저 확인한다. `frontend/src/api.ts`의 `myCredits` 옆에 `giftCredits: (to: number, amount: number) => request<void>('/api/me/credits/gifts', { method: 'POST', body: JSON.stringify({ to, amount }) })`. `SharePanel.tsx`의 `emptySaying` 본문을 그대로 `usePeopleNamed.ts`의 `export function nobodySaying(found: PeopleNamed): string`으로 옮기고, `SharePanel`은 그것을 import한다.

- [ ] **Step 4: `GiftCredits`와 `giftable`을 `frontend/src/components/GiftCredits.tsx`에 쓴다**

- `giftable`: `text.trim()`이 `/^\d+$/`에 맞고, 그 수가 1 이상 `balance` 이하이면 그 수, 아니면 `null`.
- 상태: 검색 글자, 고른 사람(`PersonMatch | null`), 숫자 칸 글자, 확인 중인지, 보내는 중인지, 오류 문구.
- 고르기 전: "Back" 링크(`button.btn-link`), label "Gift credits to"인 검색칸(placeholder "their username", `autoCapitalize="none"`, `spellCheck={false}`, `autoFocus`). 검색 글자가 비어 있지 않으면 `usePeopleNamed`의 `people`을 `<ul aria-label="Matches">` 안의 `<button type="button">`으로 보여 주고, `people`이 비었으면 `nobodySaying(found)`를 보여 준다.
- 고른 뒤: "Back", `<h3>Gift to X</h3>`, label "Credits to gift"인 `<input type="text" inputMode="numeric" autoFocus>`, "You have N.", 보내기 버튼(`giftable`이 `null`이면 "Gift credits"이고 disabled).
- 확인 카드: `role="alertdialog"`, 제목 id로 `aria-labelledby`, 본문, "Cancel"(`autoFocus`), "Gift". 남는 액수는 `balance - amount`. 보내는 중이면 두 버튼 모두 disabled. 실패하면 카드 안 `<p role="alert">`에 `(e as Error).message`.
- 단수와 복수는 작은 helper 하나(`creditCount(n)`: 1이면 "1 credit", 아니면 "N credits")로 버튼과 제목이 같이 쓴다.
- 모양은 `CreditsPill.css`에 더한다. 확인 카드를 덮는 층은 `.credits-panel` 안에서 `position: absolute; inset: 0`이다. 목록 버튼은 `SharePanel.css`의 `.share-match` 모양을 따른다.

- [ ] **Step 5: 통과를 확인한다**

Run: `cd frontend && npx vitest run src/components/GiftCredits.test.tsx src/components/SharePanel.test.tsx`
Expected: 모두 passed.

- [ ] **Step 6: 커밋**

detect-changes를 돌린 뒤:

```bash
git add frontend/src/components/GiftCredits.tsx frontend/src/components/GiftCredits.test.tsx frontend/src/components/CreditsPill.css frontend/src/api.ts frontend/src/lib/usePeopleNamed.ts frontend/src/components/SharePanel.tsx
git commit -m "feat: a gift screen that finds someone, takes an amount and asks once"
```

---

### Task 4: 크레딧 패널에 선물을 붙이고 기록 줄을 읽기

**Files:**
- Modify: `frontend/src/components/CreditsPill.tsx` (`CreditsPill`, `CreditLine`)
- Modify: `frontend/src/components/CreditsPill.test.tsx`
- Modify: `docs/superpowers/specs/2026-11-05-credit-gifts-design.md` (상태 줄)

**Interfaces:**
- Consumes: Task 3의 `GiftCredits({ balance, onClose, onSending })`, `api.findPeople`, `api.giftCredits`.
- Produces: 없음 (화면의 끝).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`frontend/src/components/CreditsPill.test.tsx`의 import에 `waitFor`와 `api`를 더하고, 파일 위쪽에 api mock을 둔다:

```tsx
import { api } from '../api'

vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  api: { findPeople: vi.fn(), giftCredits: vi.fn() },
}))

beforeEach(() => {
  vi.mocked(api.findPeople).mockReset().mockResolvedValue([{ id: 3, username: 'minji' }])
  vi.mocked(api.giftCredits).mockReset().mockResolvedValue(undefined)
})
```

그리고 테스트를 더한다:

```tsx
test('gifts read as to and from whom, with nothing after', async () => {
  has(90, [
    { at: '2026-11-05T09:00:00Z', amount: -200, kind: 'gift_sent', detail: 'minji' },
    { at: '2026-11-04T09:00:00Z', amount: 50, kind: 'gift_received', detail: 'jun' },
  ])
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  const rows = within(screen.getByRole('dialog', { name: 'Credits' })).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('Gift to minji')
  expect(rows[0]).toHaveTextContent('−200')
  expect(rows[1]).toHaveTextContent('Gift from jun')
  expect(rows[1]).toHaveTextContent('+50')
  expect(rows[0].querySelector('.credit-detail')).toBeNull()
  expect(rows[1].querySelector('.credit-detail')).toBeNull()
})

test('the gift button opens the gift screen and Back returns to the charges', async () => {
  has(240)
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  await userEvent.click(screen.getByRole('button', { name: 'Gift credits' }))
  expect(screen.getByRole('textbox', { name: 'Gift credits to' })).toBeInTheDocument()
  expect(screen.queryByText('No charges yet.')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Back' }))
  expect(screen.getByText('No charges yet.')).toBeInTheDocument()
})

test('with nothing to give the gift button cannot be pressed', async () => {
  has(0)
  render(<CreditsPill />)
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  expect(screen.getByRole('button', { name: 'Gift credits' })).toBeDisabled()
})

test('the panel stays open while a gift is on its way', async () => {
  let land = () => {}
  vi.mocked(api.giftCredits).mockReturnValue(new Promise<void>((resolve) => (land = resolve)))
  has(240)
  render(
    <>
      <p>elsewhere</p>
      <CreditsPill />
    </>,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  await userEvent.click(screen.getByRole('button', { name: 'Gift credits' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Gift credits to' }), 'min')
  await userEvent.click(await screen.findByRole('button', { name: 'minji' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Credits to gift' }), '200')
  await userEvent.click(screen.getByRole('button', { name: 'Gift 200 credits' }))
  await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Gift' }))
  await userEvent.keyboard('{Escape}')
  await userEvent.click(screen.getByText('elsewhere'))
  await userEvent.click(screen.getByRole('button', { name: 'Credits' }))
  expect(screen.getByRole('dialog', { name: 'Credits' })).toBeInTheDocument()
  land()
  await waitFor(() => expect(screen.getByRole('dialog', { name: 'Credits' })).toHaveTextContent('Ask the admin for more.'))
})
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd frontend && npx vitest run src/components/CreditsPill.test.tsx`
Expected: 새 테스트 4개 FAIL ("Gift credits" 버튼이 없고, 기록 줄이 `gift_sent`를 그대로 보여 준다). 기존 6개는 passed.

- [ ] **Step 3: `CreditLine`이 선물 줄을 읽게 한다**

`CreditLine`을 impact로 먼저 확인한다 (`AccountsPanel`도 쓴다). 레이블을 정하는 작은 helper(`lineLabel(entry, grantedBy): string`)로 뺀다: `gift_sent`는 `Gift to ${entry.detail}`, `gift_received`는 `Gift from ${entry.detail}`, `grant`와 나머지는 지금 그대로. 두 선물 kind에서는 `.credit-detail` 꼬리를 그리지 않는다.

- [ ] **Step 4: `CreditsPill`에 선물 화면을 붙인다**

`CreditsPill`을 impact로 먼저 확인한다.
- 상태 `gifting: boolean`, `sending: boolean`을 더한다.
- `close`는 `open`과 `gifting`을 모두 false로 만든다. `useCloseOnLeave(open && !sending, here, close)`.
- 크레딧 버튼은 `sending`이면 아무것도 하지 않는다. 그 밖에는 열려 있으면 `close()`, 닫혀 있으면 연다.
- 패널 안: `gifting`이면 `<GiftCredits balance={balance} onClose={() => setGifting(false)} onSending={setSending} />`, 아니면 지금의 잔액, 기록, "Ask the admin for more."와 그 아래 "Gift credits" 버튼(`balance <= 0`이면 disabled).
- 컴포넌트 docstring에 선물 화면이 같은 패널 안에서 열린다는 것을 한 줄 더한다.

- [ ] **Step 5: 통과를 확인한다**

Run: `cd frontend && npx vitest run src/components/CreditsPill.test.tsx src/components/GiftCredits.test.tsx src/components/AccountsPanel.test.tsx`
Expected: 모두 passed.

- [ ] **Step 6: 프런트 전체를 확인한다**

Run: `cd frontend && npx vitest run`, 그다음 `npx tsc -b --noEmit`, 그다음 `npm run lint`. 셋은 따로 돌린다.
Expected: vitest는 54 files / 509 tests passed (기준선 53 / 497에 Task 3의 8개, Task 4의 4개). tsc와 lint는 오류 없음.

- [ ] **Step 7: spec의 상태 줄을 고친다**

`docs/superpowers/specs/2026-11-05-credit-gifts-design.md`의 첫 항목을 "상태: 구현됨 (2026-11-05). 구현 계획: `docs/superpowers/plans/2026-11-05-credit-gifts.md`."로 바꾼다. 구현 중에 spec과 달라진 것이 있으면 그 자리의 문장도 고친다.

- [ ] **Step 8: 커밋**

detect-changes를 돌린 뒤:

```bash
git add frontend/src/components/CreditsPill.tsx frontend/src/components/CreditsPill.test.tsx docs/superpowers/specs/2026-11-05-credit-gifts-design.md
git commit -m "feat: gift credits from the credits panel"
```

---

## 끝난 뒤

1. 백엔드 전체: `cd backend && .venv/bin/pytest -q -p no:cacheprovider > <workspace>/backend-final.txt 2>&1`, 그다음 `grep -E "FAILED|passed|failed" <workspace>/backend-final.txt`. 647 passed여야 한다 (기준선 634에 Task 1의 5개, Task 2의 8개).
2. executing-plans의 마지막 리뷰(가장 강한 모델의 새 서브에이전트 한 번). Review Focus를 그대로 넘긴다.
3. superpowers:finishing-a-development-branch. `main`에 `--ff-only`로 합치는 것과 `scripts/bump-version patch`, push, 배포는 사용자가 말할 때만 한다.
