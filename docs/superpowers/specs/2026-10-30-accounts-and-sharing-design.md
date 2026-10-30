# 계정, 세션 생성 권한, 세션 공유 설계

- 상태: 설계 (2026-10-30). 구현 전.
- 범위: 회원가입과 로그인, 세션 생성 승인, 세션별 공유, 모든 API의 권한 검사, 관련 화면, 스키마 v10.

## 목적

| 문제 (지금) | 해결 |
|---|---|
| 누구나 Claude 구독으로 세션을 만들 수 있다 | 운영자가 승인한 계정만 만든다 |
| 모든 방문자가 모든 세션을 본다 | 만든 사람과, 그 사람이 지정한 계정만 본다 |
| 설정, 삭제, 음성 토큰 API가 인증 없이 열려 있다 (`PUT /api/settings`, `DELETE /api/sessions/{id}`, `GET /api/assessor/token`) | 인증과 공개 API 두 개를 제외한 모든 경로가 로그인을 요구한다 |

## 사용자가 정한 것

| 항목 | 결정 |
|---|---|
| 화면 | B안, 폼이 영어 문장 하나다 (시안: https://claude.ai/artifact/RPb6kDVgvmYvur1qadbLaP, B 행) |
| 가입 항목 | 이메일 형식 아이디, 비밀번호, 비밀번호 확인. 이메일 인증 없음 |
| 세션 생성 | 운영자가 승인한 계정만. 가입 직후에는 권한 없음 |
| 공유 | 세션마다 만든 사람이 이메일로 대상을 지정 |
| 별표, 노트, 말하기 연습 기록 | 세션에 하나씩, 공유자가 함께 쓴다 (지금 구조 유지). 노트는 나중에 저장한 내용으로 덮어쓰인다 |
| 운영자의 열람 | 데이터베이스 페이지의 링크로 다른 사람의 세션을 열 수 있다 |

이 문서의 나머지는 설계자의 판단이며, 승인 전까지 바꿀 수 있다.

## 권한

계정은 세 가지 값으로 판단한다. 역할 표를 따로 두지 않는다.

- `is_admin`: 운영자. 한 명뿐이다. 세션 생성 권한을 포함한다.
- `can_create`: 운영자가 켜 주는 세션 생성 권한.
- 세션 접근권: 그 세션을 만든 사람, `session_shares`에 있는 사람, 또는 운영자.

여기서 연습 권한(`can_practice`)을 계산한다. `is_admin` 또는 `can_create`이거나, 내가 만든 세션 또는 공유받은 세션이 하나 이상이면 참이다. 코치와 음성 API는 Gemini와 Azure 비용이 들고 요청에 세션 번호가 없다. 가입은 누구나 할 수 있으므로 로그인만 요구하면 비용 제한이 되지 않는다.

| 경로 | 조건 |
|---|---|
| `POST /api/auth/signup`, `POST /api/auth/login` | 공개 |
| `POST /api/auth/logout`, `GET /api/auth/me` | 로그인 |
| `GET /api/sessions` | 로그인. 내가 만든 세션과 공유받은 세션만 |
| `POST /api/sessions` | `can_create` 또는 `is_admin` |
| `GET`, `DELETE /api/jobs...` | 그 job을 시작한 사람만 |
| `GET /api/sessions/{id}`, 별표와 노트의 `GET`/`PUT`, `examples`, `summaries`, `readings` | 세션 접근권 |
| `DELETE /api/sessions/{id}`, 표현 교체와 추가, 공유 해제 | 세션을 만든 사람만 |
| 그림 다시 그리기, 공유 추가 | 세션을 만든 사람이면서 `can_create` 또는 `is_admin` |
| `GET /api/images/{name}` | 그 그림을 쓰는 세션에 접근권 |
| `read-aloud`, `summary`, `example`, `assessor/token`, `speech` | `can_practice` |
| `GET /api/topics`, `POST /api/topics/refresh` | `can_create` 또는 `is_admin` |
| `/api/topics/all`, 주제 삭제, `/api/expressions`와 그 삭제, `/api/settings/*`, `/api/accounts/*` | `is_admin` |

응답 규칙:

- 로그인하지 않았으면 401.
- 역할이 모자라면 403.
- 없는 세션과 접근권 없는 세션은 똑같이 404다. 세션 번호로 존재 여부를 알아낼 수 없게 한다.
- 운영자는 다른 사람의 세션에 공유받은 사람과 같은 권한을 가진다. 삭제, 표현 교체, 공유 관리는 할 수 없고, 그 세션은 운영자의 홈 목록에 나오지 않는다. 데이터베이스 페이지의 링크로 연다.

운영자가 `can_create`를 끄면 비용이 새로 드는 생성, 그림 다시 그리기, 공유 추가만 막힌다. 이미 돌고 있는 job은 끝까지 간다. 그 계정이 만든 세션, 이미 지정한 공유, 연습 권한은 유지한다.

## 운영자 계정

`.env`의 `ADMIN_EMAIL`, `ADMIN_PASSWORD`로 시작 시 만든다.

- 운영자가 아직 없을 때만 동작한다. 있으면 두 값을 무시한다.
- 그 이메일의 계정이 이미 있으면 비밀번호를 덮어쓰고 운영자로 올린다. `.env`를 고칠 수 있는 사람이 곧 운영자이기 때문이다. 그 계정의 기존 로그인은 모두 끊는다.
- 운영자를 만들 때 `created_by`가 비어 있는 기존 세션을 모두 운영자 소유로 넘긴다.
- 값이 없거나 비밀번호가 8자 미만이면 경고를 남기고 운영자 없이 뜬다. 소유자 없는 세션은 아무도 볼 수 없다.

"첫 가입자가 운영자" 또는 "그 이메일로 가입하면 운영자" 방식은 쓰지 않는다. 사이트가 공개되어 있고 이메일을 확인하지 않으므로, 먼저 가입하는 사람이 운영자가 될 수 있다.

## 데이터 (스키마 v10)

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,   -- 앞뒤 공백 제거, 소문자로 저장
    password_hash TEXT    NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    can_create    INTEGER NOT NULL DEFAULT 0
) STRICT;
CREATE UNIQUE INDEX users_one_admin ON users (is_admin) WHERE is_admin = 1;

CREATE TABLE logins (
    token_hash TEXT PRIMARY KEY,             -- 쿠키 토큰의 SHA-256. 토큰 원문은 저장하지 않는다
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT    NOT NULL
) STRICT;
CREATE INDEX logins_user ON logins (user_id);

CREATE TABLE session_shares (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    PRIMARY KEY (session_id, user_id)
) STRICT;
CREATE INDEX session_shares_user ON session_shares (user_id);

ALTER TABLE sessions ADD COLUMN created_by INTEGER REFERENCES users(id);
```

`schema.upgrade`의 기존 패턴대로 `version < 10` 단계를 더한다. 업그레이드 전 백업은 `Database`가 이미 만든다. 새 파일용 `SCHEMA`에도 같은 정의를 넣는다. `created_by`는 v9 파일을 이어받기 위해 NULL을 허용한다.

## 인증 동작

| 항목 | 내용 |
|---|---|
| 비밀번호 해시 | 표준 라이브러리 `hashlib.scrypt` (n=2^15, r=8, p=1, 랜덤 salt). 파라미터를 해시 문자열에 함께 저장. 새 의존성 없음 |
| 비밀번호 규칙 | 8자 이상 1024자 이하. 그 외 제한 없음 |
| 이메일 검사 | `이름@도메인.최상위` 형식만 확인. 소문자로 정규화 |
| 로그인 토큰 | `secrets.token_urlsafe(32)`. DB에는 SHA-256만 저장 |
| 쿠키 | 이름 `login`, `HttpOnly`, `SameSite=Lax`, `Path=/`, 30일. `Secure`는 `COOKIE_SECURE` 환경변수를 따른다 (기본 켜짐, `compose.dev.yaml`만 끔) |
| CSRF | `SameSite=Lax`로 막는다. 상태를 바꾸는 요청은 모두 POST, PUT, DELETE다 |
| 로그인 실패 | 없는 이메일과 틀린 비밀번호를 같은 문구, 같은 401로 답한다. 없는 이메일에도 해시를 한 번 계산해 응답 시간을 맞춘다 |
| 로그인 제한 | 이메일별 15분에 실패 10회를 넘으면 429. 메모리에 둔다 |
| 가입 제한 | 전체 시간당 20건을 넘으면 429. 메모리에 둔다. 터널 뒤라 클라이언트 IP를 믿을 수 없어 IP 단위로 세지 않는다 |
| 가입 | 성공하면 바로 로그인 상태가 된다. 중복 이메일은 409. 서버는 `email`, `password`만 받고, 비밀번호 확인은 화면에서 검사한다 |
| 로그아웃 | `logins` 행을 지우고 쿠키를 만료시킨다. 만료된 행은 로그인할 때 함께 지운다 |
| 비밀번호 재설정 | 이메일 인증이 없어 화면 기능을 두지 않는다. `docker compose exec backend uv run --no-dev python -m app.accounts.reset_password EMAIL`이 임시 비밀번호를 한 번 출력하고 그 계정의 로그인을 모두 끊는다 |

## 백엔드 구조

```
app/accounts/passwords.py        해시와 검증
app/accounts/limits.py           로그인 실패와 가입 횟수 제한
app/accounts/reset_password.py   재설정 명령
app/db/accounts.py               users, logins, session_shares 저장소
app/api/auth.py                  signup, login, logout, me
app/api/accounts.py              운영자의 계정 목록과 can_create 변경
app/api/deps.py                  Me, 역할 검사, 세션 접근 검사
```

- **기본 거부:** `create_app`이 라우터를 등록할 때 인증 라우터를 제외한 전부에 `dependencies=[Depends(signed_in)]`을 건다. 새 경로를 만들면서 검사를 잊어도 최소한 로그인은 요구한다.
- **세션 접근:** `require_session`을 `require_access(db, me, session_id)`와 `require_creator(db, me, session_id)`로 바꾼다. `require_paragraph`도 문단이 속한 세션의 접근권을 본다.
- **기록 조회:** `GET /api/examples`, `summaries`, `readings`의 `session_id`도 접근권을 검사한다. 지금은 검사가 없다.
- **그림:** `/api/images`의 `StaticFiles` 마운트를 라우트로 바꾼다. 그림 번호로 `vocabulary.picture_id`, `vocabulary.example_picture_id`, `figures.picture_id`를 찾아 그 세션의 접근권을 확인한다. 번호가 순차적이라 로그인 검사만으로는 다른 세션의 그림을 볼 수 있다. 응답에 `Cache-Control: private, max-age=86400`을 붙인다.
- **세션 생성:** `Job`에 `created_by`를 더하고 `SessionRepo.create`로 넘긴다. `jobs.open()`과 조회, 닫기는 시작한 사람으로 거른다.
- **공유:** `GET`, `POST /api/sessions/{id}/shares`, `DELETE /api/sessions/{id}/shares/{user_id}`. 가입된 계정의 이메일만 받는다. 없으면 404 "No account uses that email." 자기 자신과 중복 지정은 그대로 성공으로 처리한다.
- **별표:** 지금은 브라우저가 가진 전체 목록을 저장해서, 두 사람이 같은 세션을 열어 두면 한 사람의 별표가 다른 사람의 저장으로 지워진다. `PUT /api/sessions/{id}/stars`를 `PUT /api/sessions/{id}/stars/{kind}/{item}` (`{"starred": bool}`, `kind`는 `expressions` 또는 `words`)로 바꾸고, `useStars`는 누른 항목만 보낸 뒤 응답의 전체 목록으로 화면을 갱신한다.
- **응답 추가:** `SessionSummary`와 `Session`에 `mine: bool`, `shared_by: str | None`(만든 사람의 이메일, 내 세션이면 없음)을 더한다.

## 화면

UI 문구는 지금 앱과 같이 영어다.

### 로그인, 회원가입 (`/login`, `/signup`)

시안의 B안을 따른다.

- 로그인: "Hi, my email is ___ and my password is ___."
- 가입: "Hi, I'm new here. My email is ___, I'd like my password to be ___, and one more time, that's ___."
- 빈칸마다 화면에 보이지 않는 `<label>`을 둔다. 포커스된 빈칸은 형광펜 색(`--marker`)으로 칠한다.
- 비밀번호 확인이 다르면 입력 중에 "The two passwords don't match yet."를 보여 주고 제출하지 않는다.
- PC: 문장이 한 덩어리로 이어지고, 쉼표와 마침표는 빈칸에 붙어 줄이 갈리지 않는다.
- 폭 640px 이하: 문구 한 줄, 빈칸 한 줄을 번갈아 쌓는다. 빈칸은 버튼과 같은 폭이고 쉼표와 마침표는 오른쪽 여백으로 나간다. 글자 크기는 `min(1.8rem, 8.1vw)`. 안내와 오류는 해당 빈칸 바로 아래에 둔다. 앱 이름과 소개 문구는 위에, 폼은 아래에 붙인다. 세로 760px 이하에서는 소개 문구를 숨긴다.
- 이메일 칸은 `inputmode="email"`, `autocapitalize="none"`, `autocomplete="username"`을 쓴다. 비밀번호 칸은 `new-password` 또는 `current-password`를 쓴다.

### 나머지 화면

- **라우팅:** `/login`, `/signup`을 뺀 모든 경로는 로그인이 필요하다. 로그인 후 `next`로 돌아가되 같은 사이트 안의 경로만 허용한다. API의 401은 `/login`으로 보낸다. 이미 로그인했으면 `/login`, `/signup`은 `/`로 보낸다.
- **홈:** `can_create`가 없으면 주제 선택 대신 "Session creation isn't on for this account yet. Ask the admin to turn it on."을 보여 준다. 세션 목록이 비면 "Nothing here yet. Sessions shared with you appear here."를 보여 준다. 공유받은 세션에는 공유한 사람의 이메일을 표시하고 Delete를 숨긴다.
- **세션 화면:** 만든 사람에게만 왼쪽 레일에 공유 대상 목록과 해제 버튼을 보여 주고, 표현 교체와 추가도 만든 사람에게만 보여 준다. 공유 입력란과 그림 다시 그리기는 생성 권한도 있어야 보인다. 그 외 기능은 공유받은 사람도 그대로 쓴다.
- **오른쪽 위 버튼:** 모든 사용자에게 로그아웃 버튼을 더한다. 데이터베이스와 설정 버튼은 운영자에게만 보인다.
- **계정 관리:** 설정 창에 운영자 전용 Accounts 구역을 더한다. 이메일, 가입일, "Can create sessions" 토글을 나열한다.

## 배포

순서를 지켜야 한다. 값을 넣지 않고 올리면 운영자 없이 떠서 기존 세션을 아무도 볼 수 없다. 값을 넣고 다시 띄우면 복구된다.

1. 서버 `.env`에 `ADMIN_EMAIL`, `ADMIN_PASSWORD`를 넣는다.
2. `git pull && docker compose up -d --build`. 스키마 v10 이전, 백업, 운영자 생성, 기존 세션 이전이 시작할 때 자동으로 일어난다.

함께 고칠 문서:

- `.env.example`에 두 값을 추가한다.
- `compose.yaml`의 "The app has no login" 주석을 고친다.
- `README.md`의 "The app has no login yet." 문단을 지우고 운영자와 비밀번호 재설정을 설명한다.

## 하지 않는 것

- 이메일 인증, 이메일로 비밀번호 찾기, 본인 비밀번호 변경, 계정 삭제
- 그룹 공유, 공유 링크, 소셜 로그인, 2단계 인증
- 계정별 생성 횟수 제한
- 사람별 별표, 노트, 연습 기록
- 공유자 사이의 실시간 동기화. 상대의 별표, 노트, 기록은 새로고침해야 보인다
- 표현 corpus, 주제 풀, "이미 가르친 단어" 목록의 계정별 분리. 지금처럼 전체가 함께 쓴다

## 알려진 한계

- 이메일을 확인하지 않으므로 남의 이메일로 먼저 가입할 수 있다. 그 이메일로 세션을 공유하면 먼저 가입한 사람이 받는다. 운영자가 승인할 때도 이메일만 보고 판단한다.
- 공유 입력란과 가입의 409로 어떤 이메일이 가입되어 있는지 알 수 있다. 공유 입력란은 세션 생성 권한자만 쓴다.
- 횟수 제한은 메모리에 있어 재시작하면 초기화된다.
- `ADMIN_PASSWORD`는 `.env`에 평문으로 있다. 다른 키와 같은 수준으로 다룬다. 운영자 생성 후에는 지워도 된다.

## 검증

- **권한 표 전체:** 모든 경로를 비로그인, 미승인, 공유받은 계정, 승인 계정, 운영자로 호출해 기대한 상태 코드를 확인한다. `app.routes`를 순회해, 공개 경로를 뺀 경로가 익명 요청에 모두 401인지도 확인한다. 새 경로가 생기면 자동으로 검사된다.
- **세션 격리:** 다른 사람의 세션, 그림, 기록을 번호로 직접 요청하면 404다.
- **이전:** v9 파일을 v10으로 올리면 데이터가 유지되고, 운영자 생성 시 기존 세션이 넘어가는지 확인한다.
- **인증:** 로그인 실패 문구 동일, 횟수 제한, 만료된 토큰 거부, 로그아웃 후 쿠키 무효, DB에 토큰과 비밀번호 원문 없음.
- **프론트:** 두 페이지의 검증과 이동, 권한별 UI 표시를 테스트한다. 끝으로 Playwright로 PC와 폰 폭에서 가입, 승인, 생성 버튼 노출, 공유, 로그아웃을 실제로 돌려 본다.

## 구현자에게 맡기는 것

CSS 세부값과 컴포넌트 분할, 저장소 메서드 이름, 횟수 제한 자료구조, 커밋 단위.
