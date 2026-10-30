# 계정, 세션 공유, 실시간 반영 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인한 계정만 세션을 만들고, 세션을 지정한 사람에게만 공유하며, 공유자의 변경이 실시간으로 보이게 한다.

**Architecture:** 쿠키 로그인과 라우터 단위 기본 거부로 API를 닫고, 세션 접근 판단을 `ShareRepo` 한 곳에 둔다. 상태는 REST로만 읽고 쓰며, 이벤트 스트림은 "다시 읽을 자원 이름"만 보낸다. 이벤트 발행은 저장소에서만, 구독은 `useSessionResource`에서만 한다.

**Tech Stack:** FastAPI, SQLite (STRICT), 표준 라이브러리 `hashlib.scrypt`와 `secrets`, Server-Sent Events, React, react-router-dom, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-accounts-and-sharing-design.md`. 구현 전에 "통신의 경계"와 "권한" 절을 읽는다.

## Global Constraints

- 새 의존성을 추가하지 않는다. 새 셸 스크립트를 만들지 않는다.
- 비밀번호: 8자 이상 1024자 이하. scrypt n=2^15, r=8, p=1.
- 쿠키: 이름 `login`, `HttpOnly`, `SameSite=Lax`, `Path=/`, 30일. `Secure`는 `COOKIE_SECURE` 환경변수를 따르고 기본은 켜짐.
- 제한: 이메일별 15분에 로그인 실패 10회, 전체 시간당 가입 20건을 넘으면 429.
- 응답: 비로그인 401, 역할 부족 403, 없는 세션과 접근권 없는 세션은 똑같이 404.
- 이벤트 이름: `session`, `stars`, `note`, `records`, `gone`. 내부 신호 `access`는 브라우저로 나가지 않는다.
- 이벤트에는 데이터를 싣지 않는다. 이벤트 발행은 저장소에서만, 구독은 `useSessionResource`에서만 한다.
- UI 문구는 영어이고 스펙의 문구를 그대로 쓴다.
- 편집 전 `node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .`, 커밋 전 `node .gitnexus/run.cjs detect-changes --scope all --repo .`를 실행하고 HIGH 이상이면 보고한다.
- 커밋 메시지에 `Co-Authored-By`를 넣지 않는다. push하지 않는다.
- 주석은 주변 코드의 밀도와 말투를 따른다. 함수 하나의 추상화 수준을 맞춘다.

## Review Focus

1. 가입과 로그인의 이메일이 `Mina@Example.COM ` 처럼 대소문자나 공백만 다르면 같은 계정으로 처리해야 한다. Task 1, 2에 테스트.
2. 별표를 빠르게 두 번 누르는 사이에 다시 읽기 결과가 도착해도 별표가 되돌아가면 안 된다. Task 11에 테스트.
3. `next=//evil.example`이나 `next=https://evil.example`로 로그인하면 외부로 나가지 않고 `/`로 가야 한다. Task 9에 테스트.
4. 저장하지 않은 노트를 입력하는 중에 상대가 노트를 저장해도 내 입력이 지워지면 안 되고, 상대가 세션을 지우면 화면이 "This session is no longer available."로 바뀌어야 한다. Task 11에 테스트.
5. 스트림이 열린 채로 로그인이 만료되면 다음 하트비트에 `gone`을 보내고 닫혀야 한다. Task 8에 테스트.

---

### Task 1: 스키마 v10, 비밀번호, 계정 저장소

**Files:**
- Create: `backend/app/accounts/__init__.py`, `backend/app/accounts/passwords.py`, `backend/app/db/accounts.py`, `backend/app/db/shares.py`
- Modify: `backend/app/db/schema.py`, `backend/app/db/__init__.py`, `backend/app/models.py`, `backend/app/db/sessions.py`
- Test: `backend/tests/test_accounts.py`, `backend/tests/test_schema.py`

**Interfaces:**
- Produces:
  - `models.User(id: int, created_at: datetime, email: str, is_admin: bool, can_create: bool)`
  - `passwords.hash_password(password: str) -> str`, `passwords.verify_password(password: str, stored: str) -> bool`, `passwords.burn_time() -> None`
  - `accounts.normalize_email(email: str) -> str`, `accounts.EmailTaken`
  - `db.accounts`: `create(email, password_hash) -> User`, `with_hash(email) -> tuple[User, str] | None`, `get(user_id) -> User | None`, `by_email(email) -> User | None`, `list_all() -> list[User]`, `set_can_create(user_id, value) -> User | None`, `set_password(user_id, password_hash) -> None`, `start_login(user_id) -> str`, `user_of_login(token) -> User | None`, `end_login(token) -> None`, `ensure_admin(email, password_hash) -> User | None`
  - `db.shares`: `share(session_id, user_id) -> None`, `unshare(session_id, user_id) -> bool`, `shared_with(session_id) -> list[User]`, `created_by(session_id) -> int | None`, `can_access(user, session_id) -> bool`, `has_sessions(user_id) -> bool`, `can_see_picture(user, picture_id) -> bool`
  - `SessionRepo.create(draft, expression_ids, created_by: int | None = None)`
  - `tests.conftest.add_user(db, email="a@example.com", *, admin=False, can_create=False) -> User`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_a_password_is_kept_only_as_a_hash_and_checks_out():
    stored = hash_password("correct horse")
    assert "correct horse" not in stored and stored.startswith("scrypt$")
    assert verify_password("correct horse", stored) and not verify_password("wrong", stored)

def test_an_email_differing_only_in_case_or_spaces_is_the_same_account(store):
    store.accounts.create("  Mina@Example.COM ", "h")
    assert store.accounts.by_email("mina@example.com").email == "mina@example.com"
    with pytest.raises(EmailTaken):
        store.accounts.create("mina@example.com", "h")

def test_a_login_token_is_stored_hashed_and_ends(store):
    user = store.accounts.create("a@example.com", "h")
    token = store.accounts.start_login(user.id)
    assert store.accounts.user_of_login(token).id == user.id
    with store.connect() as conn:
        assert token not in [r[0] for r in conn.execute("SELECT token_hash FROM logins")]
    store.accounts.end_login(token)
    assert store.accounts.user_of_login(token) is None

def test_an_expired_login_is_refused_and_purged_at_the_next_login(store):
    user = store.accounts.create("a@example.com", "h")
    token = store.accounts.start_login(user.id)
    with store.connect() as conn:
        conn.execute("UPDATE logins SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert store.accounts.user_of_login(token) is None
    store.accounts.start_login(user.id)
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM logins").fetchone()[0] == 1

def test_ensure_admin_claims_old_sessions_once_and_then_does_nothing(store):
    old = store.sessions.create(sample_draft(), [])
    admin = store.accounts.ensure_admin("boss@example.com", "h")
    assert admin.is_admin and store.shares.created_by(old.id) == admin.id
    assert store.accounts.ensure_admin("other@example.com", "h") is None

def test_ensure_admin_takes_over_an_account_with_that_email_and_ends_its_logins(store):
    user = store.accounts.create("boss@example.com", "old")
    token = store.accounts.start_login(user.id)
    admin = store.accounts.ensure_admin("boss@example.com", "new")
    assert admin.id == user.id and store.accounts.with_hash("boss@example.com")[1] == "new"
    assert store.accounts.user_of_login(token) is None

def test_access_goes_to_the_creator_the_shared_and_the_admin_only(store):
    me, friend, stranger = (add_user(store, f"{n}@example.com") for n in ("me", "friend", "stranger"))
    admin = add_user(store, "boss@example.com", admin=True)
    session = store.sessions.create(sample_draft(), [], created_by=me.id)
    store.shares.share(session.id, friend.id)
    assert [store.shares.can_access(u, session.id) for u in (me, friend, stranger, admin)] == [True, True, False, True]
    assert not store.shares.can_access(me, 999)
    assert store.shares.has_sessions(me.id) and store.shares.has_sessions(friend.id) and not store.shares.has_sessions(stranger.id)
```

`test_schema.py`에 추가: v9 파일(현재 파일에서 `users`, `logins`, `session_shares`, `created_by`를 지우고 `user_version = 9`로 되돌린 것)을 열면 v10이 되고 세션이 그대로이며 `created_by`가 NULL이다.

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd backend && uv run pytest tests/test_accounts.py tests/test_schema.py -v`
Expected: FAIL, `app.accounts`를 찾을 수 없음.

- [ ] **Step 3: 구현**

`schema.py`: `VERSION = 10`. 스펙의 DDL을 상수 `ACCOUNTS`로 두고, `SESSIONS`의 `CREATE TABLE`에 `created_by INTEGER REFERENCES users(id)`를 더하고, `users` 테이블이 먼저 만들어지게 `SCHEMA` 앞쪽에 `ACCOUNTS`를 둔다. `upgrade`에 `if version < 10:` 단계로 `_run(conn, ACCOUNTS)`, `ALTER TABLE sessions ADD COLUMN created_by ...`, `PRAGMA user_version = 10`을 더한다.

`start_login`은 `secrets.token_urlsafe(32)`를 만들어 SHA-256만 저장하고, 만료 30일, 만료된 행을 지운다. `can_access`는 관리자이면 세션 존재 여부만, 아니면 생성자 또는 공유 대상인지를 본다. `can_see_picture`는 `vocabulary.picture_id`, `vocabulary.example_picture_id`, `figures.picture_id`로 세션을 찾아 그중 하나라도 `can_access`면 참이다. `Database`에 `self.accounts`, `self.shares`를 더한다.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/test_accounts.py tests/test_schema.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/app backend/tests
git commit -m "feat: accounts, logins, and session shares in schema v10"
```

### Task 2: 인증 API와 기본 거부

**Files:**
- Create: `backend/app/accounts/limits.py`, `backend/app/api/auth.py`
- Modify: `backend/app/api/deps.py`, `backend/app/api/__init__.py`, `backend/app/api/settings.py`, `backend/app/api/corpus.py`, `backend/app/api/topics.py`, `backend/app/api/coaches.py`, `backend/app/main.py`, `backend/tests/conftest.py`, 라우트를 호출하는 테스트 파일 전부(`test_swaps`, `test_speech`, `test_daily_topics`, `test_assessor`, `test_api`, `test_settings`, `test_catalog`, `test_example_feedback`, `test_summary_feedback`, `test_live`, `test_topic_rows`, `test_expressions`)
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: Task 1의 `db.accounts`, `passwords`.
- Produces:
  - `deps.LOGIN_COOKIE = "login"`, `deps.signed_in(request) -> User`(401), `deps.Me`, `deps.admin_only(me) -> User`(403), `deps.can_create(me) -> User`(403), `deps.Creator`, `deps.can_practice(me, db) -> User`(403)
  - `limits.FailedLogins(limit=10, window_s=900, clock=time.monotonic)`: `blocked(email) -> bool`, `failed(email)`, `cleared(email)`. `limits.SignupLimit(limit=20, window_s=3600, clock=time.monotonic)`: `allow() -> bool`.
  - 라우트 `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`. 응답 모델 `User`.
  - `tests.conftest.sign_in(client, db, user) -> None`: 토큰을 만들어 쿠키에 넣는다.

- [ ] **Step 1: 실패하는 테스트 작성** (`TestClient(app, base_url="https://testserver")`)

```python
def test_signing_up_logs_you_in_without_rights(client):
    res = client.post("/api/auth/signup", json={"email": " Mina@Example.COM ", "password": "12345678"})
    assert res.status_code == 201 and res.json()["email"] == "mina@example.com"
    assert res.json()["can_create"] is False and res.json()["is_admin"] is False
    cookie = res.headers["set-cookie"].lower()
    assert "login=" in cookie and "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie and "max-age=2592000" in cookie
    assert client.get("/api/auth/me").json()["email"] == "mina@example.com"

@pytest.mark.parametrize("email,password", [("not-an-email", "12345678"), ("a@b", "12345678"), ("a@example.com", "1234567"), ("a@example.com", "x" * 1025)])
def test_a_bad_signup_gets_a_400_with_a_readable_reason(client, email, password):
    res = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert res.status_code == 400 and isinstance(res.json()["detail"], str)

def test_an_email_in_use_gets_a_409(client): ...

def test_a_wrong_password_and_an_unknown_email_answer_alike(client):
    client.post("/api/auth/signup", json={"email": "a@example.com", "password": "12345678"})
    client.cookies.clear()
    wrong = client.post("/api/auth/login", json={"email": "a@example.com", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"email": "b@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
    assert wrong.json()["detail"] == "That email and password don't match. Check them and try again."

def test_the_eleventh_failure_within_15_minutes_gets_a_429_even_with_the_right_password(client): ...
def test_the_21st_signup_in_an_hour_gets_a_429(client): ...
def test_logging_out_ends_the_login_on_the_server(client): ...

def test_every_route_but_signup_and_login_refuses_an_anonymous_call(anonymous_client):
    public = {("POST", "/api/auth/signup"), ("POST", "/api/auth/login")}
    for route in anonymous_client.app.routes:
        for method in getattr(route, "methods", None) or ():
            if method == "HEAD" or not route.path.startswith("/api/") or (method, route.path) in public:
                continue
            path = re.sub(r"\{[^}]+\}", "1", route.path)
            assert anonymous_client.request(method, path).status_code == 401, (method, route.path)
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd backend && uv run pytest tests/test_auth.py -v`
Expected: FAIL, 404 또는 import 오류.

- [ ] **Step 3: 구현**

`create_app`에서 `app.include_router(router, dependencies=[Depends(signed_in)])`로 `ROUTERS`를 등록하고, `auth.public_router`(signup, login)만 그 밖에 등록한다. logout과 me는 `ROUTERS`에 든 `auth.router`에 둔다. 라우터 수준 의존성: `settings.router`와 `corpus.router`에 `admin_only`, `coaches.router`에 `can_practice`. `topics.py`는 경로별로 `GET ""`, `POST /refresh`에 `can_create`, `/all`과 `DELETE`에 `admin_only`. 쿠키의 `secure`는 `app.state.env.get("COOKIE_SECURE", "true") != "false"`. 없는 이메일에도 `burn_time()`을 호출한다. 제한 객체는 `app.state.failed_logins`, `app.state.signups`.

`conftest.py`에 `add_user`와 `sign_in`을 두고, 라우트를 호출하는 테스트 파일마다 `TestClient`를 만든 직후 `sign_in(c, db, add_user(db, "admin@example.com", admin=True))`를 넣는다.

- [ ] **Step 4: 전체 통과 확인**

Run: `cd backend && uv run pytest -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend
git commit -m "feat: sign up, log in, and refuse every other route without a login"
```

### Task 3: 세션 접근 규칙

**Files:**
- Create: `backend/app/api/images.py`
- Modify: `backend/app/api/deps.py`, `backend/app/api/sessions.py`, `backend/app/api/records.py`, `backend/app/api/__init__.py`, `backend/app/db/sessions.py`, `backend/app/generation/jobs.py`, `backend/app/models.py`, `backend/app/main.py`
- Test: `backend/tests/test_session_access.py`, `backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `db.shares`, `deps.Me`, `deps.Creator`.
- Produces:
  - `deps.require_access(db, me, session_id)`(404), `deps.require_creator(db, me, session_id)`(접근권 없으면 404, 있으면 403), `deps.require_paragraph(db, me, paragraph_id)`(404). `require_session`은 지운다.
  - `SessionSummary`와 `Session`에 `mine: bool = True`, `shared_by: str | None = None`.
  - `SessionRepo.list_visible(user_id) -> list[SessionSummary]`(내가 만들었거나 공유받은 세션, 최신순). `SessionRepo.viewpoint(session_id, user_id) -> tuple[bool, str | None]`. `list_all`은 지운다.
  - `JobRunner.start(topic, generator, illustrator=None, created_by: int | None = None)`, `Job.created_by: int | None = None`.
  - `GET /api/images/{name}`. `create_app`의 `StaticFiles` 마운트는 지운다.

- [ ] **Step 1: 실패하는 테스트 작성**

호출자 5종(`anon`, `newcomer`, `sharee`, `creator`, `admin`)을 만드는 픽스처를 두고 표로 검사한다. `creator`는 `can_create=True`로 세션을 만들고 `sharee`에게 공유한다.

```python
SID = "{sid}"
TABLE = [  # method, path, anon, newcomer, sharee, creator, admin
    ("GET", f"/api/sessions/{SID}", 401, 404, 200, 200, 200),
    ("GET", f"/api/sessions/{SID}/stars", 401, 404, 200, 200, 200),
    ("GET", f"/api/sessions/{SID}/note", 401, 404, 200, 200, 200),
    ("GET", f"/api/examples?session_id={SID}", 401, 404, 200, 200, 200),
    ("GET", f"/api/summaries?session_id={SID}", 401, 404, 200, 200, 200),
    ("GET", f"/api/readings?session_id={SID}", 401, 404, 200, 200, 200),
    ("POST", f"/api/sessions/{SID}/expressions", 401, 404, 200, 200, 200),
    ("DELETE", f"/api/sessions/{SID}", 401, 404, 403, 204, 403),
    ("GET", "/api/settings", 401, 403, 403, 403, 200),
    ("GET", "/api/expressions", 401, 403, 403, 403, 200),
    ("GET", "/api/topics/all", 401, 403, 403, 403, 200),
    ("GET", "/api/topics", 401, 403, 403, 200, 200),
    ("GET", "/api/assessor/token", 401, 403, 503, 503, 503),
]

def test_list_shows_only_my_sessions_and_those_shared_with_me(...):
    assert [s["mine"] for s in sharee.get("/api/sessions").json()] == [False]
    assert sharee.get("/api/sessions").json()[0]["shared_by"] == "creator@example.com"
    assert newcomer.get("/api/sessions").json() == [] and admin.get("/api/sessions").json() == []

def test_only_an_approved_account_can_start_a_session(...): ...
def test_jobs_are_seen_and_closed_only_by_who_started_them(...): ...
def test_a_new_try_clears_only_my_own_failed_job(...): ...  # test_jobs.py
def test_an_image_is_served_only_to_who_can_open_its_session(...):
    assert sharee.get(f"/api/images/{pid}.png").status_code == 200
    assert newcomer.get(f"/api/images/{pid}.png").status_code == 404
    assert "private" in sharee.get(f"/api/images/{pid}.png").headers["cache-control"]
    assert sharee.get("/api/images/..%2Fsessions.db").status_code == 404
def test_adding_a_record_on_a_paragraph_of_someone_elses_session_is_a_404(...): ...
def test_an_approval_taken_away_stops_new_spending_but_keeps_my_sessions(...):
    # can_create 끔: POST /api/sessions 403, 그림 다시 그리기 403, 세션 조회 200, assessor 토큰은 can_practice 유지
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd backend && uv run pytest tests/test_session_access.py -v`
Expected: FAIL, 다른 계정이 세션을 읽을 수 있음.

- [ ] **Step 3: 구현**

`sessions.py`와 `records.py`의 모든 라우트에 `me: Me`를 받아 표대로 `require_access` 또는 `require_creator`를 호출한다. `redraw_picture`는 `require_creator`와 `Creator`를 함께 쓴다. `get_session`은 `viewpoint`로 `mine`, `shared_by`를 채운다. `start`의 실패 job 정리는 `j.status != "failed" or j.created_by != created_by`로 좁힌다. `_run`은 `self._sessions.create(draft, ids, job.created_by)`. `images.py`는 이름을 `^\d+\.png$`로 검사한 뒤 `can_see_picture`와 파일 존재를 확인하고 `FileResponse`에 `Cache-Control: private, max-age=86400`을 붙인다.

- [ ] **Step 4: 전체 통과 확인**

Run: `cd backend && uv run pytest -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend
git commit -m "feat: sessions, records, jobs, and images are served only to who may see them"
```

### Task 4: 공유 API

**Files:**
- Modify: `backend/app/api/sessions.py`, `backend/app/api/schemas.py`
- Test: `backend/tests/test_session_access.py`

**Interfaces:**
- Produces: `GET /api/sessions/{id}/shares -> list[ShareEntry]`, `POST /api/sessions/{id}/shares {email} -> list[ShareEntry]`(201), `DELETE /api/sessions/{id}/shares/me`(204), `DELETE /api/sessions/{id}/shares/{user_id}`(204). `ShareEntry(user_id: int, email: str)`. `me` 경로를 먼저 등록한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_the_creator_shares_by_email_and_the_friend_can_open_it(...):
    res = creator.post(f"/api/sessions/{sid}/shares", json={"email": " Friend@Example.com "})
    assert res.status_code == 201 and [e["email"] for e in res.json()] == ["friend@example.com"]
    assert friend.get(f"/api/sessions/{sid}").status_code == 200

def test_sharing_with_an_email_nobody_uses_is_a_404_saying_so(...):
    assert res.json()["detail"] == "No account uses that email."

def test_sharing_twice_or_with_myself_changes_nothing(...): ...
def test_sharing_needs_an_approved_creator_but_unsharing_only_the_creator(...):
    # can_create 끈 생성자: POST 403, DELETE 204. 공유받은 사람의 POST 403.
def test_removing_a_session_from_my_list_keeps_it_for_everyone_else(...):
    assert friend.delete(f"/api/sessions/{sid}/shares/me").status_code == 204
    assert friend.get(f"/api/sessions/{sid}").status_code == 404
    assert creator.get(f"/api/sessions/{sid}").status_code == 200
def test_shares_me_is_a_404_for_whoever_has_no_share(...): ...
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd backend && uv run pytest tests/test_session_access.py -k "share or list" -v`
Expected: FAIL, 405 또는 404.

- [ ] **Step 3: 구현.** 자기 자신을 지정하면 아무것도 저장하지 않고 목록을 돌려준다.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/test_session_access.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend
git commit -m "feat: the creator shares a session by email and a sharer can leave it"
```

### Task 5: 운영자 생성, 비밀번호 재설정, 계정 관리, 운영 문서

**Files:**
- Create: `backend/app/accounts/admin.py`, `backend/app/accounts/reset_password.py`, `backend/app/api/accounts.py`
- Modify: `backend/app/main.py`, `backend/app/api/__init__.py`, `.env.example`, `compose.yaml`, `compose.dev.yaml`, `README.md`
- Test: `backend/tests/test_admin.py`

**Interfaces:**
- Produces: `admin.ensure_admin_from(db, env) -> None`. `reset_password.main(argv: list[str]) -> int`. `GET /api/accounts -> list[User]`, `PUT /api/accounts/{id} {can_create: bool} -> User`(라우터 전체 `admin_only`).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_the_env_creates_the_admin(store):
    ensure_admin_from(store, {"ADMIN_EMAIL": "boss@example.com", "ADMIN_PASSWORD": "12345678"})
    assert store.accounts.by_email("boss@example.com").is_admin

@pytest.mark.parametrize("env", [{}, {"ADMIN_EMAIL": "boss@example.com"}, {"ADMIN_EMAIL": "boss@example.com", "ADMIN_PASSWORD": "short"}])
def test_without_usable_values_the_app_warns_and_old_sessions_stay_hidden_until_they_come(store, caplog, env):
    old = store.sessions.create(sample_draft(), [])
    ensure_admin_from(store, env)
    assert "ADMIN_EMAIL" in caplog.text and store.shares.created_by(old.id) is None
    ensure_admin_from(store, {"ADMIN_EMAIL": "boss@example.com", "ADMIN_PASSWORD": "12345678"})
    assert store.shares.created_by(old.id) is not None

def test_reset_prints_a_new_password_once_and_ends_the_logins(store, capsys, monkeypatch): ...
def test_reset_of_an_unknown_email_exits_1(store, capsys, monkeypatch): ...
def test_the_admin_lists_accounts_and_turns_creation_on(...): ...
def test_others_cannot_see_or_change_accounts(...): ...
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd backend && uv run pytest tests/test_admin.py -v`
Expected: FAIL, import 오류.

- [ ] **Step 3: 구현과 문서**

`default_app`에서 `create_app` 전에 `ensure_admin_from(db, os.environ)`을 호출한다. `reset_password`는 `DB_PATH`를 `default_app`과 같은 방식으로 읽고 `secrets.token_urlsafe(12)`로 임시 비밀번호를 만든다.

문서: `.env.example`에 `ADMIN_EMAIL=`, `ADMIN_PASSWORD=`를 주석과 함께 추가하고 `COOKIE_SECURE`를 설명한다. `compose.dev.yaml`의 backend에 `COOKIE_SECURE: "false"`. `compose.yaml`의 "The app has no login" 주석을 고친다. `README.md`의 "The app has no login yet." 문단을 지우고 운영자 설정, 승인, `python -m app.accounts.reset_password EMAIL`을 설명한다.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/test_admin.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend .env.example compose.yaml compose.dev.yaml README.md
git commit -m "feat: the admin comes from the environment and approves accounts"
```

### Task 6: 사람별 중복 체크

**Files:**
- Modify: `backend/app/db/expressions.py`, `backend/app/db/sessions.py`, `backend/app/generation/jobs.py`, `backend/app/api/sessions.py`
- Test: `backend/tests/test_expressions.py`, `backend/tests/test_swaps.py`, `backend/tests/test_jobs.py`

**Interfaces:**
- Produces: `ExpressionRepo.pick(count, rng, exclude=(), seen_by: int | None = None)`, `SessionRepo.used_words(limit_sessions=40, seen_by: int | None = None)`, `SessionRepo.swap_expression(session_id, expression_id, rng=None, seen_by=None)`, `SessionRepo.add_expression(session_id, rng=None, seen_by=None)`. `seen_by=None`은 전체 기록을 본다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_what_someone_else_was_taught_stays_new_for_me(store):
    ids = seed_expressions(store, 2)
    me, other = add_user(store, "me@example.com"), add_user(store, "other@example.com")
    store.sessions.create(sample_draft(), [ids[0]], created_by=other.id)
    assert {e.id for e in store.expressions.pick(2, random.Random(1), seen_by=me.id)} == set(ids)

def test_what_was_shared_with_me_counts_as_seen(store):
    ids = seed_expressions(store, 2)
    me, other = add_user(store, "me@example.com"), add_user(store, "other@example.com")
    shared = store.sessions.create(sample_draft(), [ids[0]], created_by=other.id)
    store.shares.share(shared.id, me.id)
    assert [e.id for e in store.expressions.pick(1, random.Random(1), seen_by=me.id)] == [ids[1]]

def test_once_all_are_seen_my_own_oldest_comes_first(store): ...
def test_a_swap_avoids_what_the_requester_saw(store): ...
def test_the_words_to_avoid_come_from_my_sessions_only(store): ...
def test_a_job_uses_its_starters_history(tmp_path): ...  # Recording.excluded와 고른 표현 확인
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd backend && uv run pytest tests/test_expressions.py tests/test_swaps.py tests/test_jobs.py -v`
Expected: FAIL, `seen_by` 인자 없음.

- [ ] **Step 3: 구현.** `USES` 서브쿼리를 `session_id IN (SELECT id FROM sessions WHERE created_by = ? UNION SELECT session_id FROM session_shares WHERE user_id = ?)`로 좁힌다. `_run`은 `job.created_by`를, 라우트는 `me.id`를 넘긴다. `recent_topics`는 바꾸지 않는다.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend
git commit -m "feat: expressions and words repeat per person, not across everyone"
```

### Task 7: 항목별 별표

**Files:**
- Modify: `backend/app/db/sessions.py`, `backend/app/api/sessions.py`, `backend/app/api/schemas.py`, `frontend/src/api.ts`, `frontend/src/lib/useStars.ts`
- Test: `backend/tests/test_store.py`, `backend/tests/test_api.py`, `frontend/src/lib/useStars.test.ts`

**Interfaces:**
- Produces: `SessionRepo.set_star(session_id, kind: Literal["expressions", "words"], item: int, starred: bool) -> Stars`. `PUT /api/sessions/{id}/stars/{kind}/{item} {starred: bool} -> Stars`. `api.setStar(sessionId, kind, item, starred)`. `SessionRepo.set_stars`, `PUT .../stars`, `api.setStars`는 지운다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_two_people_starring_different_words_keep_both(store):
    session = store.sessions.create(sample_draft(), [])
    a, b = [v.id for v in session.content.vocabulary[:2]]
    store.sessions.set_star(session.id, "words", a, True)
    assert store.sessions.set_star(session.id, "words", b, True).words == [a, b]

def test_an_item_of_another_session_is_ignored(store): ...
```

`useStars.test.ts`: 누른 항목만 `api.setStar`로 보내고, 응답의 목록을 보여 주고, 실패하면 서버가 마지막으로 준 목록으로 되돌린다.

- [ ] **Step 2: 프론트 의존성 설치 후 실패 확인**

Run: `cd frontend && npm ci && npx vitest run src/lib/useStars.test.ts; cd ../backend && uv run pytest tests/test_store.py -k star -v`
Expected: FAIL

- [ ] **Step 3: 구현**

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest -q && cd ../frontend && npx vitest run src/lib/useStars.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend frontend/src
git commit -m "fix: a star saves on its own, so two people starring do not erase each other"
```

### Task 8: 변경 알림과 이벤트 스트림

**Files:**
- Create: `backend/app/live/__init__.py`, `backend/app/live/changes.py`, `backend/app/api/events.py`
- Modify: `backend/app/db/__init__.py`, `backend/app/db/sessions.py`, `backend/app/db/records.py`, `backend/app/db/shares.py`, `backend/app/db/expressions.py`, `backend/app/api/__init__.py`, `frontend/nginx.conf`, `backend/Dockerfile`, `compose.dev.yaml`, `AGENTS.md`, `CLAUDE.md`
- Test: `backend/tests/test_changes.py`

**Interfaces:**
- Produces:
  - `changes.SessionChange(StrEnum)`: `SESSION="session"`, `STARS="stars"`, `NOTE="note"`, `RECORDS="records"`, `ACCESS="access"`
  - `changes.SessionChanges`: `publish(session_id: int, change: SessionChange) -> None`(스레드 안전, 예외 없음), `subscribe(session_id: int) -> Subscription`(이벤트 루프에서 호출)
  - `Subscription`: `async next(timeout: float) -> set[SessionChange]`(시간 초과면 빈 집합), `close() -> None`
  - `Database.changes: SessionChanges`
  - `events.events_of(subscription, still_allowed: Callable[[], Awaitable[bool]], heartbeat_s: float = 25) -> AsyncIterator[str]`
  - `GET /api/sessions/{id}/events`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
@pytest.mark.parametrize("write,expected", [
    (lambda db, s: db.sessions.set_note(s.id, Note(text="x")), {"note"}),
    (lambda db, s: db.sessions.set_star(s.id, "words", s.content.vocabulary[0].id, True), {"stars"}),
    (lambda db, s: db.sessions.add_expression(s.id), {"session"}),
    (lambda db, s: db.sessions.swap_expression(s.id, s.content.expressions[0].id), {"session", "stars"}),
    (lambda db, s: db.sessions.add_figure(s.id, None, db.pictures.add(None, None, None), "c", None, None), {"session"}),
    (lambda db, s: db.sessions.replace_picture(s.content.vocabulary[0].id, "image", db.pictures.add(None, None, None)), {"session"}),
    (lambda db, s: db.records.add_example(s.id, s.content.vocabulary[0].id, "u", "c", 1.0), {"records"}),
    (lambda db, s: db.records.add_summary(s.content.article.paragraphs[0].id, "u", SummaryFeedback(...), 1.0), {"records"}),
    (lambda db, s: db.records.add_reading(s.content.article.paragraphs[0].id, "u", 1.0, []), {"records"}),
    (lambda db, s: db.expressions.delete(s.content.expressions[0].id), {"session"}),
    (lambda db, s: db.sessions.delete(s.id), {"access"}),
])
def test_every_write_says_what_changed_after_it_commits(store, write, expected): ...
    # publish를 기록하는 가짜를 store.changes에 넣고, 기록 시점에 다른 연결로 읽어 커밋된 값이 보이는지도 확인한다

def test_a_write_that_fails_says_nothing(store): ...  # 없는 세션의 add_figure: KeyError, 발행 없음
def test_unsharing_signals_access(store): ...

async def test_changes_published_from_another_thread_wake_the_stream(): ...
async def test_a_burst_of_one_change_arrives_as_one_event_however_slow_the_reader(): ...
async def test_events_carry_only_a_name(): ...
    # event: stars\ndata: {}\n\n 형식, 데이터 없음
async def test_access_never_reaches_the_browser_while_i_am_allowed(): ...
async def test_losing_access_sends_gone_and_ends(): ...
async def test_a_login_gone_stale_ends_the_stream_at_the_next_heartbeat(): ...
    # still_allowed가 False로 바뀌면 heartbeat 뒤 gone 후 종료 (heartbeat_s=0.01)
def test_opening_the_stream_needs_access(...): ...  # 익명 401, 접근권 없음 404
```

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd backend && uv run pytest tests/test_changes.py -v`
Expected: FAIL, `app.live`를 찾을 수 없음.

- [ ] **Step 3: `SessionChanges` 구현**

구독자마다 `pending: set[SessionChange]`와 `asyncio.Event`를 둔다. `publish`는 잠금 안에서 구독자 목록을 복사한 뒤, 각 구독자의 루프에 `call_soon_threadsafe`로 집합 추가와 이벤트 설정을 예약한다. 루프가 닫혔으면 `RuntimeError`를 삼킨다.

- [ ] **Step 4: 저장소에서 발행**

스펙의 이벤트 표대로, 각 메서드의 `with self._db.connect()` 블록이 끝난 뒤 `self._db.changes.publish(...)`를 호출한다. 라우트, job, 콜백에는 넣지 않는다. `replace_picture`는 `vocabulary`에서 `session_id`를 함께 읽고, `add_summary`와 `add_reading`은 문단의 세션을 찾으며, `ExpressionRepo.delete`는 지우기 전에 영향받는 세션 번호를 읽어 세션마다 발행한다. `SessionRepo.create`는 발행하지 않는다.

- [ ] **Step 5: 스트림 구현**

`events_of`의 흐름:

```python
while True:
    changed = await subscription.next(heartbeat_s)
    if not await still_allowed():
        yield 'event: gone\ndata: {}\n\n'
        return
    if not changed:
        yield ': keep-alive\n\n'
    for change in sorted(changed - {SessionChange.ACCESS}):
        yield f'event: {change}\ndata: {{}}\n\n'
```

라우트는 `require_access` 후 `StreamingResponse(media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})`를 돌려주고, `still_allowed`는 쿠키의 토큰으로 `user_of_login`과 `can_access`를 `run_in_threadpool`에서 확인한다. 구독은 `finally`에서 닫는다.

- [ ] **Step 6: 프록시, 종료, 규칙 문서**

`frontend/nginx.conf`의 `location /api/` 앞에 추가:

```nginx
location ~ ^/api/sessions/[0-9]+/events$ {
    proxy_pass http://backend:8765;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 1h;
}
```

`backend/Dockerfile`의 CMD와 `compose.dev.yaml`의 command에 `"--timeout-graceful-shutdown", "5"`를 더한다.

`AGENTS.md`와 `CLAUDE.md`의 Versioning 절 뒤에 다음 절을 더한다.

```markdown
# Client-server communication

- REST owns all state: every read and write goes through it. The event stream `GET /api/sessions/{id}/events` carries only the name of what to read again, never data.
- Only repositories in `backend/app/db` publish events, after commit. Routes, jobs, and callbacks do not.
- In the browser, only `useSessionResource` subscribes. Nothing else opens an `EventSource`.
- New shared session state gets a GET route and an event name. One person's temporary progress is polled.
```

- [ ] **Step 7: 통과 확인**

Run: `cd backend && uv run pytest -q`
Expected: 전부 PASS

- [ ] **Step 8: 커밋**

```bash
git add backend frontend/nginx.conf compose.dev.yaml AGENTS.md CLAUDE.md
git commit -m "feat: repositories announce what changed, and a stream tells the session's viewers"
```

### Task 9: 프론트 인증과 로그인, 가입 페이지

**Files:**
- Create: `frontend/src/lib/auth.tsx`, `frontend/src/lib/safeNext.ts`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/SignupPage.tsx`, `frontend/src/pages/AuthPage.css`
- Modify: `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/App.tsx`
- Test: `frontend/src/lib/safeNext.test.ts`, `frontend/src/pages/AuthPages.test.tsx`, `frontend/src/api.test.ts`

**Interfaces:**
- Produces:
  - `types.Me = { id: number; email: string; is_admin: boolean; can_create: boolean }`
  - `api.ApiError extends Error { status: number }`. `request`가 이것을 던진다. `/api/auth/` 밖의 401은 `/login?next=<현재 경로>`로 보낸다.
  - `api.me()`, `api.login(email, password)`, `api.signup(email, password)`, `api.logout()`
  - `useAuth(): { me: Me | null; loading: boolean; logIn(email, password): Promise<void>; signUp(email, password): Promise<void>; logOut(): Promise<void> }`, `AuthProvider`, `RequireAuth`
  - `safeNext(raw: string | null): string`

- [ ] **Step 1: 실패하는 테스트 작성**

```ts
test.each(['//evil.example', 'https://evil.example', '/\\evil.example', 'evil', '', null])('next %s goes home', (raw) => {
  expect(safeNext(raw)).toBe('/')
})
test('a path on this site is kept', () => expect(safeNext('/s/26?x=1#article')).toBe('/s/26?x=1#article'))
```

`AuthPages.test.tsx`:

- 가입 페이지의 세 빈칸을 `getByLabelText('Email')`, `'Password'`, `'Confirm password'`로 찾을 수 있다.
- 두 비밀번호가 다르면 "The two passwords don't match yet."가 나오고 `api.signup`을 호출하지 않는다.
- 잘못된 이메일로 제출하면 "Enter an email address, like you@example.com."이 나온다. 8자 미만이면 "At least 8 characters."가 강조된다.
- 로그인 401이면 서버의 문구를 보여 주고 페이지에 머문다.
- 비로그인으로 `/s/26`에 가면 `/login?next=%2Fs%2F26`로 가고, 로그인 후 `/s/26`으로 돌아온다. 이미 로그인했으면 `/login`은 `/`로 간다.

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd frontend && npx vitest run src/lib/safeNext.test.ts src/pages/AuthPages.test.tsx src/api.test.ts`
Expected: FAIL

- [ ] **Step 3: 구현**

`App.tsx`: `BrowserRouter` > `AuthProvider` > `Routes`. `/login`, `/signup`은 공개, 나머지는 `RequireAuth`와 `CornerTools`를 가진 레이아웃 라우트 아래에 둔다.

페이지는 시안 B안의 마크업과 CSS를 옮긴다. 원본은 시안 캔버스의 `BLogin`, `BSignup`이며 수치는 스펙의 "로그인, 회원가입" 절을 따른다. 색과 글꼴은 `base.css`의 변수(`--marker`, `--error`, `--serif`, `--sans` 등)를 쓴다. 문장은 `<span class="lead">`와 `<span class="slot">`로 나눠, 640px 초과에서는 인라인으로, 이하에서는 줄을 쌓는다. 폭 640px 이하, 세로 760px 이하에서 `.lede`를 숨긴다.

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add frontend/src
git commit -m "feat: sign in and sign up pages, and every other page needs a login"
```

### Task 10: 권한별 화면, 계정 관리, 공유 화면

**Files:**
- Create: `frontend/src/components/SessionCreator.tsx`, `frontend/src/components/AccountsPanel.tsx`, `frontend/src/components/SharePanel.tsx`, `frontend/src/components/SharePanel.css`
- Modify: `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/pages/HomePage.tsx`, `frontend/src/pages/SessionPage.tsx`, `frontend/src/components/CornerTools.tsx`, `frontend/src/components/SettingsModal.tsx`, `frontend/src/components/VocabularyTab.tsx`
- Test: `frontend/src/pages/HomePage.test.tsx`, `frontend/src/components/CornerTools.test.tsx`, `frontend/src/components/SharePanel.test.tsx`, `frontend/src/components/AccountsPanel.test.tsx`, `frontend/src/components/VocabularyTab.test.tsx`

**Interfaces:**
- Consumes: `useAuth`, Task 3, 4, 5의 API.
- Produces: `api.listAccounts()`, `api.setCanCreate(id, value)`, `api.listShares(sessionId)`, `api.addShare(sessionId, email)`, `api.removeShare(sessionId, userId)`, `api.leaveSession(sessionId)`. `VocabularyTab`의 새 prop `canRedraw: boolean`. `SessionSummary`, `Session` 타입에 `mine`, `shared_by`.

- [ ] **Step 1: 실패하는 테스트 작성**

- 생성 권한이 없으면 주제 선택 대신 "Session creation isn't on for this account yet. Ask the admin to turn it on."이 보이고 `api.topics`를 호출하지 않는다.
- 빈 목록이면 "Nothing here yet. Sessions shared with you appear here."가 보인다.
- 공유받은 세션은 공유한 사람의 이메일과 Remove를 보여 주고, Remove는 `api.leaveSession`을 호출한다. 내 세션은 Delete를 보여 주고 `api.deleteSession`을 호출한다.
- `CornerTools`: 모두에게 로그아웃 버튼, 운영자에게만 데이터베이스와 설정 버튼.
- `SharePanel`: `mine && can_create`이면 입력란과 목록, `mine`이면 목록과 해제 버튼, 그 외에는 렌더링하지 않는다. 없는 이메일이면 "No account uses that email."을 보여 준다.
- `AccountsPanel`: 이메일, 가입일, "Can create sessions" 토글. 토글하면 `api.setCanCreate`를 호출한다. 운영자 행의 토글은 비활성이다.
- `VocabularyTab`: `canRedraw`가 거짓이면 다시 그리기 버튼이 없다.

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd frontend && npx vitest run src/pages/HomePage.test.tsx src/components/CornerTools.test.tsx src/components/SharePanel.test.tsx src/components/AccountsPanel.test.tsx src/components/VocabularyTab.test.tsx`
Expected: FAIL

- [ ] **Step 3: 구현**

`SessionCreator`는 `HomePage`의 `useTopics`, `useGenerationJob`, `TopicPicker`, `GenerationProgress`를 옮겨 받는다. 그래서 권한이 없는 계정은 `api.topics`를 호출하지 않는다. `SharePanel`은 `SessionPage`의 `<aside className="rail">` 안 탭 목록 아래에 둔다. `AccountsPanel`은 `SettingsModal`에 "Accounts" 탭으로 더한다. 설정 필드 그룹과 달리 저장 버튼 없이 바로 저장한다. `canRedraw`는 `session.mine && (me.can_create || me.is_admin)`이다.

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add frontend/src
git commit -m "feat: screens follow the account: creation, sharing, and account approval"
```

### Task 11: 세션 화면의 실시간 반영

**Files:**
- Create: `frontend/src/lib/sessionChanges.ts`, `frontend/src/lib/useDrawingPictures.ts`
- Delete: `frontend/src/lib/useArrivingPictures.ts`
- Modify: `frontend/src/lib/useStars.ts`, `frontend/src/lib/useNote.ts`, `frontend/src/lib/useExamples.ts`, `frontend/src/lib/useSummaries.ts`, `frontend/src/lib/useReadingMarks.ts`, `frontend/src/components/SummaryTab.tsx`, `frontend/src/pages/SessionPage.tsx`, `frontend/src/test-setup.ts`
- Test: `frontend/src/lib/sessionChanges.test.ts`, `frontend/src/lib/useStars.test.ts`, `frontend/src/lib/useNote.test.ts`, `frontend/src/pages/SessionPage.test.tsx`

**Interfaces:**
- Produces:
  - `type SessionChange = 'session' | 'stars' | 'note' | 'records'`
  - `useSessionResource(sessionId: number, change: SessionChange, read: () => Promise<unknown>): void`. `read`는 `useCallback`으로 안정적이어야 한다.
  - `useSessionGone(sessionId: number, onGone: () => void): void`
  - `useDrawingPictures(sessionId: number): boolean`. `GET /api/jobs`만 3초마다 폴링한다.
  - 테스트용 `FakeEventSource`를 `test-setup.ts`에 전역으로 둔다.

- [ ] **Step 1: 실패하는 테스트 작성**

`sessionChanges.test.ts`:

- 같은 세션을 읽는 훅이 여럿이어도 `EventSource`는 하나이고, 마지막 훅이 사라지면 닫힌다.
- 처음에 한 번 읽고, 그 이벤트에 다시 읽고, 다른 이벤트에는 읽지 않는다.
- 읽는 중에 이벤트가 세 번 와도 끝난 뒤 한 번만 더 읽고, 두 번째 읽기가 끝나기 전에는 읽기가 겹치지 않는다.
- 다시 연결(`open` 두 번째)되면 모든 자원을 다시 읽는다.
- `gone`을 받으면 `onGone`을 호출한다.
- `EventSource`가 `CLOSED`가 되면 `session` 자원을 다시 읽고 5초 뒤 다시 연다.

`useStars.test.ts`:

```ts
test('a read that lands between two quick toggles does not undo them', async () => {
  // setStar 두 건을 대기시킨 채 stars 이벤트로 getStars가 옛 목록을 돌려줘도 화면은 두 별표를 유지하고,
  // 마지막 setStar의 응답이 최종 목록이 된다
})
```

`useNote.test.ts`:

- 저장하지 않은 입력이 있을 때 `note` 이벤트로 다른 내용을 받아도 입력이 그대로다.
- 저장이 끝난 뒤의 `note` 이벤트는 새 내용을 보여 준다.

`SessionPage.test.tsx`:

- `gone` 이벤트에 "This session is no longer available."와 홈 링크가 나온다. `getSession`의 404도 같다.
- `session` 이벤트에 새 표현과 그림이 새로고침 없이 나타난다.

- [ ] **Step 2: 실행해서 실패 확인**

Run: `cd frontend && npx vitest run src/lib/sessionChanges.test.ts src/lib/useStars.test.ts src/lib/useNote.test.ts src/pages/SessionPage.test.tsx`
Expected: FAIL

- [ ] **Step 3: `sessionChanges.ts` 구현**

모듈 안의 `Map<number, Channel>`이 세션당 연결 하나를 참조 수로 관리한다. `useSessionResource`는 실행 중 여부와 "한 번 더" 표시만으로 읽기를 직렬화한다.

- [ ] **Step 4: 훅 전환**

세션 데이터를 읽는 곳을 모두 `useSessionResource` 하나로 바꾸고 기존의 초기 로드 `useEffect`를 지운다. 대응: `useStars`와 `stars`, `useNote`와 `note`, `useExamples`, `useSummaries`, `useReadingMarks`, `SummaryTab`과 `records`, `SessionPage`의 `getSession`과 `session`. `useStars`의 읽기는 저장 대기 수가 0일 때만 결과를 반영한다. `NoteSaver.loaded`는 `touched` 대신 `inFlight`가 아니고 `shown === stored`일 때만 반영한다. `useArrivingPictures`를 지우고 `useDrawingPictures`로 바꾼다.

- [ ] **Step 5: 경계 확인**

Run: `cd frontend && grep -rn "EventSource" src --include='*.ts' --include='*.tsx' | grep -v -E 'test|sessionChanges.ts'`
Expected: 출력 없음

- [ ] **Step 6: 통과 확인**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add frontend/src
git commit -m "feat: an open session re-reads what others change, through one hook"
```

### Task 12: 브라우저 전체 검증

**Files:**
- Test: 스크래치패드의 Playwright 스크립트 (저장소에 넣지 않는다)

**Interfaces:**
- Consumes: 전체 앱.

- [ ] **Step 1: 임시 데이터 폴더로 개발 스택을 띄운다**

운영 데이터(`backend/data`)를 건드리지 않도록 스크래치패드에 브랜치를 `git clone`하고, 그 복제본의 `.env`에 `ADMIN_EMAIL=boss@example.com`, `ADMIN_PASSWORD=12345678`, `COOKIE_SECURE=false`, 비어 있는 `FRONTEND_PORT`를 적는다.

Run: 복제본에서 `docker compose -f compose.yaml -f compose.dev.yaml -p tme-test up -d --build`
Expected: 시작 로그에 운영자 생성, `/login`이 200.

- [ ] **Step 2: 흐름을 PC(1280×800)와 폰(390×844) 폭에서 실행해 스크린샷을 확인한다**

브라우저 컨텍스트 세 개(운영자, A, B)로 다음을 확인한다.

1. A, B 가입. A의 홈에 생성 불가 문구가 보인다.
2. 운영자가 A를 승인하면 A의 홈에 주제 선택이 나타난다. 복제본에는 Claude 토큰이 없으므로 실제 생성은 하지 않고, 컨테이너 안에서 Python으로 `db.sessions.create(..., created_by=<A의 id>)`를 호출해 표현이 든 세션을 넣는다.
3. A가 B에게 공유. B의 홈에 나타나고 Remove가 보인다.
4. 두 화면을 열어 둔 채 A의 별표, 노트, 표현 교체, 연습 기록이 B 화면에 새로고침 없이 2초 안에 보인다. 반대 방향도 확인한다.
5. B가 노트 입력 중(저장 전)에 A가 노트를 저장해도 B의 입력이 남는다.
6. 탭을 네트워크 오프라인으로 만든 사이 변경하고, 온라인으로 돌리면 놓친 변경이 보인다.
7. A가 공유를 해제하면 B 화면이 "This session is no longer available."로 바뀐다. 다시 공유한 뒤 A가 삭제해도 같다.
8. 로그아웃 후 API와 그림 URL을 직접 호출하면 401이다.

Expected: 전부 기대대로. 어긋나면 해당 Task로 돌아가 테스트를 먼저 추가한다.

- [ ] **Step 3: 전체 테스트와 정리**

Run: `cd backend && uv run pytest -q && cd ../frontend && npx vitest run && npx tsc -b`, 이어서 복제본에서 `docker compose -p tme-test down -v`
Expected: 전부 PASS, 임시 스택 제거.

- [ ] **Step 4: 인덱스 갱신과 그래프 확인**

Run: `gitnexus analyze --index-only && node .gitnexus/run.cjs detect-changes --scope compare --base-ref main --repo .`
Expected: `partial`이나 `truncated` 없음. 영향받는 흐름을 보고 내용에 적는다.

배포는 이 계획에 넣지 않는다. 서버 `.env`에 `ADMIN_EMAIL`, `ADMIN_PASSWORD`를 넣는 순서가 필요하므로 사용자의 확인을 받고 진행한다. 배포 후에는 Cloudflare를 거치는 공개 주소에서 Step 2의 4번을 다시 확인한다.
