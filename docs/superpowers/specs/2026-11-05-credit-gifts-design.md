# 크레딧 선물

- 상태: 구현됨 (2026-11-05). 구현 계획: `docs/superpowers/plans/2026-11-05-credit-gifts.md`.
- 범위: 일반 사용자가 자기 크레딧 일부를 다른 일반 사용자에게 보낸다. 오른쪽 위 크레딧 버튼의 패널에서 시작한다. DB 스키마는 바뀌지 않는다. `credits` 테이블에 새 `kind` 두 개가 생긴다.

## 목적

크레딧이 있는 사람이 크레딧이 없는 사람에게 준다. 공유 세션을 함께 하다 보면 한 사람이 AI 기능(연습 피드백, 요약 피드백, 소리 내어 읽기 코치, 그림 다시 그리기 등)을 쓰고 싶은데 크레딧이 모자라 못 쓸 때가 있다. 세션 생성(200)도 마찬가지다. 지금은 관리자만 크레딧을 줄 수 있다 (`POST /api/accounts/{user_id}/credits`, `CreditRepo.grant`). 그래서 같이 공부하는 사람이 바로 도와줄 방법이 없다.

## 사용자가 정한 것 (2026-11-05 대화)

1. 일반 사용자끼리 주고받는다. 관리자는 이 기능에 끼지 않는다.
2. 실수 방지 장치는 보내기 전 확인 모달 하나로 충분하다. 한도, 승인 절차, 받는 사람의 수락 단계는 두지 않는다.
3. 시작 지점은 오른쪽 위 크레딧 버튼(`CreditsPill`)의 패널이다. 지금 "Ask the admin for more."가 있는 자리에 "Gift credits" 버튼을 둔다.
4. 받는 사람은 username 검색으로 고른다. 세션 공유 패널(`SharePanel`)과 같은 검색이다. 가입한 누구에게나 보낼 수 있다.
5. 액수는 숫자 칸 하나로 넣는다. 미리 정한 액수 버튼은 없다.
6. 받는 사람에게는 잔액과 기록 줄만 바뀐다. 버튼 옆 표시나 화면 알림은 없다.

## 목표가 아닌 것

- 관리자가 선물을 주거나 받는 것. 관리자는 크레딧을 쓰지 않는다 (`balance`가 `None`, 크레딧 버튼이 안 보인다).
- 보낸 선물 되돌리기, 받는 사람의 거절이나 수락.
- 하루 한도, 한 번 한도, 액수 상한. 잔액이 유일한 상한이다.
- 선물에 메시지 붙이기.
- 세션 화면의 사람 목록에서 바로 선물하기. 이번에는 크레딧 패널 한 곳에서만 시작한다.
- 새 알림 장치(토스트 등).

## 화면 흐름 (보내는 사람)

앱 화면 문구는 영어다. 아래 따옴표 안이 화면에 나오는 문구다.

1. 크레딧 버튼을 눌러 패널을 연다. 패널은 지금처럼 잔액, 최근 기록, "Ask the admin for more."를 보여 준다. 그 아래에 "Gift credits" 버튼이 있다.
2. "Gift credits"를 누르면 패널 내용이 선물 화면으로 바뀐다. 맨 위에 username 검색칸(placeholder "their username")이 있다. 검색은 `usePeopleNamed`(`frontend/src/lib/usePeopleNamed.ts`, `GET /api/users?q=`)를 쓴다. 자기 자신은 서버가 빼므로 결과에 나오지 않는다. 결과가 없을 때와 검색이 실패했을 때의 문구는 `SharePanel`의 것("No one goes by a name like that.", "The search did not go through. Type again to retry.", "Looking…")을 그대로 쓴다. 선물 화면에는 패널의 원래 화면으로 돌아가는 "Back" 링크가 있다.
3. 결과에서 이름을 고르면 "Gift to minji" 제목 아래에 숫자 칸, "You have 240.", "Gift 200 credits" 버튼이 나온다. 버튼 문구의 숫자는 칸에 쓴 값을 따라간다. 칸이 비었거나 값이 맞지 않으면 버튼 문구는 "Gift credits"다.
4. 버튼은 칸의 값이 1 이상의 정수이고 지금 잔액 이하일 때만 눌린다. 잔액은 `useCredits()`에서 읽으므로 패널이 열려 있는 동안에도 바뀐다.
5. 버튼을 누르면 확인 모달이 뜬다.
   - 제목: "Gift 200 credits to minji?"
   - 본문: "You will have 40 left. A gift cannot be taken back."
   - 버튼: "Cancel", "Gift"
6. "Gift"를 누르면 요청을 보낸다. 요청이 도는 동안에는 "Gift"와 "Cancel"이 모두 눌리지 않고, Escape와 모달 바깥 누르기로도 닫히지 않는다. 그래서 두 번 눌러도 한 번만 보내고, 이미 보낸 선물을 취소했다고 착각할 일이 없다.
7. 성공하면 모달이 닫히고 패널은 원래 화면으로 돌아간다. 잔액과 기록은 계정 이벤트로 새로 읽힌다. 기록 맨 위에 "Gift to minji" 줄과 −200이 보인다.
8. 실패하면 모달 안에 서버가 준 문구를 보여 준다 (예: "Not enough credits: this needs 200 and you have 150."). 모달은 열린 채로 남고, "Cancel"로 닫을 수 있다.

잔액이 0 이하이면 "Gift credits" 버튼은 보이지만 눌리지 않는다.

## 받는 사람

받는 사람의 잔액은 새로고침 없이 바로 늘어난다. 지금도 크레딧이 바뀌면 `AccountChange.CREDITS`가 `GET /api/me/events`로 가고, `CreditsProvider`가 `useAccountResource('credits', ...)`로 `GET /api/me/credits`를 다시 읽는다. 패널 기록에는 "Gift from jun" 줄과 +200이 생긴다. 그 밖의 표시는 없다.

## 기록 줄

`CreditLine`(`frontend/src/components/CreditsPill.tsx`)이 새 `kind` 두 개를 읽는다.

| kind | 누구의 줄 | amount | detail | 화면 |
| --- | --- | --- | --- | --- |
| `gift_sent` | 보낸 사람 | 음수 | 받는 사람의 username | "Gift to minji" |
| `gift_received` | 받는 사람 | 양수 | 보낸 사람의 username | "Gift from jun" |

이 두 kind는 username이 레이블 안에 들어가므로 " · detail" 꼬리를 따로 붙이지 않는다. 관리자의 계정 화면도 같은 `CreditLine`으로 각 계정의 기록을 보여 주므로 거기서도 같은 문구가 나온다.

## 서버

### 경로

`POST /api/me/credits/gifts`, `backend/app/api/credits.py`의 기존 라우터(prefix `/api/me`)에 둔다.

- 요청 본문: `{"to": <받는 사람 user id>, "amount": <정수>}`. `amount`는 pydantic에서 1 이상으로 검사한다 (그 밖은 422).
- 성공: 204, 본문 없음. 보낸 사람의 화면은 계정 이벤트로 새로 읽는다.
- 오류:
  - 보낸 사람이 관리자: 400, "The admin has no credits to give."
  - `to`인 계정이 없음: 404, "account not found".
  - `to`가 자기 자신: 400, "You cannot gift credits to yourself."
  - `to`가 관리자: 400, "The admin is not charged, so there is nothing to add to." (관리자 지급 경로의 문구와 같다.)
  - 잔액 부족: 402, "Not enough credits: this needs 200 and you have 150." (`held_or_402`와 같은 문구 형식.)

### 저장소

`CreditRepo`에 `gift(sender: User, recipient: User, amount: int) -> None`을 더한다. `hold`와 같은 방식으로 한 트랜잭션 안에서 처리한다.

1. `BEGIN IMMEDIATE`로 쓰기 잠금을 먼저 잡는다. 동시에 들어온 선물과 hold가 같은 크레딧을 두 번 쓰지 못한다.
2. `_release_expired(conn)`.
3. 보낸 사람의 `_balance`가 `amount`보다 작으면 `NotEnoughCredits(amount, balance)`를 던진다. 잔액에는 아직 돌고 있는 hold가 빠져 있으므로, 세션 생성 중에 잡힌 200은 선물로 쓸 수 없다.
4. 보낸 사람에게 `-amount`, kind `gift_sent`, detail 받는 사람 username인 줄을 더한다.
5. 받는 사람에게 `+amount`, kind `gift_received`, detail 보낸 사람 username인 줄을 더한다.
6. 두 줄 모두 `granted_by`는 보낸 사람 id, `state`는 `settled`다.
7. 커밋한 뒤에 두 계정 모두에 `AccountChange.CREDITS`를 publish한다.

두 줄은 함께 들어가거나 함께 안 들어간다. 이벤트는 저장소만 publish한다는 규칙(`CLAUDE.md`의 Client-server communication)을 따른다.

관리자 여부, 자기 자신 여부, 계정 존재 여부는 경로에서 검사한다. 저장소는 잔액과 기록만 다룬다.

### 브라우저 API

`frontend/src/api.ts`에 `giftCredits: (to: number, amount: number) => request<void>('/api/me/credits/gifts', { method: 'POST', ... })`를 더한다. 다른 POST 함수의 본문 전달 방식을 따른다.

## 내가 정한 것 (사용자 확인 전)

- 선물은 되돌릴 수 없고, 모달에 그렇게 쓴다.
- "Ask the admin for more." 문구는 그대로 두고, 버튼을 그 아래에 둔다.
- `detail`에는 보낸 시점의 username을 적는다. 나중에 이름을 바꾸어도 기록 줄은 옛 이름을 보여 준다. 현재 이름을 보여 주려면 줄마다 계정을 다시 찾아야 하는데, 그만한 쓰임이 없다.
- 관리자 계정은 받는 사람이 될 수 없다. 검색 결과에서는 빼지 않고 (`PersonMatch`에 관리자 여부가 없다), 보내면 서버가 400으로 거절한다.
- 경로는 성공 시 204를 돌려주고, 화면은 이벤트로 새로 읽는다.
- 요청이 도는 동안 확인 모달은 어떤 방법으로도 닫히지 않는다.

## 구현에서 정한 것

- 선물 화면은 `frontend/src/components/GiftCredits.tsx`다. 액수 검사(`giftable`)와 "1 credit"/"N credits" 문구(`creditCount`)는 `frontend/src/lib/gifts.ts`에 있다.
- 검색 결과는 react-aria `Popover`가 아니라 패널 안의 평범한 목록이다. 확인 모달도 패널 DOM 안의 `role="alertdialog"` 카드로, CSS로 패널 위를 덮는다. 둘 다 portal이 아니므로 누를 때 `useCloseOnLeave`가 패널을 닫지 않는다. 카드가 뜨면 "Cancel"에 focus가 간다.
- 확인 카드는 물은 순간의 액수와 남을 잔액을 붙잡아 둔다. 선물 자신의 크레딧 이벤트가 POST 응답보다 먼저 와도 카드 내용이 바뀌거나 사라지지 않는다.
- 요청이 도는 동안 `CreditsPill`은 Escape, 바깥 누르기, 크레딧 버튼 다시 누르기를 모두 무시한다.
- 402 문구는 `backend/app/api/deps.py`의 `short_of_credits`가 만든다. 다른 유료 경로의 `held_or_402`와 같이 쓴다.
- CSS는 `CreditsPill.css`에 있고, `SharePanel`의 검색칸 모양과 `SettingsModal`의 확인 카드 모양을 따른다.

## 시험할 것

- 백엔드: 선물 뒤 두 잔액, 두 기록 줄의 kind, detail, amount, `granted_by`. 잔액 부족 시 402와 아무 줄도 안 생김. hold가 잡힌 크레딧은 선물로 못 씀. 자기 자신, 관리자에게, 관리자가 보내기, 없는 계정, 0과 음수 액수. 두 계정 모두 `AccountChange.CREDITS`를 받음.
- 프런트엔드: 검색해서 고르고, 액수를 쓰고, 모달에서 확인하면 `giftCredits`가 한 번 불림. 잔액보다 큰 값, 0, 소수, 빈 칸에서 버튼이 안 눌림. "Cancel"은 아무것도 보내지 않음. 실패 문구가 모달에 남음. `CreditLine`이 두 kind를 "Gift to X", "Gift from X"로 보여 줌.
