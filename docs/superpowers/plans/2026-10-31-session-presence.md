# 세션 현존감 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세션 화면 안에서 서로의 커서, 있는 탭, 뒤집어 본 화면 요소, 타이머를 실시간으로 공유한다.

**Architecture:** `WS /api/sessions/{id}/presence` 하나가 저장되지 않는 값만 나른다. 서버는 프레임워크를 모르는 방 모델(`app/live/presence.py`)과 얇은 라우트로, 브라우저는 소켓을 독점하는 연결 모듈과 React 밖의 스토어로 나눈다. 스토어가 없으면 모든 것이 지금처럼 지역 상태로 동작한다.

**Tech Stack:** FastAPI WebSocket, uvicorn의 `websockets`, React 19, `partysocket`, pytest, vitest, Playwright(저장소 밖 검증 스크립트)

**Spec:** `docs/superpowers/specs/2026-10-31-session-presence-design.md`

## Global Constraints

- 새 Python 의존성 없음. 새 npm 의존성은 `partysocket`(^1.3.0) 하나, `package-lock.json` 함께 커밋.
- `partysocket`을 import하는 파일은 `frontend/src/lib/presence/connection.ts` 하나뿐이고, `maxEnqueuedMessages: 0`으로 만든다.
- 메시지에 계정 번호나 이메일을 넣지 않는다.
- 커서 메시지는 React 상태를 바꾸지 않는다.
- 값을 받아 적용할 때 다시 보내지 않는다.
- 상대의 행동으로 내 마이크나 소리가 시작되지 않는다. `ArticleTab.reading`, `ReadAloud`, `Practice`, `Summarize`, `SpeakButton`, `NoteBox.open`은 건드리지 않는다.
- 타이머는 탭을 옮기지 않는다.
- 웹소켓이 끊겨도 칩, 카드, 타이머는 혼자서 동작한다. 끊김 표시는 하지 않는다.
- 편집 전 GitNexus `impact`, 커밋 전 `detect_changes`. 커밋 메시지에 `Co-Authored-By`를 넣지 않는다. 화면 문구는 영어(한국어 학습 문구 제외).
- 병합 후 `scripts/bump-version patch`만 쓴다.

## Review Focus

1. 두 사람이 같은 칩을 거의 동시에 누른다: 양쪽 화면이 같은 값으로 끝나야 한다. (Task 3의 스토어 테스트)
2. 숨겨진 탭에서 `setInterval`이 느려진다: 돌아왔을 때 타이머가 뒤처지지 않아야 한다. (Task 5)
3. 끊겼다 다시 붙는다: 그동안 나간 사람의 점과 커서가 남지 않고, 옛 커서 위치가 한꺼번에 나가지 않아야 한다. (Task 3)
4. 상대가 가리키는 요소가 내 화면에 없거나 크기가 0이다(표현 교체, 다른 레이아웃): 커서가 (0, 0)이나 NaN에 그려지지 않고 사라져야 한다. (Task 7)
5. 작별 없이 사라진다(창 닫기, 세션 삭제, 공유 해제, 로그아웃): 다른 사람 화면에서 사라지고, 쫓겨난 사람의 소켓은 재시도하지 않아야 한다. (Task 2, Task 3)

## 메시지 계약

모든 태스크가 따른다. JSON 텍스트 프레임, 1024바이트 이하.

브라우저에서 서버로:

```json
{"type": "cursor", "tab": 0, "anchor": "expression:12", "x": 0.31, "y": 0.62}
{"type": "cursor", "tab": 0, "anchor": null}
{"type": "tab", "tab": 2}
{"type": "view", "key": "chip:word:2", "value": true, "seq": 7}
{"type": "timer", "running": true, "elapsed": 65, "seq": 8}
```

서버에서 브라우저로:

```json
{"type": "welcome", "you": {"id": "a1b2", "color": 1}, "people": [{"id": "c3d4", "color": 0, "tab": 2}], "view": {"chip:word:2": true}, "timer": {"running": true, "elapsed": 65}}
{"type": "joined", "id": "c3d4", "color": 0, "tab": null}
{"type": "left", "id": "c3d4"}
{"type": "tab", "id": "c3d4", "tab": 2}
{"type": "cursor", "id": "c3d4", "tab": 0, "anchor": "expression:12", "x": 0.31, "y": 0.62}
{"type": "view", "key": "chip:word:2", "value": true, "by": "a1b2", "seq": 7}
{"type": "timer", "running": true, "elapsed": 65, "by": "a1b2", "seq": 8}
```

- `welcome.timer`는 아무도 건드리지 않았으면 `null`이다.
- `cursor`, `tab`, `joined`, `left`와 `welcome.people`은 **다른 계정의 연결만** 대상이다.
- `view`, `timer`는 **보낸 사람을 포함한 방 전체**에 서버가 받은 순서대로 간다.
- 닫는 코드: `4401` 로그인 없음, `4403` 다른 Origin, `4404` 세션 없음이나 접근권 없음.
- 상한: `tab` 0~9, `x`, `y` 0~1, `anchor`는 `^[a-z-]+(:[0-9]+)?$`이고 40자 이하, `key`는 `^[a-z]+(:[a-z0-9]+)*$`이고 80자 이하, `value`는 불리언, 유한한 숫자, 32자 이하 문자열, `null`, `elapsed` 0~86400, 방당 키 2000개, 연결당 커서 초당 40개, 보낼 큐 256개. 벗어난 프레임은 조용히 버린다.

---

### Task 1: 방 모델

**Files:**
- Create: `backend/app/live/presence.py`
- Test: `backend/tests/test_presence_room.py`

**Interfaces:**
- Produces:
  - `color_order(creator_id: int | None, shared_ids: Iterable[int], user_id: int) -> int`
  - `Outbox`: `take() -> list[dict]`, `async wait() -> None`, `overflowed: bool`
  - `Member`: `id: str`, `user_id: int`, `color: int`, `tab: int | None`, `outbox: Outbox`
  - `Room`: `welcome(member) -> dict`, `handle(member, raw: str) -> None`
  - `Rooms(keep_seconds: float = 600, clock: Callable[[], float] = time.monotonic)`: `join(session_id, user_id, preferred_color) -> tuple[Room, Member]`, `leave(session_id, member) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def cursor(x=0.5): return json.dumps({"type": "cursor", "tab": 0, "anchor": "brief", "x": x, "y": 0.5})
def view(key="chip:word:2", value=True, seq=1): return json.dumps({"type": "view", "key": key, "value": value, "seq": seq})

def test_joining_tells_me_who_is_here_and_tells_them_about_me():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    welcome = room.welcome(jo)
    assert welcome["you"] == {"id": jo.id, "color": 1}
    assert welcome["people"] == [{"id": mina.id, "color": 0, "tab": None}]
    assert welcome["view"] == {} and welcome["timer"] is None
    assert mina.outbox.take() == [{"type": "joined", "id": jo.id, "color": 1, "tab": None}]

def test_a_cursor_and_a_tab_go_to_other_accounts_only():
    rooms = Rooms()
    room, mine = rooms.join(1, 10, 0)
    _, my_other_tab = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    for m in (mine, my_other_tab, jo): m.outbox.take()
    room.handle(mine, cursor())
    room.handle(mine, json.dumps({"type": "tab", "tab": 2}))
    assert my_other_tab.outbox.take() == []
    assert [m["type"] for m in jo.outbox.take()] == ["cursor", "tab"]
    assert room.welcome(my_other_tab)["people"] == [{"id": jo.id, "color": 1, "tab": None}]
    assert {"id": mine.id, "color": 0, "tab": 2} in room.welcome(jo)["people"]

def test_someone_coming_late_sees_a_cursor_that_is_standing_still():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    room.handle(mina, cursor(0.3))
    _, jo = rooms.join(1, 20, 1)
    assert [(m["type"], m["id"], m["x"]) for m in jo.outbox.take()] == [("cursor", mina.id, 0.3)]

def test_a_cursor_may_say_there_is_none():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    mina.outbox.take()
    room.handle(mina, cursor(0.3))
    room.handle(mina, json.dumps({"type": "cursor", "tab": 0, "anchor": None}))
    assert jo.outbox.take() == [{"type": "cursor", "id": mina.id, "tab": 0, "anchor": None}]
    _, late = rooms.join(1, 30, 2)
    assert late.outbox.take() == []

def test_view_goes_back_to_everyone_in_the_order_it_came_saying_who_sent_it():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    for m in (mina, jo): m.outbox.take()
    room.handle(mina, view(value=True, seq=1))
    room.handle(jo, view(value=False, seq=1))
    expected = [
        {"type": "view", "key": "chip:word:2", "value": True, "by": mina.id, "seq": 1},
        {"type": "view", "key": "chip:word:2", "value": False, "by": jo.id, "seq": 1},
    ]
    assert mina.outbox.take() == expected and jo.outbox.take() == expected
    assert room.welcome(mina)["view"] == {"chip:word:2": False}

def test_only_the_newest_cursor_of_a_person_waits_and_keeps_its_place():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    for m in (mina, jo): m.outbox.take()
    room.handle(mina, cursor(0.1))
    room.handle(mina, view())
    room.handle(mina, cursor(0.9))
    assert [(m["type"], m.get("x")) for m in jo.outbox.take()] == [("cursor", 0.9), ("view", None)]

def test_someone_who_left_leaves_no_cursor_behind():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    for m in (mina, jo): m.outbox.take()
    room.handle(mina, cursor())
    rooms.leave(1, mina)
    assert jo.outbox.take() == [{"type": "left", "id": mina.id}]

@pytest.mark.parametrize("raw", [
    "not json", "[]", '{"type": "shout"}', "x" * 1025,
    view(key="Bad Key"), view(key="a" * 81), view(value={"a": 1}), view(value="x" * 33),
    '{"type": "view", "key": "k", "value": NaN, "seq": 1}',
    cursor(2), json.dumps({"type": "tab", "tab": -1}), json.dumps({"type": "tab", "tab": 10}),
    json.dumps({"type": "timer", "running": True, "elapsed": -1, "seq": 1}),
    json.dumps({"type": "timer", "running": "yes", "elapsed": 1, "seq": 1}),
])
def test_a_bad_frame_is_dropped_and_changes_nothing(raw): ...  # 다른 사람의 outbox가 비어 있고 welcome이 그대로

def test_a_room_stops_taking_new_keys_at_2000_but_keeps_updating_old_ones(): ...
def test_cursors_past_40_a_second_are_dropped(): ...  # 가짜 clock, 41번째만 버려짐, 1초 뒤 다시 통과
def test_a_full_outbox_says_so(): ...  # 보낼 것 257개째에 overflowed is True

def test_the_room_outlives_the_last_person_by_ten_minutes():
    now = [0.0]
    rooms = Rooms(clock=lambda: now[0])
    room, mina = rooms.join(1, 10, 0)
    room.handle(mina, view())
    rooms.leave(1, mina)
    now[0] = 599.0
    room, jo = rooms.join(1, 20, 1)
    assert room.welcome(jo)["view"] == {"chip:word:2": True}
    rooms.leave(1, jo)
    now[0] = 599.0 + 601.0
    room, jo = rooms.join(1, 20, 1)
    assert room.welcome(jo)["view"] == {}

def test_the_timer_counts_on_while_running_and_stands_still_when_paused():
    now = [0.0]
    rooms = Rooms(clock=lambda: now[0])
    room, mina = rooms.join(1, 10, 0)
    room.handle(mina, json.dumps({"type": "timer", "running": True, "elapsed": 60, "seq": 1}))
    now[0] = 5.0
    assert room.welcome(mina)["timer"] == {"running": True, "elapsed": 65}
    room.handle(mina, json.dumps({"type": "timer", "running": False, "elapsed": 65, "seq": 2}))
    now[0] = 50.0
    assert room.welcome(mina)["timer"] == {"running": False, "elapsed": 65}

def test_color_order():
    assert color_order(5, [9, 7], 5) == 0
    assert color_order(5, [9, 7], 7) == 1
    assert color_order(5, [9, 7], 9) == 2
    assert color_order(5, [9, 7], 1) == 3  # 목록에 없는 운영자

def test_a_taken_color_gives_way_and_a_second_connection_keeps_its_color():
    rooms = Rooms()
    _, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 0)
    _, mina_again = rooms.join(1, 10, 3)
    assert (mina.color, jo.color, mina_again.color) == (0, 1, 0)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/pytest tests/test_presence_room.py -q`
Expected: `ModuleNotFoundError: No module named 'app.live.presence'`

- [ ] **Step 3: `app/live/presence.py` 구현**

`changes.py`처럼 웹 프레임워크를 모르게 쓰고, 이벤트 루프 안에서만 쓰이므로 잠금을 두지 않는다. `Outbox`는 deque에 메시지나 "이 사람의 커서" 자리표를 넣고, 사람별 최신 커서를 따로 둔다. `id`는 `secrets.token_hex(4)`. 프레임은 `json.loads(raw, parse_constant=...)`로 NaN을 거절한다. 빈 방은 `join`과 `leave` 때 지난 것을 지운다.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/pytest tests/test_presence_room.py -q`
Expected: all passed

- [ ] **Step 5: 커밋**

`git commit -m "feat: rooms of who is in a session, held in memory"`

---

### Task 2: 웹소켓 라우트와 프록시

**Files:**
- Create: `backend/app/api/presence.py`
- Modify: `backend/app/api/events.py`(`allowed`를 `may_open`으로 추출), `backend/app/main.py`, `frontend/nginx.conf`, `frontend/vite.config.ts`
- Test: `backend/tests/test_presence_route.py`

**Interfaces:**
- Consumes: Task 1의 `Rooms`, `color_order`
- Produces: `app.state.presence: Rooms`, `may_open(db, token, session_id) -> bool`, `WS /api/sessions/{id}/presence`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
HOME = {"origin": "http://testserver"}

def world(tmp_path):
    db = Database(tmp_path / "s.db")
    client = TestClient(create_app(db, Services(FakeGenerator()), InlineExecutor()))
    maker = add_user(db, "maker@example.com")
    return db, client, maker, db.sessions.create(sample_draft(), [], created_by=maker.id)

def closed_with(socket) -> int:
    with pytest.raises(WebSocketDisconnect) as e:
        socket.receive_json()
    return e.value.code

def test_no_login_is_closed_with_4401(tmp_path):
    _, client, _, s = world(tmp_path)
    with client.websocket_connect(f"/api/sessions/{s.id}/presence", headers=HOME) as ws:
        assert closed_with(ws) == 4401

def test_no_access_and_no_session_look_the_same(tmp_path):
    db, client, _, s = world(tmp_path)
    sign_in(client, db, add_user(db, "stranger@example.com"))
    for url in (f"/api/sessions/{s.id}/presence", "/api/sessions/999/presence"):
        with client.websocket_connect(url, headers=HOME) as ws:
            assert closed_with(ws) == 4404

def test_another_origin_is_refused_before_anything_else(tmp_path):
    db, client, maker, s = world(tmp_path)
    sign_in(client, db, maker)
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/api/sessions/{s.id}/presence", headers={"origin": "https://evil.example"}):
            pass
    assert e.value.code == 4403

def test_no_origin_only_needs_the_login(tmp_path): ...  # welcome을 받는다

def test_welcome_gives_the_makers_color_and_no_message_names_an_account(tmp_path):
    db, client, maker, s = world(tmp_path)
    sign_in(client, db, maker)
    with client.websocket_connect(f"/api/sessions/{s.id}/presence", headers=HOME) as ws:
        welcome = ws.receive_json()
    assert welcome["type"] == "welcome" and welcome["you"]["color"] == 0
    assert "maker@example.com" not in json.dumps(welcome) and "user_id" not in json.dumps(welcome)

def test_two_people_hear_each_other_and_a_departure(tmp_path): ...
    # 두 번째 TestClient로 공유받은 사람 접속. 색은 1. cursor가 상대에게 도착.
    # view는 양쪽 모두에게 도착. 한쪽 소켓을 닫으면 상대가 {"type": "left", ...}를 받는다.

def test_ending_the_share_closes_the_socket_with_4404(tmp_path):
    db, client, maker, s = world(tmp_path)
    friend = add_user(db, "friend@example.com")
    db.shares.share(s.id, friend.id)
    sign_in(client, db, friend)
    with client.websocket_connect(f"/api/sessions/{s.id}/presence", headers=HOME) as ws:
        ws.receive_json()
        db.shares.unshare(s.id, friend.id)
        assert closed_with(ws) == 4404

def test_a_login_gone_stale_closes_at_the_next_check(tmp_path, monkeypatch):
    monkeypatch.setattr(presence, "RECHECK_S", 0.05)
    # 접속 후 db.accounts.end_login(token), closed_with(ws) == 4404
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/pytest tests/test_presence_route.py -q`
Expected: 라우트가 없어 `WebSocketDisconnect`, 4401 불일치로 FAIL

- [ ] **Step 3: `app/api/events.py`에서 `may_open(db, token, session_id) -> bool` 추출**

`session_events`의 지역 함수 `allowed`를 이것으로 바꾼다. 기존 `tests/test_changes.py`가 그대로 통과해야 한다.

- [ ] **Step 4: `presence(websocket: WebSocket, session_id: int)` 구현**

`router = APIRouter(prefix="/api")`, `RECHECK_S = 25.0`. 순서: Origin이 있고 그 `netloc`이 `Host`와 다르면 accept 없이 `close(4403)` → `accept` → 쿠키 `LOGIN_COOKIE`로 `user_of_login`, 없으면 `close(4401)` → `can_access`, 아니면 `close(4404)` → `db.changes.subscribe(session_id)` → 색 계산 후 `rooms.join` → welcome 전송 → 세 태스크를 `asyncio.wait(FIRST_COMPLETED)`로 돌린다: outbox를 비워 보내기(`overflowed`면 `close(1013)`), 받은 텍스트를 `room.handle`로 넘기기, `subscription.next(RECHECK_S)`마다 `may_open` 확인해 아니면 `close(4404)`. `finally`에서 나머지 태스크 취소, `rooms.leave`, `subscription.close()`. DB 호출은 `run_in_threadpool`. 데이터베이스는 `websocket.app.state.db`로 읽는다(`Db`는 `Request`를 받으므로 쓸 수 없다). `signed_in`이 묶인 `ROUTERS`에 넣지 말고 `create_app`에서 `app.state.presence = Rooms()`, `app.include_router(presence.router)`로 등록한다.

- [ ] **Step 5: 통과 확인**

Run: `cd backend && .venv/bin/pytest tests/test_presence_route.py tests/test_changes.py -q`
Expected: all passed

- [ ] **Step 6: 프록시 수정**

`frontend/nginx.conf`의 `location /api/` 앞에 더한다.

```nginx
    # Presence: a WebSocket, and the Host it carries is what its Origin is checked against.
    location ~ ^/api/sessions/[0-9]+/presence$ {
        proxy_pass http://backend:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 1h;
    }
```

`frontend/vite.config.ts`의 프록시를 `{ '/api': { target: process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8765', ws: true } }`로 바꾼다.

- [ ] **Step 7: 커밋**

`git commit -m "feat: a WebSocket for who is in a session"`

---

### Task 3: 브라우저 연결과 스토어

**Files:**
- Create: `frontend/src/lib/presence/store.ts`, `connection.ts`, `PresenceProvider.tsx`, `useSharedView.ts`, `frontend/src/test/fakeWebSocket.ts`
- Modify: `frontend/package.json`, `package-lock.json`, `frontend/src/test-setup.ts`
- Test: `frontend/src/lib/presence/store.test.ts`, `presence.test.tsx`

**Interfaces:**
- Consumes: 메시지 계약
- Produces:
  - `PresenceStore`: `attach(send: ((m: object) => void) | null)`, `receive(message)`, `subscribe(listener) -> () => void`, `onCursor(listener: (id: string, at: CursorAt | null) => void) -> () => void`, `viewValue(key)`, `setView(key, value)`, `people(): Person[]`(바뀌기 전까지 같은 배열), `myTab(): number | null`, `setTab(tab)`, `sendCursor(tab, at: {anchor, x, y} | null)`, `timer(): TimerValue | null`, `setTimer(running, elapsed)`, `cursorOf(id)`
  - `Person = { id: string; color: number; tab: number | null }`, `CursorAt = { tab: number; anchor: string; x: number; y: number }`, `TimerValue = { running: boolean; elapsed: number; at: number }`(`at`은 받은 시각의 `Date.now()`)
  - `connectPresence(sessionId: number, store: PresenceStore): () => void`
  - `PresenceProvider({ sessionId, children })`, `usePresenceStore(): PresenceStore | null`
  - `useSharedView<T>(key: string, initial: T): [T, (value: T) => void]`

- [ ] **Step 1: `npm install partysocket@^1.3.0` (frontend에서), 그리고 `src/test/fakeWebSocket.ts` 작성**

`FakeEventSource`와 같은 모양이다. `static instances`, `static open`, 생성자 `(url, protocols, options)`, `sent`(파싱된 메시지 배열), `addEventListener`, `close()`, 시험용 `connect()`, `receive(message)`, `drop(code = 1006)`. `drop`은 그 코드로 `close` 이벤트를 내고, `close()`가 불리지 않으면 재시도 중인 것으로 `open`에 남는다. `test-setup.ts`에 `vi.mock('partysocket', async () => ({ WebSocket: (await import('./test/fakeWebSocket')).FakeWebSocket }))`를 더한다.

- [ ] **Step 2: 실패하는 테스트 작성**

`store.test.ts`:

```ts
const WELCOME = { type: 'welcome', you: { id: 'me', color: 0 }, people: [], view: {}, timer: null }
function joined(id: string) {
  const sent: any[] = []
  const store = new PresenceStore()
  store.attach((m) => sent.push(m))
  store.receive({ ...WELCOME, you: { id, color: 0 } })
  return { store, sent }
}

test.each([[['a', 'b'], false], [['b', 'a'], true]])('pressing the same chip together ends the same on both screens: server order %j', (order, final) => {
  const a = joined('a'), b = joined('b')
  a.store.setView('chip', true)
  b.store.setView('chip', false)
  const fromServer = { a: { type: 'view', key: 'chip', value: true, by: 'a', seq: a.sent[0].seq }, b: { type: 'view', key: 'chip', value: false, by: 'b', seq: b.sent[0].seq } }
  for (const who of order as ('a' | 'b')[]) { a.store.receive(fromServer[who]); b.store.receive(fromServer[who]) }
  expect(a.store.viewValue('chip')).toBe(final)
  expect(b.store.viewValue('chip')).toBe(final)
})

test('a value from someone else does not flicker over mine while mine is on its way', () => {
  const a = joined('a')
  a.store.setView('chip', true)
  a.store.receive({ type: 'view', key: 'chip', value: false, by: 'b', seq: 1 })
  expect(a.store.viewValue('chip')).toBe(true)
})

test('a received value is not sent back', () => {
  const a = joined('a')
  a.store.receive({ type: 'view', key: 'chip', value: true, by: 'b', seq: 1 })
  expect(a.sent).toEqual([])
})

test('a cursor tells cursor listeners and never React listeners', () => {
  const { store } = joined('a')
  const react = vi.fn(), cursors = vi.fn()
  store.subscribe(react); store.onCursor(cursors)
  store.receive({ type: 'cursor', id: 'b', tab: 0, anchor: 'brief', x: 0.5, y: 0.5 })
  expect(cursors).toHaveBeenCalledWith('b', { tab: 0, anchor: 'brief', x: 0.5, y: 0.5 })
  expect(react).not.toHaveBeenCalled()
})

test('a welcome after a reconnect replaces everyone and forgets their cursors', () => {
  const { store } = joined('a')
  store.receive({ type: 'joined', id: 'b', color: 1, tab: 2 })
  store.receive({ type: 'cursor', id: 'b', tab: 2, anchor: 'brief', x: 0, y: 0 })
  const gone = vi.fn(); store.onCursor(gone)
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 } })
  expect(store.people()).toEqual([])
  expect(gone).toHaveBeenCalledWith('b', null)
})

test('a welcome says the tab again', () => {
  const { store, sent } = joined('a')
  store.setTab(2)
  sent.length = 0
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 } })
  expect(sent).toEqual([{ type: 'tab', tab: 2 }])
})

test('a restarted server gets a running timer back, but not an untouched one', () => {
  const { store, sent } = joined('a')
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 } })
  expect(sent).toEqual([])
  store.setTimer(true, 60)
  sent.length = 0
  store.receive({ ...WELCOME, you: { id: 'a3', color: 0 } })
  expect(sent[0]).toMatchObject({ type: 'timer', running: true, elapsed: 60 })
})
```

`presence.test.tsx`:

```tsx
test('connects once to the session with no buffer, and closes on leaving', () => {
  const { unmount } = render(<PresenceProvider sessionId={7}><p /></PresenceProvider>)
  expect(FakeWebSocket.open.map((s) => s.url)).toEqual(['ws://localhost:3000/api/sessions/7/presence'])
  expect(FakeWebSocket.open[0].options.maxEnqueuedMessages).toBe(0)
  unmount()
  expect(FakeWebSocket.open).toHaveLength(0)
})

test.each([4401, 4403, 4404])('closed with %i it stops trying', (code) => {
  render(<PresenceProvider sessionId={7}><p /></PresenceProvider>)
  act(() => FakeWebSocket.open[0].drop(code))
  expect(FakeWebSocket.open).toHaveLength(0)
})

test('useSharedView is plain local state without a provider', ...)    // 누르면 바뀌고 소켓이 없다
test('useSharedView shows what arrives and sends what I set', ...)    // receive view → 표시, 클릭 → sent에 view
test('a set while the socket is down stays on my screen and sends nothing', ...)
```

- [ ] **Step 3: 실패 확인**

Run: `cd frontend && node_modules/.bin/vitest run src/lib/presence`
Expected: FAIL, 모듈 없음

- [ ] **Step 4: `store.ts`, `connection.ts`, `PresenceProvider.tsx`, `useSharedView.ts` 구현**

스토어의 보류 규칙: `setView`는 `seq`를 올려 보내고 `pending[key] = seq`를 적는다. `by`가 나이고 `seq`가 `pending[key]`와 같으면 지우고 값을 적용한다. `pending[key]`가 있는 동안 받은 다른 값은 버린다. `welcome`은 보류를 모두 비우고 view를 통째로 바꾼다. 타이머도 키 하나로 같은 규칙을 쓴다. `welcome`의 `timer`가 `null`인데 내 타이머의 경과가 0보다 크면 내 값을 보낸다. `useSharedView`는 `useSyncExternalStore`로 그 키의 값만 본다. `connection.ts`는 열려 있을 때만 보내고, `4401`, `4403`, `4404`로 닫히면 `socket.close()`로 재시도를 끝낸다. URL 스킴은 `location.protocol`을 따른다.

- [ ] **Step 5: 통과 확인**

Run: `cd frontend && node_modules/.bin/vitest run src/lib/presence && node_modules/.bin/tsc -b`
Expected: all passed, 타입 오류 없음

- [ ] **Step 6: 커밋**

`git commit -m "feat: the browser's end of who is in a session"`

---

### Task 4: 화면 요소 맞추기

**Files:**
- Modify: `frontend/src/pages/SessionPage.tsx`(`OpenSession`을 `<PresenceProvider key={id} sessionId={Number(id)}>`로 감싼다), `components/KoreanChip.tsx`, `ExpressionsTab.tsx`, `VocabularyTab.tsx`, `Sentence.tsx`, `Paragraph.tsx`, `ArticleTab.tsx`
- Test: `components/ExpressionsTab.test.tsx`, `VocabularyTab.test.tsx`, `ArticleTab.test.tsx`

**Interfaces:**
- Consumes: `PresenceProvider`, `useSharedView`, `FakeWebSocket`
- Produces: `KoreanChip`의 필수 prop `viewKey: string`, `Sentence`의 필수 prop `viewKey: string`

키는 스펙의 표를 그대로 쓴다: `chip:expression:{id}`, `chip:word:{id}`, `example:{표현 id}`, `reveal:{단어 id}`, `face:{단어 id}`, `caption:{단어 id}`, `sentence:{문단 id}:{piece.start}`, `question`.

- [ ] **Step 1: 실패하는 테스트 작성**

각 테스트 파일에 공통 도우미를 두고, 기존 픽스처를 `<PresenceProvider sessionId={3}>`로 감싸 렌더링한 뒤 `const socket = FakeWebSocket.open[0]; act(() => { socket.connect(); socket.receive(WELCOME) })`로 시작한다.

```tsx
it('turns over the chip someone else turned over, and tells them when I do', ...)
  // receive({ type: 'view', key: 'chip:expression:1', value: true, by: 'b', seq: 1 }) → 한국어 표시
  // 클릭 → socket.sent에 { type: 'view', key: 'chip:expression:1', value: false }가 포함(toMatchObject)
it('flips the Korean card with them', ...)              // key 'example:1', 영어 답 표시
it('reveals the definition with them', ...)             // key 'reveal:2'
it('shows the picture face they flipped to', ...)       // key 'face:2', value 'practice'
it('opens the scene caption with them, and flipping the picture closes it for both', ...)
  // key 'caption:2' true → 표시. 그림 뒤집기 클릭 → sent에 caption:2 false와 face:2 둘 다
it('a redraw closes the scene caption for both', ...)   // ↻ 클릭 → sent에 caption:2 false
it('flips a sentence the same way a click does', ...)
  // receive key 'sentence:1:0' value 'ko' → span.is-sinking → fireEvent.animationEnd → 한국어, is-rising
  // 애니메이션 끝난 뒤 값 'en'이 오면 다시 is-sinking. 애니메이션 도중 온 값은 끝난 뒤 맞춘다
it('marks the passage of the question they picked, without scrolling me', ...)
  // scrollIntoView = vi.fn(). receive key 'question' value 0 → mark 표시, scrollIntoView 호출 안 됨
it('scrolls only the person who clicked the question', ...) // 클릭 → scrollIntoView 호출, sent에 question 0
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && node_modules/.bin/vitest run src/components/ExpressionsTab.test.tsx src/components/VocabularyTab.test.tsx src/components/ArticleTab.test.tsx`
Expected: 새 테스트 FAIL

- [ ] **Step 3: 구현**

표의 `useState`를 `useSharedView`로 바꾼다. 다음은 대체만으로 안 되는 곳이다.
- `Sentence`: 공유 값은 목표 언어다. 화면 `lang`은 지역 상태로 두고 처음 값은 목표에서 가져온다. `phase`가 `still`이고 목표와 `lang`이 다르면 `sinking`을 시작한다. `sinking`이 끝나면 `lang`을 목표로 맞춘다. 클릭은 `still`일 때만 목표를 뒤집는다.
- `ArticleTab`: 클릭 핸들러가 `ref`에 스크롤 예약을 적고, `active` 효과는 예약이 있을 때만 `scrollIntoView`한다.
- `VocabCell`: `caption` 공유 값을 여기로 올려 `VocabPicture`를 거쳐 `SceneCaption`에 `shown`, `onShownChange`로 내려준다. `onFlip`과 `onRedraw`에서 `false`로 쓴다. `key={image}`는 없앤다.

- [ ] **Step 4: 전체 확인**

Run: `cd frontend && node_modules/.bin/vitest run && node_modules/.bin/tsc -b`
Expected: 모두 통과. 프로바이더 없이 렌더링하는 기존 테스트도 그대로 통과

- [ ] **Step 5: 커밋**

`git commit -m "feat: what one person turns over turns over for everyone"`

---

### Task 5: 공유 타이머

**Files:**
- Create: `frontend/src/lib/presence/useSharedTimer.ts`
- Modify: `frontend/src/components/SessionTimer.tsx`
- Test: `frontend/src/components/SessionTimer.test.tsx`

**Interfaces:**
- Consumes: `usePresenceStore`, `PresenceStore.timer`, `setTimer`
- Produces: `useSharedTimer(): { elapsed: number; running: boolean; start(): void; pause(): void; reset(): void }`. `elapsed`는 `SESSION_SECONDS`로 잘린 정수 초다.

- [ ] **Step 1: 실패하는 테스트 작성**

```tsx
it('falls behind nothing when a hidden tab slows its interval', () => {
  render(<SessionTimer />)
  fireEvent.click(screen.getByRole('button', { name: /start/i }))
  vi.setSystemTime(Date.now() + 600_000)   // 인터벌 없이 시간만 흐른다
  act(() => vi.advanceTimersByTime(1000))
  expect(screen.getByText('19:59')).toBeInTheDocument()
})
it('runs from what arrives, counting on by itself', ...)
  // 프로바이더 안에서 receive({ type: 'timer', running: true, elapsed: 65, by: 'b', seq: 1 }) → '28:55', 1초 뒤 '28:54'
it('shows the same time to someone who comes late', ...)  // welcome.timer { running: true, elapsed: 600 } → '20:00'
it('sends start, pause and reset', ...)
  // 각 클릭 뒤 sent 마지막이 { type: 'timer', running: true, elapsed: 0 }, { running: false, elapsed: n }, { running: false, elapsed: 0 }
it('stops at thirty minutes whatever arrives', ...)       // elapsed 99999 → 'Time. Well done.'
it('keeps time alone with the socket down', ...)          // 프로바이더 있고 connect 안 함, Start 후 1초 → '29:59'
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && node_modules/.bin/vitest run src/components/SessionTimer.test.tsx`
Expected: 새 테스트 FAIL

- [ ] **Step 3: `useSharedTimer` 구현, `SessionTimer`가 쓰도록 변경**

경과는 항상 `base + (Date.now() - at) / 1000`에서 계산한다. 인터벌은 다시 그리기만 맡는다. 프로바이더가 없으면 같은 모양의 값을 지역 상태로 둔다.

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && node_modules/.bin/vitest run src/components/SessionTimer.test.tsx src/pages/SessionPage.test.tsx`
Expected: all passed

- [ ] **Step 5: 커밋**

`git commit -m "feat: one timer for everyone in a session"`

---

### Task 6: 탭 표시와 색

**Files:**
- Create: `frontend/src/lib/presence/useOthersOnTab.ts`, `frontend/src/components/TabPeople.tsx`, `TabPeople.css`
- Modify: `frontend/src/styles/base.css`, `frontend/src/pages/SessionPage.tsx`, `frontend/src/lib/presence/store.ts`
- Test: `frontend/src/pages/SessionPage.test.tsx`

**Interfaces:**
- Consumes: `PresenceStore.people`, `setTab`
- Produces: `useOthersOnTab(tab: number): number[]`(겹치지 않는 색 번호), `<TabPeople tab={n} />`, CSS 토큰 `--person-1`부터 `--person-6`, `personColor(color: number): string`(`var(--person-${color % 6 + 1})`, `lib/presence/store.ts`)

- [ ] **Step 1: 실패하는 테스트 작성**

```tsx
it('says which tab the other person is on, in their color', async () => {
  renderAt('/s/3')
  await screen.findByText('a moving target')
  const socket = FakeWebSocket.open[0]
  act(() => { socket.connect(); socket.receive({ type: 'welcome', you: { id: 'me', color: 0 }, people: [{ id: 'b', color: 1, tab: 2 }], view: {}, timer: null }) })
  const vocabulary = screen.getByRole('button', { name: /Vocabulary/ })
  expect(within(vocabulary).getByRole('img', { name: 'Someone else is here' }).getAttribute('style')).toContain('--person-2')
  expect(within(screen.getByRole('button', { name: /Article/ })).queryByRole('img')).toBeNull()
})
it('moves the mark when they move, and takes it away when they leave', ...)  // tab, left 메시지
it('tells the others which tab I am on, and again after reconnecting', ...)  // sent에 { type: 'tab', tab: 0 }, 탭 클릭 뒤 { type: 'tab', tab: 1 }
it('shows one mark for one person on two connections', ...)                  // 같은 색 두 연결 → 점 하나
it('marks the Summary tab too', ...)                                          // tab: 3
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && node_modules/.bin/vitest run src/pages/SessionPage.test.tsx`
Expected: 새 테스트 FAIL

- [ ] **Step 3: 구현**

`base.css`에 토큰 여섯 개를 더한다. `--marker`, `--error`, `--right`, `--phrase`와 헷갈리지 않고 `--paper` 위 대비 3:1 이상이어야 한다. `OpenSession`이 `tab`이 바뀔 때 `store.setTab(tab)`을 부른다. `.tab`은 3칸 격자이므로 점이 격자를 깨지 않게 둔다(예: `.tab`에 `position: relative`).

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && node_modules/.bin/vitest run src/pages/SessionPage.test.tsx`
Expected: all passed

- [ ] **Step 5: 커밋**

`git commit -m "feat: a mark on the tab someone else is on, in their color"`

---

### Task 7: 커서

**Files:**
- Create: `frontend/src/lib/presence/anchors.ts`, `useCursorSender.ts`, `frontend/src/components/Cursors.tsx`, `Cursors.css`
- Modify: 기준 요소에 `data-presence-anchor` 추가: `ExpressionsTab.tsx`(`expression:{id}`), `VocabularyTab.tsx`(`word:{id}`), `Paragraph.tsx`(`paragraph:{id}`), `ArticleTab.tsx`(토론 질문 `question:{i}`), 각 탭의 `.tab-brief`(`brief`), `SessionTimer.tsx`(`timer`), `SharePanel.tsx`(`shares`), `SessionPage.tsx`(`tabs`, `rail`, `content`, `<Cursors />` 추가, `useCursorSender(tab)`)
- Test: `frontend/src/lib/presence/anchors.test.ts`, `frontend/src/components/Cursors.test.tsx`

**Interfaces:**
- Consumes: `PresenceStore.onCursor`, `sendCursor`, `people`, `myTab`, `personColor`
- Produces: `anchorAt(clientX, clientY): { anchor: string; x: number; y: number } | null`, `pointFor(anchor: string, x: number, y: number): { left: number; top: number } | null`

- [ ] **Step 1: 실패하는 테스트 작성**

jsdom에는 레이아웃이 없으므로 `getBoundingClientRect`와 `document.elementFromPoint`를 스텁한다.

```ts
test('turns a point into the nearest anchor and its fractions', ...)
  // rect { left: 100, top: 200, width: 400, height: 100 }, (300, 250) → { anchor: 'word:2', x: 0.5, y: 0.5 }
test('nothing under the mouse carries an anchor: no cursor', ...)   // null
test('turns fractions back into a point', ...)                      // { left: 300, top: 250 }
test.each(['없는 요소', '크기 0 요소'])('%s has no point', ...)      // null, NaN 아님
```

```tsx
it('draws the cursor of someone on my tab in their color, where their anchor is on my screen', ...)
it('draws nothing for someone on another tab', ...)
it('draws nothing when the anchor is not on my screen, and takes away one that was drawn', ...)
it('marks a cursor off the top or bottom of my screen, and keeps it in view', ...)   // is-above, is-below
it('removes the cursor when they send none and when they leave', ...)
it('follows the anchor when I scroll', ...)    // 스크롤 이벤트 후 rect 변경 반영
it('does not re-render React for a cursor', ...)  // <Profiler onRender={spy}> 안에서 cursor 메시지 100개 → spy 추가 호출 없음
it('lets clicks through', ...)                 // 레이어에 aria-hidden, CSS pointer-events는 e2e에서 확인
it('sends a mouse at most 20 times a second, and not a touch', ...)
  // pointerType 'mouse' pointermove 100번을 1초에 → sent의 cursor 21개 이하. pointerType 'touch'는 0개
it('says there is no cursor when the mouse leaves or the page hides', ...)  // anchor: null
it('sends again when scrolling moves another element under a still mouse', ...)
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && node_modules/.bin/vitest run src/lib/presence/anchors.test.ts src/components/Cursors.test.tsx`
Expected: FAIL, 모듈 없음

- [ ] **Step 3: `anchors.ts`, `useCursorSender.ts`, `Cursors.tsx` 구현, 기준 요소 표시**

`Cursors`는 레이어 `div` 하나만 React로 그리고, 커서는 `store.onCursor`에서 DOM으로 직접 만들고 `transform`을 고친다. 스크롤(캡처), `resize`, `ResizeObserver`(내용 높이 변화. jsdom에 없으면 건너뜀), 내 탭 변경에 모두 다시 놓는다. 레이어는 `position: fixed; inset: 0; pointer-events: none; z-index: 19`, `aria-hidden`. 보간은 CSS `transition: transform 90ms linear`로 하고 `prefers-reduced-motion`이면 끈다. 전송은 `pointermove`에서 `pointerType === 'mouse'`만, 50ms로 줄인다.

- [ ] **Step 4: 전체 확인**

Run: `cd frontend && node_modules/.bin/vitest run && node_modules/.bin/tsc -b && node_modules/.bin/oxlint src/lib/presence src/components/Cursors.tsx`
Expected: 테스트와 타입 통과, 새 파일에 경고 없음

- [ ] **Step 5: 커밋**

`git commit -m "feat: see where the others are pointing"`

---

### Task 8: 규칙 문서, 실제 검증, 배포

**Files:**
- Modify: `CLAUDE.md`, `AGENTS.md`, `docs/superpowers/specs/2026-10-30-accounts-and-sharing-design.md`("통신의 경계" 표와 규칙)
- Create (저장소 밖, 스크래치패드): Playwright 검증 스크립트, compose 덮어쓰기 파일

- [ ] **Step 1: 규칙 문서 수정**

`CLAUDE.md`, `AGENTS.md`의 Client-server communication 절에 더한다.

```markdown
- Presence is the one exception to REST: `WS /api/sessions/{id}/presence` carries who is here, cursors, tabs, what they have turned over, and the shared timer. None of it is saved; losing it costs no more than a reload. Whatever must survive stays REST plus an event.
- In the browser, only `frontend/src/lib/presence/connection.ts` opens that socket.
```

설계 문서의 통신 표에 같은 내용의 줄을 더한다.

- [ ] **Step 2: 전체 테스트**

Run: `cd backend && .venv/bin/pytest -q` 그리고 `cd frontend && node_modules/.bin/vitest run && node_modules/.bin/tsc -b`
Expected: 모두 통과

- [ ] **Step 3: 운영 데이터와 분리된 스택 띄우기**

`COMPOSE_PROJECT_NAME=tme-e2e FRONTEND_PORT=5199`, 덮어쓰기 파일로 `/data`를 스크래치패드의 DB와 그림 **복사본**으로 바꾸고 `COOKIE_SECURE=false`, `ADMIN_PASSWORD=""`로 띄운다. `docker compose config`로 `/data` 원본이 운영 경로가 아닌지 먼저 확인한다. 실제 nginx를 지나는 검증이다.

- [ ] **Step 4: 브라우저 두 개로 검증**

창 크기가 다른 두 계정(1280px, 900px)으로 확인한다.
1. 커서가 같은 요소를 가리키고, 지연이 눈에 띄지 않으며, 커서 위 클릭이 그 아래 요소에 닿는다.
2. 탭 점이 맞고, 다른 탭의 커서는 보이지 않는다.
3. 표의 화면 요소 여덟 줄이 모두 양쪽에서 맞는다. 같은 칩을 동시에 눌러도 같은 값으로 끝난다.
4. 타이머 시작, 일시정지, 초기화가 맞고, 늦게 들어온 사람도 같은 시간을 본다. 10분을 넘어도 탭이 그대로다.
5. 마이크 권한을 기록하도록 `getUserMedia`를 감싸고, 상대가 Read aloud와 Speak를 눌러도 내 쪽 호출과 재생이 0번이다.
6. 백엔드를 멈춰도 칩과 타이머가 혼자 동작하고, 다시 켜면 재연결되며 돌던 타이머가 이어진다.
7. 공유를 끊으면 상대 화면이 닫히고 재연결을 시도하지 않는다.
8. 390px에서 옆 넘침이 0이다.

- [ ] **Step 5: 검증 스택과 복사본 삭제**

Run: `docker compose down --rmi local`(같은 환경 변수로), 복사본 디렉터리 삭제
Expected: `docker ps`에 `tme-e2e`가 없다

- [ ] **Step 6: 커밋, 병합, 배포**

`detect_changes` 후 커밋하고, `main`에 fast-forward 병합, `scripts/bump-version patch`, `docker compose up -d --build`. 배포 전에 로그로 돌고 있는 생성 작업이 없는지 확인한다.

- [ ] **Step 7: 공개 주소 확인**

`backend/.venv/bin/python`의 `websockets`로 `.env`의 운영자 계정(값은 출력하지 않는다)으로 로그인한 쿠키를 들고 `wss://english.daily-cotidie.com/api/sessions/{내 세션}/presence`에 `Origin: https://english.daily-cotidie.com`으로 접속한다.
Expected: `welcome` 수신, `{"type": "tab", "tab": 0}` 전송 후 끊기지 않음, 다른 Origin은 거절. 끝나면 로그아웃한다.

연결이 안 되면 Cloudflare의 WebSockets 설정을 사용자에게 알리고, 세션이 지금처럼 동작하는지 확인한 뒤 멈춘다.

- [ ] **Step 8: push**

Run: `git push --follow-tags`
Expected: `main`과 태그가 올라간다
