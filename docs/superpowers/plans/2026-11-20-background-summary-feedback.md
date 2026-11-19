# Summarize 피드백을 서버 뒤에서 판정하기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 이 세션에서 직접 실행하고 끝에 새 서브에이전트 리뷰를 한 번 한다. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Summarize의 Done 뒤 판정과 저장을 서버가 뒤에서 하고, 브라우저는 바로 문단을 풀어 다음 Read aloud와 Summarize로 넘어간다. 요약에 말한 사람이 남는다.

**Architecture:** `summaries` 줄이 `judging` → `done` 또는 `failed` 상태를 가진다 (스키마 v18). `POST /api/summaries`는 판정 가격을 hold하고 `judging` 줄을 저장한 뒤 새 `SummaryJudges`(`backend/app/coaching/summary_judging.py`)의 실행기에 판정을 넘기고 곧바로 답한다. 실행기가 `SummaryCoach.feedback`을 불러 줄을 채우고 hold를 정산하거나 돌려준다. 모든 상태 변경은 `RecordRepo`가 `records` 이벤트로 알리고, 화면은 그 이벤트로 다시 읽어 카드를 상태별로 그린다.

**Tech Stack:** FastAPI, SQLite (STRICT 테이블, `PRAGMA user_version`), pytest; React 19, TypeScript, vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-20-background-summary-feedback-design.md` (실행 전에 함께 읽는다).

## Global Constraints

- 브랜치 `feat/background-summary-feedback`. 끝나면 `main`에 `--ff-only`로 합치고 `scripts/bump-version patch`, 그리고 `git push --follow-tags origin main` (`CLAUDE.md`의 Versioning). 배포는 사용자가 말할 때만 한다.
- 심볼을 고치기 전에 GitNexus `impact`(upstream), 커밋 전에 `node .gitnexus/run.cjs detect-changes --scope all --repo .`. 인덱스가 낡았으면 먼저 `node .gitnexus/run.cjs analyze --index-only`.
- 커밋 메시지에 `Co-Authored-By` 없음. 제목과 본문만.
- 이벤트는 `RecordRepo`만 커밋 뒤에 보낸다. 라우트와 실행기는 보내지 않는다. 새 이벤트 이름은 없고 모두 `SessionChange.RECORDS`다.
- 정확한 문구:
  - 서버 재시작: `The server restarted before the feedback came back.`
  - 판정 실패: `feedback failed: <오류의 message 또는 str>` (지금 `failed("feedback", e)`의 꼴)
  - 409 다시 판정: `Only a summary whose feedback failed can be judged again.`
  - 409 지우기: `Only a summary whose feedback failed can be removed.`
  - 503: `summary coach is off: the summary-coach folder is missing` (지금 문구 그대로)
  - 판정 중 카드: `Reading your summary against the paragraph…`
  - 실패 카드 버튼: `Judge again`, `Remove`
  - 말한 사람: 내 것 `You`, 다른 사람 것 `speaker`, 모르면 `Someone`
  - Summary 탭: 제목 `Paragraphs summed up`, 판정 중 note `Waiting for feedback…`, 실패 note `No feedback: judge it again in the Article tab.`, label `<말한 사람> · <문단 첫 네 단어>…`
- 판정 실행기 동시 실행 수 4, 세션 생성 실행기와 따로.
- 가격은 바꾸지 않는다: `summary_voice` 5, `summary_feedback` 5.
- 테스트: `cd backend && uv run pytest -q`, `cd frontend && npx vitest run`, `npx tsc -b --noEmit`, `npm run lint`. 기준 수치는 Task 0에서 적는다. 테스트는 명령 하나로 따로 돌리고 결과의 `FAILED` 줄을 읽은 뒤에 커밋한다.

## Review Focus

1. Done 뒤, 판정이 끝나기 전에 다른 문단과 같은 문단의 버튼이 눌린다. (Task 3 `frees the paragraph as soon as the summary is sent, before any feedback`)
2. 판정이 도는 중 탭을 옮겨 `Paragraph`가 사라져도 POST의 결과를 버리지 않고, 사라진 뒤 POST가 실패하면 녹음 가격을 돌려준다. (Task 3 `still gives the voice back when the summary could not be sent after the page was left`)
3. 두 사람이 같은 실패 카드의 Judge again을 동시에 누르면 한 번만 판정하고, 다른 쪽은 409와 함께 hold를 돌려받는다. (Task 2 `judging again twice at once runs it once and gives the second price back`)
4. 판정 중 세션이 지워지면 실행기가 터지지 않고, 이미 돈 판정은 정산한다. (Task 2 `a summary whose session went while it was judged is paid for and dropped`)
5. 다른 사람의 Read aloud 회가 끝난 직후 요약 판정이 끝나 `records` 이벤트가 와도, 그 회의 표시가 옛 표시로 깜빡이지 않는다. 읽기 기록이 그대로면 `useReadingMarks`가 같은 배열을 유지한다. (Task 3 `keeps the same marks when the records come back with no new reading`)

---

### Task 0: 준비

- [ ] `git switch -c feat/background-summary-feedback` (main에서).
- [ ] `node .gitnexus/run.cjs analyze --index-only`.
- [ ] 기준 수치를 이 줄에 적는다: backend `uv run pytest -q` 통과 수, frontend `npx vitest run` 통과 수, `npm run lint` 경고 수.

### Task 1: 저장소: 상태와 말한 사람을 담는 summaries (v18)

**Files:**
- Modify: `backend/app/db/schema.py` (`VERSION`, summaries DDL, `upgrade`, 새 단계 함수)
- Modify: `backend/app/models.py` (`Summary`)
- Modify: `backend/app/db/records.py` (요약 메서드)
- Modify: `backend/app/api/records.py` (이 task에서는 기존 `POST /api/summaries`가 새 메서드로 계속 동작하게만)
- Test: `backend/tests/test_schema.py`, `backend/tests/test_store.py`, `backend/tests/test_changes.py`, `backend/tests/test_migrate.py`

**Interfaces:**
- Produces (`app.models`):
  ```python
  SummaryStatus = Literal["judging", "done", "failed"]
  class Summary(BaseModel):
      id: int; created_at: datetime; paragraph_id: int; user_text: str; seconds: float
      status: SummaryStatus = "done"
      feedback: SummaryFeedback | None = None
      error: str | None = None
      speaker: str | None = None   # 말한 사람의 username, 모르면 None
      mine: bool = False           # 조회한 사람이 말한 사람이면 True
  ```
- Produces (`RecordRepo`, `add_summary`는 없앤다):
  - `start_summary(paragraph_id: int, user_id: int | None, user_text: str, seconds: float) -> int` — `judging` 줄, 알림, 새 id.
  - `summary_to_judge(summary_id: int) -> tuple[str, str] | None` — `judging`인 줄의 (문단 텍스트, user_text). 아니면 None.
  - `finish_summary(summary_id: int, feedback: SummaryFeedback) -> bool` — `judging`인 줄만 `done`으로. 바뀌었으면 알림 후 True.
  - `fail_summary(summary_id: int, error: str) -> bool` — `judging`인 줄만 `failed`로.
  - `rejudge_summary(summary_id: int) -> bool` — `failed`인 줄만 `judging`으로, `error` NULL. 한 번의 UPDATE.
  - `remove_failed_summary(summary_id: int) -> bool` — `failed`인 줄만 지운다.
  - `fail_unfinished_summaries(error: str) -> None` — 모든 `judging`을 `failed`로. 알림 없음 (시작 시 전용).
  - `get_summary(summary_id: int, viewer_id: int) -> Summary | None`
  - `list_summaries(session_id: int, viewer_id: int) -> list[Summary]` — 만든 순서(id), 모든 상태.
  - 상태를 바꾸는 메서드는 `UPDATE/DELETE ... RETURNING paragraph_id`로 알릴 세션을 찾는다 (기존 `_announce(paragraph_id)`).

- [ ] **Step 1: impact** — `RecordRepo.add_summary`, `RecordRepo.list_summaries`, `Summary`, `schema.upgrade`.

- [ ] **Step 2: 실패하는 테스트**
  - `test_schema.py`: v17 꼴로 되돌리는 `as_v17(path)`를 더한다. summaries를 이름 바꿔 두고, 지금 `schema.py`의 summaries DDL(고치기 전의 것: `id`, `created_at`, `paragraph_id ... ON DELETE CASCADE`, `user_text`, `feedback TEXT NOT NULL`, `seconds REAL NOT NULL DEFAULT 0`, STRICT)과 `summaries_paragraph` 인덱스를 테스트 안에 문자열로 옮겨 새로 만들고, 행을 복사하고, 옛 테이블을 지우고, `PRAGMA user_version = 17`. 지금 `as_v16`은 현재 파일을 v17로 보고 시작하므로 맨 앞에서 `as_v17(path)`를 부르게 고친다.
  - `test_schema.py::test_v18_keeps_every_summary_as_judged_with_no_speaker_and_carries_the_id_counter_on`: v17 파일에 요약 두 줄을 넣고 두 번째(id 2)를 지운 뒤 열면 `list_summaries(sid, viewer_id=0)`이 한 줄, `(id, status, feedback, speaker, mine) == (1, "done", FEEDBACK, None, False)`, `start_summary(...)`의 새 id가 3, `user_version`이 18.
  - `test_schema.py::test_a_summary_is_done_exactly_when_it_has_feedback`: `status='done'`에 `feedback` NULL, `status='judging'`에 feedback 있음, 둘 다 `sqlite3.IntegrityError`.
  - `test_store.py`의 `test_readings_and_summaries_hang_off_a_paragraph_and_go_with_the_session`: `add_summary` 대신 `start_summary` + `finish_summary`, `list_summaries(session.id, viewer_id=...)`.
  - `test_store.py::test_a_summary_goes_from_judging_to_done_or_failed_and_only_a_failed_one_comes_back_or_goes`:
    - `start_summary(p, mina.id, "said", 5)` → `get_summary(id, mina.id)`는 `status == "judging"`, `feedback is None`, `speaker == mina.username`, `mine is True`; `get_summary(id, other.id).mine is False`; `summary_to_judge(id) == (문단 텍스트, "said")`.
    - `rejudge_summary(id) is False`, `remove_failed_summary(id) is False` (judging).
    - `fail_summary(id, "feedback failed: down") is True` → `status == "failed"`, `error == "feedback failed: down"`; `summary_to_judge(id) is None`; `finish_summary(id, FEEDBACK) is False`.
    - `rejudge_summary(id) is True` → `judging`, `error is None`; 한 번 더 `rejudge_summary(id) is False`.
    - `finish_summary(id, FEEDBACK) is True` → `done`, `feedback == FEEDBACK`.
    - 두 번째 요약을 `fail_summary` 후 `remove_failed_summary` → True, 목록에서 빠짐.
    - `start_summary(p, None, ...)` 줄은 `speaker is None`.
  - `test_store.py::test_summaries_left_judging_fail_when_the_app_starts_again`: `judging` 하나, `done` 하나 → `fail_unfinished_summaries("The server restarted before the feedback came back.")` → 앞의 것만 `failed`와 그 문구.
  - `test_changes.py`의 매개변수: `add_summary` 줄을 `start_summary(p, None, "u", 1.0)` → `{"records"}`로 바꾸고, 미리 만든 `judging` 줄에 대한 `finish_summary`, `fail_summary`, 실패 줄에 대한 `rejudge_summary`, `remove_failed_summary`도 각각 `{"records"}`. 바뀐 것이 없는 호출(예: `done` 줄에 `fail_summary`)은 아무것도 알리지 않음을 한 줄 더한다.
  - `test_migrate.py:216`: `list_summaries(11, viewer_id=0)`.

- [ ] **Step 3: 실패 확인** — `cd backend && uv run pytest -q tests/test_schema.py tests/test_store.py tests/test_changes.py tests/test_migrate.py`. Expected: 새 메서드와 v18이 없어 FAIL.

- [ ] **Step 4: 구현**
  - `schema.py`: `VERSION = 18`. SCHEMA의 summaries를 spec의 DDL로 (`user_id INTEGER REFERENCES users(id) ON DELETE SET NULL`, `status ... DEFAULT 'done' CHECK (...)`, `feedback TEXT`, `error TEXT`, `CHECK ((status = 'done') = (feedback IS NOT NULL))`)와 인덱스 `summaries_paragraph`. 이 DDL을 `SUMMARIES` 상수로 빼서 `SCHEMA`와 v18 단계가 함께 쓴다.
  - `upgrade`: `if version < 18: _summaries_with_status(conn)`. 함수는 `_examples_of_words`를 따른다: id 카운터 보관 → `ALTER TABLE summaries RENAME TO summaries_v17` → `DROP INDEX IF EXISTS summaries_paragraph` → `SUMMARIES` 실행 → `INSERT INTO summaries (id, created_at, paragraph_id, user_text, status, feedback, seconds) SELECT id, created_at, paragraph_id, user_text, 'done', feedback, seconds FROM summaries_v17` → `DROP TABLE summaries_v17` → `sqlite_sequence` 정리와 카운터 복원 → `PRAGMA user_version = 18`.
  - `records.py`: 위 Interfaces. 조회는 `LEFT JOIN users u ON u.id = s.user_id`로 `u.username AS speaker`, `mine`은 `s.user_id = viewer_id`. `feedback`은 NULL이면 None.
  - `api/records.py`의 기존 `add_summary` 라우트는 이 task에서만 `start_summary(..., me.id, ...)` 뒤 `finish_summary(id, body.feedback)`, 응답은 `get_summary(id, me.id)`. `list_summaries` 라우트는 `viewer_id=me.id`. Task 2가 둘 다 갈아 끼운다.

- [ ] **Step 5: 통과 확인** — `cd backend && uv run pytest -q`. Expected: 기준 + 새 테스트 모두 통과.

- [ ] **Step 6: 커밋** — detect-changes 후 `git commit -m "feat: a summary keeps who said it and whether its feedback is in, failed or still coming (schema v18)"`.

### Task 2: 서버가 요약을 뒤에서 판정한다

**Files:**
- Create: `backend/app/coaching/summary_judging.py`
- Modify: `backend/app/main.py` (`create_app`), `backend/app/api/deps.py` (`Judges` 의존성), `backend/app/api/records.py` (세 쓰기 경로), `backend/app/api/schemas.py` (`SummaryRequest`, `SummaryFeedbackRequest` 삭제), `backend/app/api/coaches.py` (`POST /api/summary/feedback` 삭제)
- Test: `backend/tests/test_summary_feedback.py`(다시 씀), `backend/tests/test_credits.py`, `backend/tests/test_session_access.py`

**Interfaces:**
- Consumes: Task 1의 `RecordRepo` 메서드들. `CreditRepo.settle(hold: int | None)`, `CreditRepo.release(hold: int | None)`. `app.generation.jobs.Executor` (Protocol, `submit(fn, /, *args)`).
- Produces:
  ```python
  # backend/app/coaching/summary_judging.py
  RESTARTED = "The server restarted before the feedback came back."
  class SummaryJudges:
      def __init__(self, records: RecordRepo, credits: CreditRepo, executor: Executor) -> None
      def judge(self, summary_id: int, coach: SummaryCoach, hold: int | None) -> None  # 실행기에 넘기고 바로 돌아온다
  ```
  ```python
  # backend/app/main.py
  def create_app(db, services, executor=None, rebuild=None, env=None, image_dir=None, catalog=None,
                 judges: Executor | None = None) -> FastAPI
  ```
  `judges`가 없으면 `ThreadPoolExecutor(max_workers=4, thread_name_prefix="summary-judge")`. `app.state.judges = SummaryJudges(db.records, db.credits, ...)`. `release_abandoned()` 바로 다음 줄에서 `db.records.fail_unfinished_summaries(RESTARTED)`.
- API (spec의 표 그대로): `POST /api/summaries` 201, `POST /api/summaries/{summary_id}/judge` 200, `DELETE /api/summaries/{summary_id}` 204. 요청 본문 `SummaryRequest {paragraph_id: int, user_text: str (빈칸 불가), seconds: float = 0}`.

- [ ] **Step 1: impact** — `create_app`, `summary_feedback` 라우트, `SummaryRequest`, `add_summary` 라우트.

- [ ] **Step 2: 실패하는 테스트** (`test_summary_feedback.py`를 다시 쓴다. 기존 `FakeCli`, `AGENT_DIR`, `PARAGRAPH`, `ANSWER`는 둔다. 세션의 문단 텍스트를 프롬프트에서 확인하므로 `PARAGRAPH` 대신 세션에서 읽은 텍스트로 단언한다.)
  - `test_a_spoken_summary_is_judged_on_the_server_and_kept_with_who_said_it`: `create_app(..., judges=InlineExecutor())`. `POST /api/summaries {paragraph_id, user_text: said, seconds: 12}` → 201, 본문 `status == "done"`, `feedback == ANSWER`, `mine is True`, `speaker`는 admin의 username. 프롬프트에 그 문단 텍스트와 `said`가 있고 `"{{"`가 없다. `GET /api/summaries`에 같은 줄. `paragraph_id: 999` → 404. `user_text: " "` → 422. 세션 삭제 뒤 GET → 404.
  - `test_the_answer_comes_before_the_feedback_and_the_session_hears_both`: `judges=HeldExecutor()`(`tests/test_api.py`). POST → 201, `status == "judging"`, `feedback is None`; `db.changes`를 `Recorder`로 바꿔 `records`가 한 번; `held.release()` 뒤 GET이 `done`이고 `records`가 한 번 더.
  - `test_a_failed_judgment_keeps_the_summary_to_judge_again_or_remove`: coach가 `GenerationError("down")`를 던진다 → 줄은 `failed`, `error == "feedback failed: down"`. coach를 성공하는 것으로 바꾸고(`app.state.services = Services(..., summary_coach=...)`) `POST /api/summaries/{id}/judge` → 200 `done`. `done` 줄에 다시 judge → 409와 정확한 문구, `DELETE` → 409와 정확한 문구. 새로 실패시킨 줄은 `DELETE` → 204, 목록에서 빠짐. 없는 id → 404.
  - `test_judging_again_twice_at_once_runs_it_once_and_gives_the_second_price_back`: `HeldExecutor`로 실패 줄을 만든 뒤, 크레딧 있는 사용자가 `/judge`를 두 번 → 첫째 200, 둘째 409; `held.release()` 뒤 잔액은 판정 한 번 값(5)만 빠짐.
  - `test_a_summary_whose_session_went_while_it_was_judged_is_paid_for_and_dropped`: `HeldExecutor`로 POST, 세션 삭제, `held.release()` → 예외 없음, 사용자 잔액에서 5가 빠지고 hold가 남지 않음.
  - `test_a_restart_turns_a_summary_still_judging_into_a_failure`: `HeldExecutor`로 POST(release하지 않음) → 같은 DB로 `create_app` 다시 → GET이 `failed`와 `RESTARTED`.
  - `test_the_summary_round_is_503_without_a_voice_key`: `/api/summary/sessions` 503은 그대로, `POST /api/summaries` 503(coach 없음, 문단은 있는 세션), `/api/summary/feedback`은 404 또는 405 (경로가 없다).
  - `test_credits.py`: 매개변수 표에서 `/api/summary/feedback` 줄을 지운다. `paid_world`의 `create_app`에 `judges=InlineExecutor()`. `paid_world`에 mina의 세션 문단을 만드는 도우미 `a_paragraph_of(db, user) -> int`(`db.sessions.create(sample_draft(), [], created_by=user.id)`의 첫 문단)를 더한다. 그 위에서:
    - `test_a_summary_judgment_costs_5_and_then_refuses`: POST 201 → 마지막 기록 `(-5, "summary_feedback", None)` → 다시 POST 402 (줄은 하나만 남는다).
    - `test_an_error_no_route_expects_takes_nothing_either`의 summary 부분: `CrashingCoach`면 POST는 201, 줄은 `failed`, 잔액 그대로.
    - `test_a_summary_coach_that_fails_takes_nothing`: POST 201, `failed`, 잔액 25 그대로.
    - `test_a_whole_summarize_round_costs_10`: `/api/summary/sessions` + `POST /api/summaries` → 잔액 0.
  - `test_session_access.py::test_only_people_in_the_session_can_judge_again_or_remove_a_failed_summary`: id가 필요해 표 대신 따로 쓴다. `world.db.records.start_summary(그 세션의 첫 문단, creator.id, "said", 1)` 뒤 `fail_summary(id, "feedback failed: down")`로 실패 줄을 만든다. newcomer의 `POST /api/summaries/{id}/judge`와 `DELETE`는 404, sharee의 `DELETE`는 204.

- [ ] **Step 3: 실패 확인** — `cd backend && uv run pytest -q tests/test_summary_feedback.py tests/test_credits.py tests/test_session_access.py`.

- [ ] **Step 4: 구현**
  - `SummaryJudges._judge(summary_id, coach, hold)`: `summary_to_judge`가 None이면 hold를 돌려주고 끝 (판정 전에 줄이 사라짐). 판정 중 모든 `Exception`은 로그(`log.exception`) 후 `fail_summary(id, f"feedback failed: {getattr(e, 'message', e)}")`와 hold 반환. 성공하면 `finish_summary`; 그 결과가 False(줄이 사라짐)여도 hold는 정산. 장부 호출은 `api/deps._quietly`처럼 `sqlite3.Error`를 로그로만 남긴다 (실행기 스레드에서 예외가 사라지지 않게).
  - `POST /api/summaries`: `require_paragraph` → coach 없으면 503 → `held_or_402(db, me, "summary_feedback")` → `start_summary(..., me.id, ...)` (예외면 hold 반환 후 다시 던짐) → `judges.judge(id, coach, hold)` → `get_summary(id, me.id)`.
  - `POST /api/summaries/{id}/judge`: `get_summary(id, me.id)` 없으면 404 → `require_paragraph(summary.paragraph_id)` → 503 → hold → `rejudge_summary`가 False면 hold 반환과 409 → `judges.judge` → `get_summary`.
  - `DELETE /api/summaries/{id}`: 404 → `require_paragraph` → `remove_failed_summary`가 False면 409 → 204.
  - 서비스는 요청마다 `Svc`에서 읽는다 (설정이 바뀌면 `app.state.services`가 바뀐다).
  - `coaches.py`의 `summary_feedback` 라우트와 쓰지 않게 된 import, `schemas.SummaryFeedbackRequest`를 지운다.

- [ ] **Step 5: 통과 확인** — `cd backend && uv run pytest -q`.

- [ ] **Step 6: 커밋** — `git commit -m "feat: the server judges a summary in the background and keeps the summary when the judgment fails"`.

### Task 3: Article 탭: Done 뒤 바로 풀리고, 카드가 상태와 말한 사람을 보인다

**Files:**
- Modify: `frontend/src/types.ts` (`Summary`, `SummaryStatus`), `frontend/src/api.ts`, `frontend/src/components/Summarize.tsx`, `frontend/src/components/Summarize.css`, `frontend/src/lib/useSummaries.ts`, `frontend/src/lib/useReadingMarks.ts`
- Test: `frontend/src/components/Summarize.test.tsx`, `frontend/src/components/Paragraph.test.tsx`, `frontend/src/lib/useReadingMarks.test.ts` (없으면 만든다)

**Interfaces:**
- Consumes: Task 2의 API.
- Produces:
  ```ts
  export type SummaryStatus = 'judging' | 'done' | 'failed'
  export interface Summary {
    id: number; created_at: string; paragraph_id: number; user_text: string; seconds: number
    status: SummaryStatus
    feedback: SummaryFeedback | null
    error: string | null
    speaker: string | null
    mine: boolean
  }
  // api
  addSummary: (summary: { paragraph_id: number; user_text: string; seconds: number }) => Promise<Summary>
  judgeSummaryAgain: (id: number) => Promise<Summary>   // POST /api/summaries/{id}/judge
  removeSummary: (id: number) => Promise<void>          // DELETE /api/summaries/{id}
  // summaryFeedback은 지운다
  ```
  `speakerOf(summary: Summary): string` — `mine`이면 `'You'`, 아니면 `speaker ?? 'Someone'`. `Summarize.tsx`에서 export하고 Task 4가 쓴다.

- [ ] **Step 1: impact** — `useSummary`, `SummaryPanel`, `Feedback`, `useSummaries`, `useReadingMarks`.

- [ ] **Step 2: 실패하는 테스트** (`Summarize.test.tsx`; api mock에 `judgeSummaryAgain`, `removeSummary`를 더하고 `summaryFeedback`을 지운다. 픽스처 `Summary`에는 `status`, `feedback`, `error`, `speaker`, `mine`을 채운다.)
  - 첫 테스트를 `frees the paragraph as soon as the summary is sent, before any feedback`으로 바꾼다: `addSummary`가 `{..., status: 'judging', feedback: null, mine: true}`로 resolve. Done → `session.closed` 뒤 `addSummary`가 `{ paragraph_id: 4, user_text: said, seconds: 20 }`로 한 번, `onSummary`가 그 줄로, `onEnd` 한 번, 슬립이 닫히고, `Read aloud` 버튼이 enabled. `giveBack`은 불리지 않는다.
  - `gives the voice back when the summary could not be sent`: `addSummary` reject(`Not enough credits: …`) → 슬립에 그 문구, `giveBack` 한 번, `onEnd` 안 불림.
  - `still gives the voice back when the summary could not be sent after the page was left`: `addSummary`를 붙잡아 둔 promise로, Done과 `session.closed` 뒤 `unmount()`, 그다음 reject → `giveBack` 한 번, 오류 없이 끝남. 같은 꼴로 resolve하는 경우에는 `addSummary`가 불렸고 `giveBack`이 안 불림 (요청을 버리지 않는다).
  - `gives the voice back when the page is left before the summary is sent`: 녹음 중(`listening`) `unmount()` → `giveBack` 한 번, `addSummary` 안 불림.
  - `shows a summary being judged under the paragraph`: `summaries=[{status:'judging', feedback:null, mine:true, ...}]` → 카드에 `You`, said, `Reading your summary against the paragraph…`; `Model answer` 없음; `Summarize again`과 `Read aloud` enabled.
  - `shows a failed judgment with Judge again and Remove`: `status:'failed', error:'feedback failed: down'` → 문구가 보이고, `Judge again` 클릭 → `api.judgeSummaryAgain(7)`, `Remove` 클릭 → `api.removeSummary(7)`. `judgeSummaryAgain`이 reject하면 그 문구가 카드 안에 보인다.
  - `names who said each summary`: `mine:false, speaker:'mina'` → `mina`; `mine:false, speaker:null` → `Someone`.
  - 기존 `shows a kept summary in the card it was judged in…`는 `status:'done', mine:true` 픽스처로 그대로 통과해야 한다.
  - `Paragraph.test.tsx`: 크레딧이 모자랄 때(`summary_feedback`을 못 내는 잔액) 실패 카드의 `Judge again`이 disabled이고 이유를 title로 보인다. 기존 `short of credits…` 테스트의 `useCredits` 설정을 따른다.
  - `useReadingMarks.test.ts::keeps the same marks when the records come back with no new reading`: `useSessionResource`를 mock해 같은 내용의 새 배열을 두 번 넘기면 `marks.get(p)`의 참조가 같다. 새 reading이 오면 바뀐다.

- [ ] **Step 3: 실패 확인** — `cd frontend && npx vitest run src/components/Summarize.test.tsx src/components/Paragraph.test.tsx src/lib/useReadingMarks.test.ts`.

- [ ] **Step 4: 구현**
  - `useSummary`: `closed`이고 말한 문장이 있으면 `api.addSummary`. 성공 → 마운트돼 있으면 `onKept`, `dismiss()`. 실패 → 언제나 `round.giveBack()`, 마운트돼 있으면 `setFailure`. 요청 자체는 effect 정리로 버리지 않는다 (마운트 여부는 ref로 본다). 언마운트 시 아직 보내지 않은 회가 있으면 `round.giveBack()` (`useLiveRound`의 정리는 연결을 dispose할 뿐 `connRef`를 비우지 않고, `GeminiRound.giveBack`은 hold id로 HTTP를 부르므로 dispose 뒤에도 동작한다).
  - 슬립의 `writing` hint는 `Sending your summary…`로 바꾼다 (이제 저장 요청 동안만이다).
  - `SummaryPanel`: 카드 `<dt>`는 `speakerOf(s)`. `judging`이면 hint 문구, `failed`면 `slip-error`로 `error`와 버튼 둘, `done`이면 `Feedback`. 실패 카드 버튼은 작은 하위 컴포넌트(`FailedJudgment`)에 두고 `usePrice('summary_feedback')`로 가격과 `short`를 보인다. 요청 오류는 그 컴포넌트의 state.
  - `useSummaries.add`: 같은 id가 이미 있으면 그대로 둔다 (이벤트로 다시 읽은 목록이 먼저 올 수 있다).
  - `useReadingMarks`: 새로 읽은 목록이 지금 목록과 id와 corrections가 같으면 지금 배열을 유지한다 (`setReadings((now) => (sameReadings(now, next) ? now : next))`).

- [ ] **Step 5: 통과 확인** — `npx vitest run`, `npx tsc -b --noEmit`, `npm run lint` (경고 수가 기준보다 늘지 않음).

- [ ] **Step 6: 커밋** — `git commit -m "feat: Done frees the paragraph at once and each summary card shows who said it and where its feedback is"`.

### Task 4: Summary 탭이 상태와 말한 사람을 보인다

**Files:** Modify `frontend/src/components/SummaryTab.tsx`; Test `frontend/src/components/SummaryTab.test.tsx`.

**Interfaces:** Consumes `speakerOf` (Task 3), `Summary` (Task 3).

- [ ] **Step 1: impact** — `SummaryTab`.

- [ ] **Step 2: 실패하는 테스트** (`SummaryTab.test.tsx`)
  - `names each summary by the opening words of the paragraph it sums up` → `names each summary by who said it and the opening words of its paragraph`: 픽스처 `mine:true` → `You · A modest twin delivers…`; `mine:false, speaker:'mina'` → `mina · Upkeep is what actually…`.
  - `says where the feedback of each summary is`: `judging` → note `Waiting for feedback…`, `failed` → `No feedback: judge it again in the Article tab.`, `done` → `feedback.summary`.
  - `counts each section`(기존)과 새 제목 `Paragraphs summed up`.

- [ ] **Step 3: 실패 확인** — `npx vitest run src/components/SummaryTab.test.tsx`.

- [ ] **Step 4: 구현** — label과 note만 바꾼다. `SummaryCard`는 바꾸지 않는다.

- [ ] **Step 5: 통과 확인** — `npx vitest run`, `npx tsc -b --noEmit`, `npm run lint`.

- [ ] **Step 6: 커밋** — `git commit -m "feat: the Summary tab shows who said each summary and whether its feedback is in"`.

### Task 5: 문서와 마무리

- [ ] `docs/superpowers/specs/2026-11-01-credits-design.md` 가격표의 "Summarize 피드백" 행 경로를 `POST /api/summaries`, `POST /api/summaries/{id}/judge`로 고친다. 같은 문서 안에 `/api/summary/feedback`를 설명하는 다른 줄이 있으면 함께 고친다.
- [ ] `agents/summary-coach/AGENT.md`와 `README.md`에서 판정을 브라우저가 부른다고 적은 곳을 서버 기준으로 고친다 (없으면 그대로).
- [ ] spec 상태를 "구현됨 (날짜)"로, 구현 계획 경로를 적는다. 커밋 `docs: the background summary feedback design is implemented`.
- [ ] 전체 테스트를 각각 돌려 기준과 비교한다: backend `uv run pytest -q`, frontend `npx vitest run`, `npx tsc -b --noEmit`, `npm run lint`.
- [ ] 새 서브에이전트(가장 강한 모델)로 브랜치 전체 리뷰를 한 번 한다 (`git diff main...HEAD`, spec과 이 계획을 함께 준다). 찾은 결함은 고치고 테스트를 다시 돌린다.
- [ ] `detect-changes --scope compare --base-ref main` 확인 → `git switch main && git merge --ff-only feat/background-summary-feedback` → `scripts/bump-version patch` → `git push --follow-tags origin main`.
- [ ] 배포는 사용자가 말할 때만: 진행 중인 생성이 없는지 확인(`docker compose logs backend --since 10m | grep -c 'POST /api/sessions HTTP'`, `GET /api/jobs`)한 뒤 `docker compose up -d --build`. 재시작하면 판정 중인 요약은 실패로 바뀌므로 판정 중인 줄도 없는지 본다.
