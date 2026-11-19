# Summarize 피드백을 서버 뒤에서 판정하기

- 상태: 구현됨 (2026-11-20). 구현 계획: `docs/superpowers/plans/2026-11-20-background-summary-feedback.md`.
- 범위: Summarize의 판정과 저장을 서버가 뒤에서 한다. 브라우저는 Done 직후 문단을 풀고 다음 일로 넘어간다. 저장된 요약에 말한 사람을 기록한다. DB 스키마가 v18로 바뀐다.

## 목적

사용자는 문단마다 Read aloud와 Summarize를 이어 하고, 피드백은 끝까지 진행한 뒤 한꺼번에 보려 한다. 지금은 Summarize에서 Done을 누르면 판정이 끝날 때까지 기사의 모든 버튼이 꺼져서 기다려야 한다.

### 지금 막히는 이유

- Done 뒤에 브라우저가 판정(`POST /api/summary/feedback`, claude CLI 실행)을 부르고, 그 답을 받아 저장(`POST /api/summaries`)한다. 둘이 끝나야 `useSummary`의 `dismiss()`가 `onEnd()`를 부른다 (`frontend/src/components/Summarize.tsx`).
- 그때까지 `ArticleTab`의 `reading`이 이 문단을 가리킨다. 다른 모든 문단은 `active`가 참이라 Read aloud와 Summarize가 꺼진다 (`frontend/src/components/ArticleTab.tsx`).
- 같은 문단의 Read aloud는 `summary.state !== null`이라 꺼진다 (`frontend/src/components/Paragraph.tsx`).
- 마이크는 Done을 누를 때 이미 풀린다 (`useLiveRound.close`). 기다리는 이유는 화면 상태뿐이다.

### 지금 있는 결함

- 판정 중에 다른 탭으로 가면 `ArticleTab`이 화면에서 빠진다 (`SessionPage`가 지금 탭만 그린다). `useSummary`의 effect가 정리되며 `live`가 거짓이 되고, 판정 결과를 저장하지 않는다. 서버는 이미 판정 가격을 정산했다. 크레딧은 빠지고 요약은 남지 않는다.
- 요약 카드는 누가 말했든 모두 "You"로 보인다. `summaries` 테이블에 말한 사람이 없다.

## 사용자가 정한 것 (2026-11-20 대화)

1. 판정은 서버가 뒤에서 한다. 공유 세션이므로 같은 세션의 다른 사람도 판정 중인 요약을 보고, 말한 사람이 탭을 옮기거나 새로고침해도 결과가 남아야 한다. 브라우저 안에서만 뒤로 돌리는 방식은 고르지 않았다.
2. 저장된 요약에 말한 사람을 기록하고, 카드에 그 이름을 보인다. 이전 요약은 이름 없이 남는다.

## 설계자가 정한 것 (사용자에게 보였고 이의가 없었던 것)

1. Done을 누르면 브라우저는 말한 문장만 서버에 보낸다. 서버는 판정 가격을 잡아 두고 "판정 중" 줄을 저장한 뒤 곧바로 답한다. 브라우저는 그 답을 받는 즉시 문단을 푼다.
2. 판정이 실패하면 판정 가격을 돌려준다. 카드에 오류와 "Judge again", "Remove"가 남는다. "Judge again"은 다시 말하지 않고 같은 문장으로 다시 판정하며, 누른 사람이 값을 낸다.
3. 판정 중에 서버가 재시작되면 그 줄은 실패로 바뀐다.
4. 녹음 가격(`summary_voice`)은 판정이 실패해도 돌려주지 않는다. 말한 문장이 남아 다시 판정할 수 있기 때문이다. 지금은 판정 실패 때 `round.giveBack()`으로 돌려준다.
5. `POST /api/summary/feedback`는 없앤다. 이 경로를 부르는 곳은 Summarize뿐이다.

## 목표

- Done 뒤 서버의 첫 답이 오면 바로 모든 문단의 Read aloud와 Summarize가 다시 눌린다. 같은 문단도 마찬가지다.
- 판정 중인 요약은 그 문단 아래에 카드로 보이고, 세션의 모든 화면에 보인다. 판정이 끝나면 모든 화면에서 피드백으로 바뀐다.
- 여러 판정이 동시에 돌 수 있다. 한 사람이 문단 다섯 개를 연달아 요약해도 서로 기다리지 않는다.
- `POST /api/summaries`가 나간 뒤에는 탭 이동, 새로고침, 창 닫기가 판정과 저장을 막지 않는다. Done과 POST 사이의 짧은 대기는 아래 "Done 직후의 대기"를 따른다.
- 카드에 말한 사람이 보인다: 내 것은 "You", 다른 사람 것은 그 사람의 `username`.

## 하지 않는 것

- 피드백을 끝날 때까지 숨기는 기능. 피드백은 도착하는 대로 보인다.
- 판정 프롬프트, schema, 모델 설정(`SUMMARY_MODEL`, `SUMMARY_EFFORT`) 변경.
- 가격 변경. `summary_voice` 5, `summary_feedback` 5 그대로다.
- 판정이 끝난 요약을 지우는 기능. Remove는 실패한 요약에만 있다.
- 판정 진행률 표시. 판정 중이라는 사실만 보인다.
- Read aloud 기록(`readings`)에 말한 사람을 남기는 일.

## 실패로 보는 것

- 판정이 돌거나 실패한 요약이 화면에서 조용히 사라지는 것.
- 크레딧이 빠졌는데 피드백도, 다시 판정할 길도 없는 요약.
- 한 판정이 실패했다고 다른 판정이나 다음 Summarize가 막히는 것.
- 세션 생성 job 뒤에 줄을 서서 판정이 몇 분씩 늦어지는 것 (아래 "판정 실행").

## 설계

### 흐름

```
브라우저                                서버
Done ─► 녹취 닫힘, 말한 문장 확정
      POST /api/summaries ───────────► 판정 가격 hold (모자라면 402)
      {paragraph_id, user_text,         summaries에 status='judging' 줄 저장 ─► records 이벤트
       seconds}                         판정을 실행기에 넘김
      ◄─── 201 Summary(judging) ───────
슬립 닫고 문단 풀기 (onEnd)
판정 중 카드 표시                        (뒤에서) coach.feedback(paragraph, user_text)
                                         성공: feedback 저장, status='done', hold 정산 ─► records
                                         실패: error 저장, status='failed', hold 반환 ─► records
records 이벤트 ─► GET /api/summaries ─► 카드가 피드백 또는 실패로 바뀜
```

### DB (스키마 v18)

SQLite는 칸의 NOT NULL을 바꿀 수 없으므로 `summaries`를 새로 만들어 옮긴다. 재구성 방식은 `backend/app/db/schema.py`의 `_examples_of_words`(v6에서 v7)를 따른다: 이름을 바꾸고, 인덱스를 지우고, 새 테이블을 만들어 옮긴 뒤, 옛 테이블을 지우고 id 카운터를 이어 간다. 새 요약이 지워진 요약의 id를 다시 쓰지 않게 하기 위해서다.

```sql
CREATE TABLE summaries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    paragraph_id INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_text    TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'done' CHECK (status IN ('judging', 'done', 'failed')),
    feedback     TEXT,
    error        TEXT,
    seconds      REAL    NOT NULL DEFAULT 0,
    CHECK ((status = 'done') = (feedback IS NOT NULL))
) STRICT;
CREATE INDEX summaries_paragraph ON summaries (paragraph_id);
```

- `user_id`는 말한 사람이다. 기존 줄은 NULL로 옮긴다. 계정이 지워지면 NULL이 된다.
- `status`: `judging`(판정 중), `done`(피드백 있음), `failed`(판정 실패). 기존 줄은 모두 `done`이다.
- `error`는 `failed`일 때 화면에 보일 문구다. 다시 판정을 시작하면 비운다.
- v1 이관(`backend/app/db/migrate.py`의 `INSERT INTO summaries`)은 칸 이름을 적어 넣으므로 그대로 동작한다. 이관한 줄은 기본값으로 `done`, `user_id` NULL이 된다.

### API

| 경로 | 하는 일 | 응답 |
|---|---|---|
| `POST /api/summaries` | 말한 요약을 받아 판정을 시작한다. 본문 `{paragraph_id, user_text, seconds}`. | 201, `Summary` (status `judging`). 크레딧이 모자라면 402, 판정기가 꺼져 있으면 503, 문단 접근 불가면 404, 빈 `user_text`면 422 |
| `GET /api/summaries?session_id=` | 지금과 같다. 모든 상태의 줄을 만든 순서로 준다. | `Summary[]` |
| `POST /api/summaries/{id}/judge` | 실패한 요약을 같은 문장으로 다시 판정한다. 누른 사람이 값을 낸다. | 200, `Summary` (status `judging`). `failed`가 아니면 409, 402와 404는 위와 같다 |
| `DELETE /api/summaries/{id}` | 실패한 요약을 지운다. | 204. `failed`가 아니면 409 |
| `POST /api/summary/feedback` | 없앤다. | |

- 세 쓰기 경로 모두 그 요약이 속한 세션에 접근할 수 있는 사람이면 누구나 부를 수 있다 (`require_paragraph`와 같은 기준).
- `Summary` 응답 모양: `id`, `created_at`, `paragraph_id`, `user_text`, `seconds`, `status`, `feedback` (`done`일 때만, 아니면 null), `error` (`failed`일 때만, 아니면 null), `speaker` (말한 사람의 `username`, 모르면 null), `mine` (요청한 사람이 말한 사람이면 참). `mine`은 `SessionSummary.mine`처럼 서버가 요청자 기준으로 계산한다.
- 판정에 쓰는 문단 텍스트는 서버가 `paragraph_id`로 DB에서 읽는다. 브라우저가 보낸 문단 텍스트를 믿지 않는다.
- 다시 판정의 상태 전환은 원자적이다: `failed`인 줄만 `judging`으로 바꾸는 한 번의 UPDATE로 차지한다. 두 사람이 동시에 누르면 한 쪽은 409를 받고 그 쪽의 hold는 반환된다. 가격 hold는 상태를 바꾸기 전에 잡는다 (402가 상태를 건드리지 않게).
- 모든 상태 변경(저장, 판정 시작, 성공, 실패, 삭제)은 `RecordRepo`가 커밋한 뒤 `SessionChange.RECORDS`를 알린다. 라우트와 실행기는 이벤트를 직접 보내지 않는다 (`CLAUDE.md`의 Client-server communication).

### 판정 실행

- 판정은 세션 생성용 `JobRunner.executor`와 따로 둔 실행기에서 돈다. 생성 job 실행기는 `max_workers=2`이고 한 생성이 수백 초 걸리므로, 같은 실행기를 쓰면 판정이 그 뒤에 줄을 선다.
- 실행기의 동시 실행 수는 4로 둔다 (설계자의 판단). 넘치는 판정은 차례를 기다린다. 판정 하나가 claude CLI 프로세스 하나다.
- 실행기는 `create_app`에서 주입할 수 있게 한다. 테스트는 `InlineExecutor`나 붙잡아 두는 실행기(`backend/tests/test_api.py`)로 판정의 앞뒤 상태를 본다.
- 작업 하나가 하는 일: 문단 텍스트를 읽고 `SummaryCoach.feedback`을 부른다. 성공하면 feedback을 저장하고 `done`으로 바꾸고 hold를 정산한다. `GenerationError`든 다른 예외든 실패하면 `failed`와 오류 문구를 저장하고 hold를 반환하고 로그를 남긴다. 오류 문구는 지금 `failed("feedback", e)`가 만드는 "feedback failed: …"와 같은 꼴로 짧게 둔다.
- 판정 중에 세션이 지워져 줄이 사라졌으면, 판정은 이미 돌았으므로 hold를 정산하고 결과는 버린다.
- 앱이 시작할 때 `release_abandoned()` 옆에서 `judging`으로 남은 줄을 모두 `failed`로 바꾸고 오류 문구를 "The server restarted before the feedback came back."으로 둔다. 그 줄의 hold는 `release_abandoned()`가 이미 반환한다. 시작 시에는 구독자가 없으므로 이벤트를 보내지 않는다.

### 프런트엔드

- `useSummary` (`Summarize.tsx`): 녹취가 닫히고 말한 문장이 있으면 `api.addSummary({paragraph_id, user_text, seconds})`를 부른다. 성공하면 `onKept(summary)`, `dismiss()` 순으로 슬립을 닫고 문단을 푼다. 이 요청이 실패하면(402, 503, 네트워크) 지금처럼 슬립에 오류를 남기고 `round.giveBack()`으로 녹음 가격을 돌려준다. 이때는 문장이 서버에 없으므로 녹음 가격을 돌려주는 것이 맞다. 슬립의 Retry는 지금처럼 새로 녹음한다.
- 이 요청은 effect의 `live` 검사로 버리지 않는다. 컴포넌트가 사라진 뒤 응답이 오면 화면 상태만 건드리지 않는다. 서버는 이미 줄을 저장했으므로 다른 화면과 다음 읽기에서 보인다.
- Done 직후의 대기 (설계자의 판단): Done을 누른 뒤 마지막 말이 들어오기를 최대 3초 기다린다 (`FLUSH_TIMEOUT_MS`, `frontend/src/lib/live/geminiWebsocket.ts`). POST는 그 뒤에 나간다. 이 사이에 탭을 옮기면 `ArticleTab`이 사라지면서 그 회는 버려진다. 이 대기를 살리려면 녹취 회를 탭 전환보다 위로 올려야 해서 일이 크게 늘어나므로 범위 밖으로 둔다. 대신 POST를 보내기 전에 컴포넌트가 사라지면 녹음 가격(`summary_voice`)을 돌려준다. 지금은 코치가 없는 회라서 이 경우 돌려주지 않는다.
- 슬립의 hint "Reading your summary against the paragraph…"는 이제 슬립이 아니라 판정 중 카드에 보인다. 슬립의 `writing`은 저장 요청이 도는 짧은 순간만 뜻한다.
- `SummaryPanel`의 요약 목록은 상태별로 그린다.
  - `judging`: 말한 문장과 "Reading your summary against the paragraph…".
  - `failed`: 말한 문장, 오류 문구, "Judge again"과 "Remove" 버튼.
  - `done`: 지금과 같은 `Feedback`.
  - 왼쪽 표시는 `mine`이면 "You", 아니면 `speaker`, `speaker`가 null이면 "Someone" (설계자의 판단, presence의 `SOMEONE`과 같은 말).
- "Judge again"과 "Remove"는 api를 부르고 결과는 `records` 이벤트로 다시 읽는다. "Judge again"은 `usePrice('summary_feedback')`로 가격을 보이고, 모자라면 끈다. 요청이 실패하면 카드 안에 그 오류를 보인다.
- `Paragraph`: 판정 중인 요약은 아무 버튼도 막지 않는다. 지금의 막힘 조건(`active`, `summary.state !== null`, `round.phase !== null`)은 그대로 두되, `summary.state`가 저장 요청 직후 null이 되므로 판정 시간 동안 막히지 않는다.
- `SummaryTab`: 목록은 모든 상태를 보인다. note는 `done`이면 지금처럼 `feedback.summary`, `judging`이면 "Waiting for feedback…", `failed`면 "No feedback: judge it again in the Article tab."이다.
- `SummaryTab`에도 말한 사람을 보인다 (설계자의 판단). 끝에 피드백을 한꺼번에 보는 곳이 이 목록이고, 공유 세션에서는 여러 사람의 요약이 섞이기 때문이다. 카드 label은 문단 첫머리 앞에 말한 사람을 붙인다 ("You · In the classic memory…"). 이름 규칙은 위 `SummaryPanel`과 같다. 섹션 제목 "Paragraphs you summed up"은 "Paragraphs summed up"으로 바꾼다.
- `types.ts`의 `Summary`를 위 응답 모양에 맞춘다. `api.ts`에서 `summaryFeedback`을 지우고 `addSummary`의 인자를 바꾸고, `judgeSummaryAgain(id)`와 `removeSummary(id)`를 더한다.
- 새 이벤트 이름은 없다. 모든 변경은 기존 `records`로 알린다.

### 문서

- `docs/superpowers/specs/2026-11-01-credits-design.md`의 가격표에서 "Summarize 피드백" 행의 경로를 `POST /api/summaries`와 `POST /api/summaries/{id}/judge`로 고친다.
- `agents/summary-coach/AGENT.md`나 README가 판정 흐름을 브라우저 기준으로 적고 있으면 서버 기준으로 고친다.

## 빌더에게 맡기는 것

- v18 재구성의 정확한 SQL과 단계 함수 이름.
- 판정 작업을 둘 모듈 위치 (`backend/app/coaching/` 안 또는 별도 모듈)와 실행기 이름.
- `mine`과 `speaker`를 계산하는 위치 (repository 조회의 join 또는 라우트).
- 카드의 정확한 마크업과 CSS. 지금 `Summarize.css`의 `slip`과 `summary-feedback` 꼴을 따른다.
- 다시 판정한 줄의 목록 위치, 로컬 추가(`onKept`)와 다시 읽기의 중복 처리, 다시 판정 경로에서 503과 402를 확인하는 순서.
- 테스트 구성. 최소한 다음을 확인한다: 저장 직후 `judging`과 이벤트, 성공 시 `done`과 정산, 실패 시 `failed`와 반환, 시작 시 `judging` 정리, 다시 판정의 409와 402, Remove의 409, 다른 사람이 본 `mine`과 `speaker`, Done 뒤 다른 문단 버튼이 바로 눌림, 화면이 사라진 뒤에도 저장 요청을 버리지 않음.
