# 크레딧 설계

- 상태: 구현됨. 실패와 취소에서 얼마가 나가는지는 `2026-11-01-credit-transactions-design.md`가 정한다.
- 범위: 비용이 드는 기능마다 고정 크레딧을 차감하는 계정별 크레딧, 운영자의 수동 충전, 잔액과 내역 화면, `can_create`와 Practice 잠금의 삭제, 스키마 v13.
- 대체하는 문서: `2026-10-30-accounts-and-sharing-design.md`의 "권한" 중 `can_create`와 `can_practice`에 관한 부분. 세션 접근권(만든 사람, 공유받은 사람, 운영자)은 그대로다.

## 목적

| 문제 (지금) | 해결 |
|---|---|
| 세션 생성은 운영자가 켜 주는 켜짐/꺼짐 권한 하나뿐이다. 한 번 켜 주면 한도가 없다 | 계정마다 크레딧 잔액이 있고, 비용이 드는 기능은 고정 가격을 차감한다 |
| 공유받은 세션이 하나라도 있으면 Practice, Summarize, Read aloud, 문장 듣기를 한도 없이 쓴다 | 그 기능들도 같은 크레딧에서 차감한다 |
| 운영자가 누가 얼마나 썼는지 알 수 없다 | 계정마다 차감과 충전 내역이 남는다 |

## 사용자가 정한 것

| 항목 | 결정 |
|---|---|
| 과금 방식 | 기능마다 고정 가격. 시작할 때 잡아 두고, 완수하면 확정한다. 실제 토큰 수는 세지 않는다 |
| 단위 | 1 크레딧 = 약 1센트. 가격은 실측 비용을 올림한 값 |
| 충전 | 당장은 운영자가 계정마다 수동으로 넣어 준다. 자동 지급 없음 |
| 운영자 | 차감하지 않는다 |
| `can_create` | 크레딧이 "Can create sessions" 토글과 Practice 잠금을 대체한다. 더는 필요 없는 기능과 제한은 과감히 지운다 |
| 공유받은 세션에서의 사용 | 기능을 쓴 사람의 크레딧에서 나간다 |
| 잔액 표시 | A안: 모든 페이지 구석의 둥근 버튼들 옆에 코인 알약으로 잔액을 보이고, 누르면 최근 내역이 열린다. 유료 버튼마다 가격이 붙는다 |
| 운영자 화면 | 데이터베이스 화면의 Accounts 탭에서 토글 대신 계정마다 잔액, 충전 칸, 최근 내역을 본다 |

가격표 (사용자 승인):

| 기능 | 경로 | 크레딧 |
|---|---|---|
| 세션 생성 | `POST /api/sessions` | 200 |
| 세션 취소 (Claude를 부른 뒤) | `DELETE /api/jobs/{id}` | 100 |
| 그림 다시 그리기 (장당) | `POST /api/sessions/{id}/pictures/{index}` | 10 |
| Practice 음성 세션 시작 | `POST /api/example/sessions` | 10 |
| Practice 글 피드백 | `POST /api/example/feedback` | 10 |
| Summarize 녹취 세션 시작 | `POST /api/summary/sessions` | 10 |
| Summarize 피드백 | `POST /api/summary/feedback` | 10 |
| Read aloud 발음 평가 토큰 (한 회에 한 번) | `GET /api/assessor/token` | 5 |
| Read aloud 코치가 표시된 단어를 말해 주기 (표시를 누를 때마다) | `POST /api/read-aloud/sessions` | 5 |
| 문장 듣기, 캐시에 없는 문장만 | `POST /api/speech` | 1 |
| 뉴스 토픽 새로고침 | `POST /api/topics/refresh` | 0 (공용 재고) |

설계자가 승인된 표에서 바꾼 것 하나: Read aloud는 호출이 둘이다. 한 회를 시작할 때 Azure 토큰을 한 번 받고, 평가가 끝난 뒤 틀린 단어의 표시를 누를 때마다 Gemini 코치 연결을 새로 열어 그 단어를 말해 준다(`frontend/src/components/ReadAloud.tsx`의 `ask` → `speak`). 표에는 토큰 5만 있었다. 코치 경로에도 가격이 있어야 그 경로만 직접 불러 공짜로 쓰는 길이 막힌다. 그래서 토큰 5, 표시 누르기 5다. 한 회의 값은 5 + 5 × (누른 표시 수)이고, 같은 표시를 두 번 누르면 두 번 나간다. 한 회에 코치 연결을 하나만 열어 두는 방식은 흐름을 고쳐야 하고 Gemini 음성은 연결 시간으로 과금되어 더 비쌀 수 있어 택하지 않았다.

한 회에 유료 호출이 둘인 Practice와 Summarize(음성 세션 10, 피드백 10)는 버튼에 회당 합계 20을 붙이고 잔액이 20보다 적으면 비활성으로 한다. 회 중간에 402가 나서 음성 세션 값만 날아가는 일을 막기 위해서다. 말을 하지 않고 끝낸 회는 10만 나간다. 이것은 설계자의 결정이다.

이 문서의 나머지는 설계자의 판단이며, 승인 전까지 바꿀 수 있다.

## 규칙

- 잔액은 내역의 합이다. 잔액 열을 따로 두지 않는다.
- 잡아 두기는 한 트랜잭션(`BEGIN IMMEDIATE`) 안에서 잔액을 구하고 모자라지 않으면 음수 행을 넣는다. 동시에 두 요청이 와도 잔액이 음수가 되지 않는다.
- 운영자의 요청은 차감도 기록도 하지 않는다.
- 검사 순서: 로그인(401), 세션 접근권과 만든 사람 검사(404, 403), 기능이 켜져 있는지(503), 그 다음 차감(402). 비용이 전혀 나가지 않은 요청에서 크레딧이 나가는 일이 없도록 차감이 맨 마지막이다.
- 모자라면 `402 Payment Required`, `detail`은 `Not enough credits: this needs 10 and you have 3.` 꼴이다. 화면은 그 문장을 그대로 보인다.
- 세션 생성: 요청 시점에 200을 잡아 두고 job을 시작한다. 끝난 뒤의 값은 트랜잭션 설계의 결과표를 따른다. 배포는 이미 생성이 돌고 있지 않을 때만 한다.
- 문장 듣기: 그 문장이 음성 캐시에 있으면 차감 없이 돌려준다. 없을 때만 1을 잡아 두고 읽는다.
- 뉴스 토픽 조회와 새로고침은 로그인한 누구나 쓸 수 있고 무료다. 재고는 공용이고 보충은 재고가 낮을 때만 일어난다.
- 공유 추가는 세션을 만든 사람이면 누구나 한다. 비용 없음.
- 표현 교체와 추가, 별표, 노트, 기록 저장과 조회, 세션 열람은 그대로 무료다.

## 데이터

스키마 v13. v14에서 `state`와 `open_until` 열이 늘었다 (트랜잭션 설계).

```sql
CREATE TABLE credits (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    at         TEXT    NOT NULL,          -- ISO 8601, UTC
    amount     INTEGER NOT NULL,          -- 충전은 양수, 차감은 음수
    kind       TEXT    NOT NULL,          -- 아래 목록
    detail     TEXT,                      -- 사람이 읽을 보충: 세션 주제, 단어, 문장 앞부분
    granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL  -- kind = 'grant'일 때 운영자
);
CREATE INDEX credits_by_user ON credits (user_id, id);
```

`kind`: `grant`, `session`, `session_cancelled`, `redraw`, `practice_voice`, `practice_feedback`, `summary_voice`, `summary_feedback`, `read_aloud_token`, `read_aloud_voice`, `speech`. 과거 행에는 `refund`도 있다. 새로 쓰지 않는다.

가격은 백엔드 한 곳(`app/credits.py` 같은 모듈)의 표로 두고, 화면은 API로 받는다. 두 곳에 적지 않는다.

업그레이드 (`schema.upgrade`, `version < 13`): `credits` 테이블을 만들고 `users.can_create` 열을 지운다(`ALTER TABLE users DROP COLUMN`, 컨테이너의 SQLite는 3.46). 기존 계정은 모두 잔액 0에서 시작한다. `can_create`가 켜져 있던 계정에도 자동으로 주지 않는다. 운영자가 채운다. 업그레이드 전 백업은 지금 방식(`sessions.db.bak-vN-DATE`) 그대로다.

지우는 것: `users.can_create`, `User.can_create`, `AccountRepo.set_can_create`, `AccountUpdate`, `PUT /api/accounts/{id}`, `deps.can_create`, `deps.Creator`, `deps.can_practice`, `ShareRepo.has_sessions`, 프런트의 `Me.can_create`, `api.setCanCreate`, `HomePage`의 `canCreate`와 `.home-locked` 문구, `SessionPage`의 `mayCreate`, `AccountsPanel`의 토글, 이들의 테스트. "Session creation isn't on for this account yet"와 "Practice opens once a session is shared with this account" 문구도 사라진다.

## API

| 경로 | 조건 | 내용 |
|---|---|---|
| `GET /api/me/credits` | 로그인 | `{ balance, prices, recent }`. `prices`는 kind별 가격 표. `recent`는 최근 내역 10건, 최신이 먼저. 운영자에게는 `balance: null`, `recent: []` |
| `GET /api/accounts` | 운영자 | 지금 목록에 `credits`(잔액, 운영자 행은 null)를 더한다 |
| `GET /api/accounts/{id}/credits` | 운영자 | 그 계정의 최근 내역 10건 |
| `POST /api/accounts/{id}/credits` | 운영자 | 본문 `{ amount }`, 0이 아닌 정수. 음수는 회수. `grant` 행을 넣고 그 계정의 `GET /api/accounts` 한 줄과 같은 모양을 돌려준다. 운영자 자신에게는 400 |
| `GET /api/topics`, `POST /api/topics/refresh` | 로그인 | 무료 |
| `POST /api/sessions/{id}/shares` | 세션을 만든 사람 | `Creator` 대신 `Me` + `require_creator` |
| 가격표의 경로들 | 각 경로의 기존 조건 + 차감 | 위 규칙의 검사 순서 |

내역 한 건: `{ at, amount, kind, detail }`.

이벤트: 계정 스트림 `GET /api/me/events`에 `credits`를 더한다. `CreditRepo`가 잔액을 바꾸는 쓰기를 커밋한 뒤 그 계정에 발행한다. 데이터는 싣지 않고 이름만 보낸다(프로젝트 규칙). 운영자가 충전하면 그 사람의 열린 탭에서 알약이 바로 바뀐다.

## 화면

공통: 가격은 `GET /api/me/credits`의 `prices`에서 온다. 잔액이 가격보다 적은 버튼은 비활성이고, `title`에 `Not enough credits: this needs 10 and you have 3.`를 보인다. 402 응답은 그 `detail`을 기존 오류 자리에 보인다.

- 구석 알약 (`CornerTools`): 운영자가 아닌 계정에만. 노란 코인과 잔액 숫자. `useAccountResource('credits', ...)`로 구독해 새로고침 없이 바뀐다. 누르면 잔액, 최근 내역 10건, "Ask the admin for more." 한 줄이 든 작은 패널이 열린다. 내역 한 줄은 날짜, 종류, 보충 설명, 금액이다. 예: `Nov 1 · Session · Blame for the Java Sea ferry… · −200`.
- 홈: `SessionCreator`를 모든 계정에 보인다. Generate 버튼에 `200`이 붙는다. 모자라면 버튼이 비활성이고 아래에 `120 credits left. A session costs 200. Ask the admin for more.`를 보인다. "Session creation isn't on for this account yet" 문구는 없어진다. 빈 목록 문구는 하나로 합친다.
- 세션 페이지: Practice와 Summarize 버튼에 회당 합계 `20`, Read aloud 버튼에 `5`가 붙는다. Read aloud에서 틀린 단어의 표시는 누르면 코치가 말해 주므로 `title`에 `Hear the coach · 5`를 보이고, 잔액이 5보다 적으면 표시가 비활성이다. 그림 다시 그리기(↻)는 만든 사람에게만 보이고(`canRedraw={session.mine}`), 툴팁에 `New picture · 10`을 보인다. 문장 듣기 버튼에는 가격을 붙이지 않는다(캐시에 있으면 무료라 미리 알 수 없다). 모자라서 402가 오면 기존 오류 자리에 보인다. `SharePanel`은 만든 사람에게 항상 추가 칸을 보인다.
- 데이터베이스 화면의 Accounts 탭 (운영자, `/database/accounts`): 계정마다 이메일과 가입일, 잔액, 숫자 칸(기본 200)과 `Add` 버튼, 그 아래 최근 내역. 음수를 넣으면 회수. 운영자 자신의 행은 `∞ not charged`이고 칸이 없다. 저장은 지금 토글처럼 즉시다.

## 테스트

백엔드:
- 잔액 3으로 10짜리 기능을 부르면 402이고 내역에 행이 없다. 잔액 10이면 성공하고 잔액 0, `kind`와 `detail`이 맞다.
- 운영자는 잔액 0이어도 성공하고 내역에 행이 없다.
- 기능이 꺼져 있거나(503) 제공자가 실패하면(502) 차감하지 않는다.
- 동시에 두 요청이 잔액 10으로 10짜리 기능을 부르면 하나만 성공한다.
- 세션 생성: 트랜잭션 설계의 결과표 한 줄마다 테스트가 있다.
- Read aloud: 토큰 −5, 표시를 두 번 누르면 −5가 두 번.
- 문장 듣기: 캐시에 있으면 차감 없음, 없으면 −1.
- 충전: 운영자가 `+500`, `-100`, `0`(422), 자기 자신(400), 없는 계정(404). 충전 뒤 그 계정의 스트림에 `credits` 이벤트가 온다.
- 스키마 v12 → v13: `credits`가 생기고 `can_create` 열이 없어지며 기존 행과 운영자가 그대로다.
- `GET /api/topics`는 잔액 0인 보통 계정도 200이다. 공유 추가는 잔액 0인 만든 사람도 201이다.

프런트:
- 알약이 잔액을 보이고 `credits` 이벤트 뒤 다시 읽는다. 운영자에게는 없다.
- 잔액이 모자라면 Generate와 Practice, Summarize, Read aloud 버튼이 비활성이고 `title`에 이유가 있다.
- 402 `detail`이 오류 자리에 보인다.
- Accounts 탭: `Add`가 `POST /api/accounts/{id}/credits`를 부르고 잔액과 내역이 바뀐다. 토글이 없다.

## 빌더에게 맡기는 것

- `CreditRepo`의 메서드 이름과 서명, 가격표 모듈의 위치.
- 알약 패널의 열고 닫기, 바깥 클릭과 Esc 처리, 모바일 폭에서의 자리.
- 내역 `detail`의 문구와 자르는 길이.
- Accounts 탭의 내역 줄 수(최근 10건 안에서).
- Accounts 탭의 운영자 행 표기와 CSS.
