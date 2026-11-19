# 한국어로 해 보기: 대화문 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 태스크를 이 세션에서 직접 실행하고, 끝에 새 서브에이전트 리뷰를 한 번만 한다 (사용자가 정한 방식). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expression 카드의 "한국어로 해 보기"에서 한 문장 예문과 A/B 두 줄 대화문을 카드마다 토글로 고르고, 대화 카드는 한 번 누르면 두 줄이 모두 영어 모범 답안으로 바뀐다. 대화문은 커밋된 Python 모듈이 Claude로 채운다.

**Architecture:** 백엔드는 `expressions.korean_dialogue` 열(schema v17)을 더하고, `Expression.korean_dialogue`로 세션 내용과 corpus 읽기 경로에 실어 보낸다. `app.generation.korean_dialogues`가 대화문 없는 표현을 묶어 `Claude.run`으로 보내고 `--apply`일 때 `ExpressionRepo.set_dialogue`로 쓴다. 프런트엔드는 `KoreanPractice`가 presence 공유 키 `mode:{id}`로 모드를 고르고, 새 `KoreanDialogue` 카드가 `dialogue:{id}`로 뒤집기를 공유한다.

**Tech Stack:** Python 3, FastAPI, pydantic, SQLite, pytest, claude_agent_sdk, React 19, TypeScript, vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-19-korean-dialogue-design.md`

## Global Constraints

- 브랜치 `feat/korean-dialogue`에서 작업한다 (`git switch -c feat/korean-dialogue`, spec과 이 계획이 커밋된 `main` 위에서). `main`에는 `--ff-only`로 합치고, 그 뒤 `scripts/bump-version patch`만 쓴다. minor나 major는 올리지 않는다. push와 배포는 사용자가 말할 때만 한다.
- 심볼을 고치기 전에 GitNexus `impact`(`node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .` 또는 MCP `impact`), 커밋 전에 `node .gitnexus/run.cjs detect-changes --scope all --repo .`. HIGH 이상은 보고한다. `risk: UNKNOWN`은 텍스트 검색으로 확인한다. 시작할 때 `node .gitnexus/run.cjs analyze --index-only`.
- 커밋 메시지는 제목과 본문뿐이다. `Co-Authored-By`를 넣지 않는다.
- 새 Python, npm 의존성이 없다. 새 셸 스크립트를 만들지 않는다.
- 이벤트를 새로 publish하지 않는다. `set_dialogue`도 publish하지 않는다 (spec 결정 6). 브라우저에서 새 `EventSource`나 소켓을 열지 않는다. 공유 상태는 `useSharedView`만 쓴다.
- presence 키는 `KEY = re.compile(r"[a-z]+(:[a-z0-9]+)*")`(`backend/app/live/presence.py:26`)에 맞아야 한다. 하이픈 금지. 이 기능의 키는 정확히 `mode:{id}`(값 `'dialogue' | 'solo'`)와 `dialogue:{id}`(값 boolean)다. 한 문장 카드는 기존 `example:{id}`를 그대로 쓴다.
- 코드, 주석, 테스트 이름은 영어다. 함수 하나는 한 추상화 수준만 말한다 (`/home/humanoid/CLAUDE.md`).
- 화면 문구는 아래 그대로 쓴다.
  - 라벨: "한국어로 해 보기" (기존).
  - 토글 그룹 `aria-label`: "연습 방식". 버튼: "한 문장", "대화".
  - 화자 표시: "A", "B".
  - 카드 안내: 한국어 면 "영어로 어떻게 말할까요?", 영어 면 "모범 답안 · 다르게 말해도 표현을 넣었으면 충분해요" (기존 두 문구, 두 카드가 같이 쓴다).
  - 탭 안내(`tab-brief`): "Read the examples aloud, then say the Korean in English, each of you a sentence or one side of the dialogue, before you tap it for the model answer."
- 테스트: 백엔드 `cd backend && .venv/bin/pytest -q`, 프런트 `cd frontend && npx vitest run`, `npx tsc -b --noEmit`, `npm run lint`. 시작 기준선(2026-11-19, `8ec2800`)은 백엔드 671 passed (약 6분), 프런트 54 files / 531 tests passed다.
- 테스트는 따로 돌리고 결과를 읽은 뒤에 커밋한다. `;`로 잇거나 `tail -1`로 자르지 않는다. 실패 이름은 `grep -E "FAILED|passed|failed"`로 남긴다.
- 운영 서버(이 호스트)에서 Create session을 누르지 않는다. 비밀값을 출력하지 않는다.

## 계획에서 정한 것 (spec이 빌더에게 맡긴 것)

- `KoreanLine`은 `KoreanExample`과 따로 둔다 (spec 그대로). 프런트 타입도 `KoreanLine`.
- 생성 모듈의 프롬프트는 파일이 아니라 모듈 상수 `PROMPT`다. 관리용 일회성 도구라 agent 폴더를 만들지 않는다. 표현 목록은 `json.dumps(..., ensure_ascii=False, indent=2)`로 프롬프트 끝에 붙인다 (테스트의 가짜 Claude가 `"id": N`을 읽는다).
- 기본값: 묶음 20, 모델 `opus`, effort `medium`, `timeout_s=300`.
- 줄 검사: 줄이 정확히 2개이고, 네 문자열(`korean`, `english` 두 쌍)이 모두 공백 아닌 내용이 있어야 쓴다. 요청하지 않은 id와 같은 id의 두 번째 답은 버린다.
- 기존 `KoreanExample` 컴포넌트는 `KoreanSentence`로 이름을 바꾼다. 둘을 고르는 `KoreanPractice`가 라벨 줄과 토글을 그린다.
- 토글은 `role="group"` 안의 `aria-pressed` 버튼 두 개다.

## Review Focus

1. Claude가 한 줄을 빈 문자열이나 공백으로 채움 → 그 표현은 쓰지 않고 건너뛴 수에 든다. (Task 2 `test_write_drops_blank_lines`)
2. Claude가 요청하지 않은 id나 같은 id를 두 번 돌려줌 → 요청한 id의 첫 답만 쓴다. (Task 2 `test_write_keeps_only_the_first_answer_for_ids_it_asked_for`)
3. 전부 채운 뒤 다시 실행 → Claude를 부르지 않고 0개, 종료 코드 0. (Task 2 `test_nothing_left_asks_claude_nothing`)
4. 나중에 들어온 표현처럼 대화문만 있고 한 문장이 없음 → 토글 없이 대화만. (Task 3 `shows only the dialogue, with no toggle, when the expression has no one sentence`)
5. 표현이 안 든 줄 → 영어 면에서 형광펜 없이 글자 그대로, 표현이 든 줄만 칠함. (Task 3 `flips both lines of the dialogue to English at once and back`)

---

### Task 0: 시작 준비

- [ ] **Step 1: 브랜치와 색인**

```bash
git switch -c feat/korean-dialogue
node .gitnexus/run.cjs analyze --index-only
```

- [ ] **Step 2: 기준선 확인**

Run: `cd backend && .venv/bin/pytest -q 2>&1 | grep -E "FAILED|passed|failed"`
Expected: 671 passed, 실패 없음. 다르면 시작 전에 원인을 사용자에게 알린다.

---

### Task 1: corpus에 대화문 열 (schema v17)

**Files:**
- Modify: `backend/app/db/schema.py` (`VERSION`, 새 상수, `SCHEMA` 끝, `upgrade`)
- Modify: `backend/app/models.py` (`KoreanLine`, `Expression.korean_dialogue`)
- Modify: `backend/app/db/expressions.py` (`COLUMNS`, `expression_from`, `ExpressionRepo.without_dialogue`, `ExpressionRepo.set_dialogue`)
- Modify: `docs/superpowers/specs/2026-10-25-sqlite-schema-redesign-design.md` (81줄 스키마 블록, 144줄 버전 문단)
- Test: `backend/tests/test_schema.py`, `backend/tests/test_expressions.py`

**Interfaces:**
- Produces:
  - `app.models.KoreanLine(BaseModel)`: `korean: str`, `english: str`.
  - `Expression.korean_dialogue: list[KoreanLine] | None = None` (A 줄, B 줄 순서).
  - `ExpressionRepo.without_dialogue(self, limit: int | None = None) -> list[Expression]`: `korean_dialogue IS NULL`, `ORDER BY e.id`, `limit`이 None이면 전부.
  - `ExpressionRepo.set_dialogue(self, expression_id: int, lines: list[KoreanLine]) -> None`: `json.dumps([l.model_dump() for l in lines], ensure_ascii=False)`로 쓴다. publish 없음.
  - `schema.VERSION == 17`.

- [ ] **Step 1: impact**

`expression_from`, `Expression`, `upgrade`에 GitNexus `impact`를 돌리고 결과를 적는다. `COLUMNS`는 `app/db/sessions.py:12`(`EXPRESSION_COLUMNS`)와 `expressions.py`의 `get`, `list_all`, `pick`이 쓴다.

- [ ] **Step 2: 실패하는 스키마 테스트**

`backend/tests/test_schema.py`에서 옛 파일 도우미 사슬 맨 앞에 `as_v16`을 더하고, `as_v15`가 먼저 그것을 부르게 한다. 그러지 않으면 v15 이하로 되돌린 파일이 v17 단계에서 같은 열을 또 더하다 실패한다.

```python
def as_v16(path) -> None:
    """Rewrites a current file the way v16 kept it: expressions with no dialogue column."""
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("ALTER TABLE expressions DROP COLUMN korean_dialogue")
        conn.execute("PRAGMA user_version = 16")
    conn.close()


def as_v15(path) -> None:
    """Rewrites a current file the way v15 kept it: accounts with no username."""
    as_v16(path)
    ...  # 기존 본문 그대로


def test_a_v16_file_gains_an_empty_korean_dialogue_on_each_expression(tmp_path):
    path = tmp_path / "s.db"
    [expression] = seed_expressions(Database(path), 1)
    as_v16(path)
    db = Database(path)
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == schema.VERSION == 17
    assert list(tmp_path.glob("s.db.bak-v16-????-??-??"))
    assert db.expressions.get(expression).korean_dialogue is None
```

- [ ] **Step 3: 실패하는 저장소 테스트**

`backend/tests/test_expressions.py` (import에 `json`, `KoreanLine` 추가):

```python
DIALOGUE = [
    KoreanLine(korean="아까 그분 이름이 뭐였더라?", english="What was his name again?"),
    KoreanLine(korean="미안, 나도 이름을 못 들었어.", english="Sorry, I didn't catch his name either."),
]


def test_a_korean_dialogue_comes_with_its_expression_wherever_it_is_read(store):
    a, b = seed_expressions(store, 2)
    store.expressions.set_dialogue(a, DIALOGUE)
    session = store.sessions.create(sample_draft(), [a, b]).id
    assert [e.korean_dialogue for e in store.sessions.get(session).content.expressions] == [DIALOGUE, None]
    assert store.expressions.get(a).korean_dialogue == DIALOGUE
    assert [e.korean_dialogue for e in store.expressions.list_all()] == [DIALOGUE, None]


def test_a_dialogue_is_kept_as_readable_korean_in_order(store):
    [a] = seed_expressions(store, 1)
    store.expressions.set_dialogue(a, DIALOGUE)
    with store.connect() as conn:
        raw = conn.execute("SELECT korean_dialogue FROM expressions WHERE id = ?", (a,)).fetchone()[0]
    assert json.loads(raw) == [line.model_dump() for line in DIALOGUE]
    assert "이름" in raw


def test_without_dialogue_lists_the_empty_ones_by_id_up_to_the_limit(store):
    a, b, c = seed_expressions(store, 3)
    store.expressions.set_dialogue(b, DIALOGUE)
    assert [e.id for e in store.expressions.without_dialogue()] == [a, c]
    assert [e.id for e in store.expressions.without_dialogue(1)] == [a]


def test_importing_an_expression_again_keeps_its_dialogue(store):
    [a] = seed_expressions(store, 1)
    store.expressions.set_dialogue(a, DIALOGUE)
    assert store.expressions.add("alpha phrase", "new meaning", [], ["e"], "n", None, "s") == a
    assert store.expressions.get(a).korean_dialogue == DIALOGUE
```

- [ ] **Step 4: 실패 확인**

Run: `cd backend && .venv/bin/pytest -q tests/test_schema.py tests/test_expressions.py 2>&1 | grep -E "FAILED|passed|failed"`
Expected: 새 테스트들이 FAIL (`no such column: korean_dialogue`, `ImportError: KoreanLine` 등).

- [ ] **Step 5: 구현**

- `schema.py`: v6 `KOREAN_EXAMPLES` 바로 아래 꼴로 상수를 둔다.
  ```python
  # Added in v17: a two-line dialogue the pair say in English, A then B, as a JSON array
  # [{"korean", "english"}, {"korean", "english"}]; NULL until the corpus has one.
  KOREAN_DIALOGUES = """
  ALTER TABLE expressions ADD COLUMN korean_dialogue TEXT;
  """
  ```
  `SCHEMA`의 연결 끝(`USERNAME_INDEX` 뒤)에 `+ KOREAN_DIALOGUES`, `VERSION = 17`, `upgrade` 끝에 `if version < 17: _run(conn, KOREAN_DIALOGUES); conn.execute("PRAGMA user_version = 17")`.
- `models.py`: `KoreanExample` 아래에 `KoreanLine`(docstring: "One speaker's line: Korean to say in English, then `english` as the model answer."), `Expression.korean_example` 아래에 `korean_dialogue`(docstring: "None until the corpus has one. A's line, then B's; at least one says the expression.").
- `expressions.py`: `COLUMNS` 끝에 `, e.korean_dialogue`, `expression_from`에 `korean_dialogue=row["korean_dialogue"] and json.loads(row["korean_dialogue"])`, 위 Interfaces의 두 메서드.

- [ ] **Step 6: 통과 확인**

Run: `cd backend && .venv/bin/pytest -q tests/test_schema.py tests/test_expressions.py tests/test_migrate.py tests/test_store.py 2>&1 | grep -E "FAILED|passed|failed"`
Expected: 실패 없음.

- [ ] **Step 7: 스키마 문서**

`2026-10-25-sqlite-schema-redesign-design.md`:
- 81줄 `korean_example` 아래에 `    korean_dialogue TEXT                         -- JSON [{korean, english}, {korean, english}]: A, B 두 줄 대화문. 적어도 한 줄에 표현. NULL이면 아직 없음 (v17)`.
- 144줄 버전 문단 끝에 "v17(2026-11-19)에 `expressions.korean_dialogue`. 열 하나 추가라 백업(`.bak-v16-…`) 뒤 `ALTER TABLE`만 한다."

- [ ] **Step 8: 커밋**

`detect-changes`를 돌린 뒤:

```bash
git add backend/app/db/schema.py backend/app/models.py backend/app/db/expressions.py backend/tests/test_schema.py backend/tests/test_expressions.py docs/superpowers/specs/2026-10-25-sqlite-schema-redesign-design.md
git commit -m "feat: each expression can carry a two-line Korean dialogue (schema v17)"
```

---

### Task 2: 대화문 생성 모듈

**Files:**
- Create: `backend/app/generation/korean_dialogues.py`
- Modify: `.claude/skills/expression-cleanup/SKILL.md` (끝에 절 하나)
- Test: `backend/tests/test_korean_dialogues.py`

**Interfaces:**
- Consumes: `ExpressionRepo.without_dialogue`, `ExpressionRepo.set_dialogue`, `KoreanLine`, `Expression` (Task 1). `app.llm.Runner`, `app.llm.Claude(model, effort, timeout_s)`, `app.llm.GenerationError`. `app.main.ROOT`.
- Produces:
  - `BATCH = 20`, `MODEL = "opus"`, `EFFORT = "medium"`, `TIMEOUT_S = 300`, `PROMPT: str`, `SCHEMA: dict` (spec의 출력 스키마에 `korean`, `english` 각각 `"minLength": 1`을 더한 것).
  - `prompt_for(expressions: list[Expression]) -> str`: `PROMPT` 뒤에 `[{"id", "phrase", "meaning", "usage_note", "examples", "korean_example"}]`를 `json.dumps(..., ensure_ascii=False, indent=2)`로 붙인다. `korean_example`은 있으면 `{"korean", "english"}`, 없으면 `null`.
  - `class DialogueWriter`: `__init__(self, runner: Runner) -> None`, `write(self, expressions: list[Expression]) -> dict[int, list[KoreanLine]]` (한 번의 `runner.run(prompt_for(expressions), SCHEMA)`; 위 "줄 검사"를 통과한 것만, 요청한 id의 첫 답만). `GenerationError`는 그대로 올린다.
  - `@dataclass(frozen=True) class Filled`: `made: int`, `skipped: int`.
  - `fill(expressions: ExpressionRepo, writer: DialogueWriter, *, limit: int | None, batch: int, apply: bool, out: TextIO) -> Filled`.
  - `main(argv: list[str]) -> int`: argparse `--apply`, `--limit N`(양의 정수), `--batch N`(양의 정수, 기본 `BATCH`), `--model`(기본 `MODEL`), `--effort`(기본 `EFFORT`). DB는 `os.environ.get("DB_PATH", ROOT / "data" / "sessions.db")`. `skipped`가 0보다 크면 1, 아니면 0. `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`. 모듈 docstring 첫 줄에 실행 명령 `docker compose exec backend uv run --no-dev python -m app.generation.korean_dialogues [--apply] [--limit N]`.

`fill`의 흐름 (`main`과 같은 높이로, 묶기와 쓰기와 출력은 private 도우미로):

```
candidates = expressions.without_dialogue(limit)
for chunk in chunks(candidates, batch):
    try: dialogues = writer.write(chunk)
    except GenerationError as e: print a warning naming the chunk's ids and e; skipped += len(chunk); continue
    print each expression in chunk that has a dialogue: "#{id} {phrase}" then "  A  {korean}" / "     {english}" / "  B  ..." 
    print a warning for each id in chunk with no usable answer; skipped += those
    if apply: set_dialogue for each answered id
    made += len(dialogues)
print one summary line: "wrote N, skipped M" when apply, "made N, skipped M (preview, nothing written)" otherwise
```

`PROMPT`에는 spec "프롬프트가 요구할 것"의 여섯 항목을 모두 영어로 담는다: A와 B 한 줄씩, B는 A에 대한 대답이나 반응; 적어도 한 줄의 `english`가 표현을 쓰고, 다른 줄은 자연스러우면 안 써도 되며 둘 다 억지로 넣지 않는다; 표현이 드는 줄이 A인지 B인지는 대화에 맞게, 한쪽으로 쏠리지 않게; 상황은 `examples`와 `korean_example`과 다르게; 한국어는 실제 구어, 영어는 그 한국어의 자연스러운 옮김이고 표현이 든 줄은 `meaning`과 `usage_note`에 맞게; 한 줄은 한두 문장. 그리고 받은 id마다 `dialogues`에 한 항목.

- [ ] **Step 1: 실패하는 테스트**

`backend/tests/test_korean_dialogues.py`:

```python
import io
import re

from app.generation.korean_dialogues import SCHEMA, DialogueWriter, Filled, fill, prompt_for
from app.llm import GenerationError
from app.models import KoreanLine
from tests.conftest import seed_expressions


def two_lines(i: int) -> list[dict]:
    return [{"korean": f"가 {i}", "english": f"A {i}"}, {"korean": f"나 {i}", "english": f"B {i}"}]


class FakeClaude:
    """Answers each batch with two lines per id in the prompt. `answers` overrides the lines for an id ([] leaves it
    out); `extra` is appended as is; a batch holding an id in `fail` raises."""

    def __init__(self, answers=None, extra=(), fail=()):
        self.answers, self.extra, self.fail = answers or {}, list(extra), set(fail)
        self.batches: list[list[int]] = []
        self.schemas: list[dict] = []

    def run(self, prompt: str, schema: dict, on_message=None) -> dict:
        ids = [int(i) for i in re.findall(r'"id": (\d+)', prompt)]
        self.batches.append(ids)
        self.schemas.append(schema)
        if self.fail & set(ids):
            raise GenerationError("claude timed out after 300s")
        dialogues = [{"id": i, "lines": self.answers.get(i, two_lines(i))} for i in ids if self.answers.get(i, True) != []]
        return {"dialogues": dialogues + self.extra}


def run_fill(store, claude, *, limit=None, batch=20, apply=True) -> tuple[Filled, str]:
    out = io.StringIO()
    return fill(store.expressions, DialogueWriter(claude), limit=limit, batch=batch, apply=apply, out=out), out.getvalue()


def test_the_prompt_gives_each_expression_with_its_examples_and_korean_example(store):
    [a] = seed_expressions(store, 1)
    with store.connect() as conn:
        conn.execute("UPDATE expressions SET korean_example = ? WHERE id = ?", ('{"korean": "못 와?", "english": "Can\'t make it?"}', a))
    prompt = prompt_for([store.expressions.get(a)])
    for text in (f'"id": {a}', "alpha phrase", "meaning 0", "note 0", "ex 0a", "ex 0b", "못 와?"):
        assert text in prompt


def test_write_drops_blank_lines(store):
    a, b = seed_expressions(store, 2)
    claude = FakeClaude(answers={b: [{"korean": "가", "english": " "}, {"korean": "나", "english": "B"}]})
    written = DialogueWriter(claude).write([store.expressions.get(a), store.expressions.get(b)])
    assert list(written) == [a]
    assert written[a] == [KoreanLine(korean=f"가 {a}", english=f"A {a}"), KoreanLine(korean=f"나 {a}", english=f"B {a}")]


def test_write_drops_answers_without_exactly_two_lines(store):
    a, b, c = seed_expressions(store, 3)
    claude = FakeClaude(answers={b: two_lines(b)[:1], c: []})
    assert list(DialogueWriter(claude).write([store.expressions.get(i) for i in (a, b, c)])) == [a]


def test_write_keeps_only_the_first_answer_for_ids_it_asked_for(store):
    [a] = seed_expressions(store, 1)
    claude = FakeClaude(extra=[{"id": a, "lines": two_lines(99)}, {"id": 999, "lines": two_lines(999)}])
    written = DialogueWriter(claude).write([store.expressions.get(a)])
    assert list(written) == [a] and written[a][0].english == f"A {a}"


def test_a_preview_prints_each_dialogue_and_writes_nothing(store):
    a, b = seed_expressions(store, 2)
    filled, printed = run_fill(store, FakeClaude(), apply=False)
    assert filled == Filled(made=2, skipped=0)
    for text in ("alpha phrase", "bravo phrase", f"가 {a}", f"A {a}", f"나 {b}", f"B {b}", "nothing written"):
        assert text in printed
    assert [e.id for e in store.expressions.without_dialogue()] == [a, b]


def test_apply_asks_in_batches_and_writes_every_dialogue(store):
    ids = seed_expressions(store, 5)
    claude = FakeClaude()
    filled, _ = run_fill(store, claude, batch=2)
    assert claude.batches == [ids[:2], ids[2:4], ids[4:]]
    assert claude.schemas[0] is SCHEMA
    assert filled == Filled(made=5, skipped=0)
    assert store.expressions.without_dialogue() == []
    assert store.expressions.get(ids[4]).korean_dialogue[1].korean == f"나 {ids[4]}"


def test_a_failed_batch_is_skipped_and_the_others_are_written(store):
    ids = seed_expressions(store, 5)
    filled, printed = run_fill(store, FakeClaude(fail={ids[2]}), batch=2)
    assert filled == Filled(made=3, skipped=2)
    assert [e.id for e in store.expressions.without_dialogue()] == ids[2:4]
    assert "timed out" in printed


def test_an_unusable_answer_is_skipped_and_left_for_the_next_run(store):
    a, b = seed_expressions(store, 2)
    filled, _ = run_fill(store, FakeClaude(answers={b: []}))
    assert filled == Filled(made=1, skipped=1)
    assert [e.id for e in store.expressions.without_dialogue()] == [b]


def test_only_expressions_without_a_dialogue_are_asked_for_up_to_the_limit(store):
    a, b, c, d = seed_expressions(store, 4)
    store.expressions.set_dialogue(a, [KoreanLine(**line) for line in two_lines(a)])
    claude = FakeClaude()
    run_fill(store, claude, limit=2)
    assert claude.batches == [[b, c]]


def test_nothing_left_asks_claude_nothing(store):
    claude = FakeClaude()
    filled, _ = run_fill(store, claude)
    assert claude.batches == [] and filled == Filled(made=0, skipped=0)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/pytest -q tests/test_korean_dialogues.py 2>&1 | grep -E "FAILED|passed|failed|Error"`
Expected: `ModuleNotFoundError: No module named 'app.generation.korean_dialogues'`.

- [ ] **Step 3: 구현**

`backend/app/generation/korean_dialogues.py`를 위 Interfaces와 흐름대로 쓴다. `main`은 `Database(...)`, `Claude(args.model, args.effort, TIMEOUT_S)`, `DialogueWriter`, `fill(..., out=sys.stdout)`만 잇는다. 로그가 보이게 `logging.basicConfig(level=logging.INFO)`.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/pytest -q tests/test_korean_dialogues.py 2>&1 | grep -E "FAILED|passed|failed"`
Expected: 11 passed.

- [ ] **Step 5: 실행 확인 (Claude 없이)**

Run: `cd backend && .venv/bin/python -m app.generation.korean_dialogues --help`
Expected: 다섯 옵션이 나오고 종료 코드 0. 실제 Claude 실행은 Task 4에서 운영 DB로 한다.

- [ ] **Step 6: cleanup skill에 한 절**

`.claude/skills/expression-cleanup/SKILL.md`의 "## Common mistakes" 앞에:

```markdown
## After an import

New expressions have no Korean dialogue. Preview a few, then fill the rest:

    docker compose exec backend uv run --no-dev python -m app.generation.korean_dialogues --limit 10
    docker compose exec backend uv run --no-dev python -m app.generation.korean_dialogues --apply

It only asks for expressions that have none, so running it again is safe.
```

- [ ] **Step 7: 커밋**

`detect-changes`를 돌린 뒤:

```bash
git add backend/app/generation/korean_dialogues.py backend/tests/test_korean_dialogues.py .claude/skills/expression-cleanup/SKILL.md
git commit -m "feat: a module fills missing Korean dialogues with Claude, preview first and --apply to write"
```

---

### Task 3: 카드의 토글과 대화 카드

**Files:**
- Modify: `frontend/src/types.ts` (`KoreanLine`, `Expression.korean_dialogue`)
- Modify: `frontend/src/components/ExpressionsTab.tsx` (`tab-brief` 문구, 111줄의 렌더, `KoreanExample` → `KoreanSentence`, 새 `KoreanPractice`, `KoreanDialogue`)
- Modify: `frontend/src/components/ExpressionsTab.css` (`.korean-example*` 옆에)
- Modify: `docs/superpowers/specs/2026-10-25-sqlite-schema-redesign-design.md` (155줄 "한국어 예문" 항목)
- Test: `frontend/src/components/ExpressionsTab.test.tsx`, `backend/tests/test_presence_room.py`

**Interfaces:**
- Consumes: 응답의 `korean_dialogue` (Task 1). `useSharedView<T>(key, initial): [T, (value: T) => void]` (`frontend/src/lib/presence/useSharedView.ts`). `Marked({ text, word })`.
- Produces (파일 안 private):
  - `type KoreanLine = { korean: string; english: string }` (`types.ts`에서 export), `Expression.korean_dialogue?: KoreanLine[] | null`.
  - `KoreanPractice({ expression }: { expression: Expression })`: `.korean-example` 래퍼, 라벨 줄 `.korean-example-head`(라벨 + 둘 다 있을 때만 토글 `.korean-practice-modes`), 고른 카드. 모드는 `useSharedView<'dialogue' | 'solo'>(\`mode:${id}\`, 'dialogue')`. 대화가 없으면 한 문장, 한 문장이 없으면 대화.
  - `KoreanSentence({ expressionId, example, phrase })`: 지금 `KoreanExample`에서 라벨 `<p>`만 뺀 카드. 키 `example:{id}` 그대로.
  - `KoreanDialogue({ expressionId, lines, phrase })`: `.korean-example-card` 버튼 하나, `aria-pressed`, 키 `dialogue:{id}`(boolean, 기본 false). 줄마다 `.korean-dialogue-line` 안에 `.korean-dialogue-speaker`("A"/"B")와 본문(한국어 면은 `.korean-example-korean` + `lang="ko"`, 영어 면은 `.korean-example-english` 안의 `<Marked>`). 끝에 기존 `.korean-example-hint`.
- `ExpressionsTab`의 렌더: `{(item.korean_example || item.korean_dialogue) && <KoreanPractice expression={item} />}`.

CSS: `.korean-example-head`는 라벨과 토글을 한 줄 양끝에 (flex, `align-items: center`, `justify-content: space-between`, 아래 여백은 지금 라벨의 `0.5rem`을 옮겨 온다; 라벨 자체 margin은 0). `.korean-practice-modes`는 테두리 하나로 묶인 두 칸, 고른 칸(`[aria-pressed='true']`)은 `var(--phrase)` 계열로 칠한다. `.korean-dialogue-line`은 화자 칸과 본문 칸의 grid, 줄 사이 여백. `.korean-dialogue-speaker`는 `var(--muted)`, 본문보다 작고 굵게. 대화 카드의 본문은 두 줄이라 `1.15rem` 정도로 한 문장 카드(`1.3rem`)보다 작게. 폰 폭(360px)에서 라벨 줄이 넘치지 않게 토글은 줄어들지 않고(`flex: none`) 라벨이 줄바꿈된다.

- [ ] **Step 1: 실패하는 presence 서버 테스트**

`backend/tests/test_presence_room.py`:

```python
def test_the_korean_practice_keys_reach_everyone():
    room, mina, jo = two_people()
    room.handle(mina, view(key="mode:21", value="solo", seq=1))
    room.handle(mina, view(key="dialogue:21", value=True, seq=2))
    assert [(m["key"], m["value"]) for m in jo.outbox.take() if m["type"] == "view"] == [("mode:21", "solo"), ("dialogue:21", True)]
```

이 테스트는 지금도 통과해야 한다 (키 패턴 확인용). 통과하지 않으면 키 이름을 고친다, 서버 패턴을 넓히지 않는다.

Run: `cd backend && .venv/bin/pytest -q tests/test_presence_room.py 2>&1 | grep -E "FAILED|passed|failed"`
Expected: 실패 없음.

- [ ] **Step 2: 실패하는 프런트 테스트**

`frontend/src/components/ExpressionsTab.test.tsx`의 `describe('ExpressionsTab', ...)` 안에:

```tsx
const sentence = { korean: '마감이 계속 바뀌어.', english: 'The deadline is a moving target.' }
const dialogue = [
  { korean: '요즘 일정 어때?', english: 'How is the schedule these days?' },
  { korean: '마감이 자꾸 바뀌어서 정신없어.', english: "The deadline is a moving target, so it's chaos." },
]
const both = [{ ...items[0], korean_example: sentence, korean_dialogue: dialogue }]
const practice = () => screen.getByRole('group', { name: '연습 방식' })

it('shows the dialogue first, with a toggle to the one sentence, when the expression has both', () => {
  render(<ExpressionsTab items={both} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
  expect(within(practice()).getByRole('button', { name: '대화' })).toHaveAttribute('aria-pressed', 'true')
  expect(within(practice()).getByRole('button', { name: '한 문장' })).toHaveAttribute('aria-pressed', 'false')
  const card = screen.getByRole('button', { name: /요즘 일정 어때\?/ })
  expect(card).toHaveAttribute('aria-pressed', 'false')
  for (const text of ['A', 'B', '요즘 일정 어때?', '마감이 자꾸 바뀌어서 정신없어.', '영어로 어떻게 말할까요?']) {
    expect(within(card).getByText(text)).toBeInTheDocument()
  }
  expect(screen.queryByText('마감이 계속 바뀌어.')).toBeNull()
})

it('flips both lines of the dialogue to English at once and back', async () => {
  render(<ExpressionsTab items={both} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
  const card = screen.getByRole('button', { name: /요즘 일정 어때\?/ })
  await userEvent.click(card)
  expect(card).toHaveAttribute('aria-pressed', 'true')
  expect(within(card).getByText('How is the schedule these days?')).toBeInTheDocument()
  expect(within(card).getAllByText('a moving target', { selector: 'mark' })).toHaveLength(1)
  expect(within(card).queryByText('요즘 일정 어때?')).toBeNull()
  expect(within(card).getByText('모범 답안 · 다르게 말해도 표현을 넣었으면 충분해요')).toBeInTheDocument()
  await userEvent.click(card)
  expect(within(card).getByText('요즘 일정 어때?')).toBeInTheDocument()
})

it('switches to the one sentence and back with the toggle', async () => {
  render(<ExpressionsTab items={both} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
  await userEvent.click(within(practice()).getByRole('button', { name: '한 문장' }))
  expect(within(practice()).getByRole('button', { name: '한 문장' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: /마감이 계속 바뀌어\./ })).toBeInTheDocument()
  expect(screen.queryByText('요즘 일정 어때?')).toBeNull()
  await userEvent.click(within(practice()).getByRole('button', { name: '대화' }))
  expect(screen.getByText('요즘 일정 어때?')).toBeInTheDocument()
})

it('shows only the dialogue, with no toggle, when the expression has no one sentence', () => {
  render(<ExpressionsTab items={[{ ...items[0], korean_dialogue: dialogue }]} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
  expect(screen.queryByRole('group', { name: '연습 방식' })).toBeNull()
  expect(screen.getByText('한국어로 해 보기')).toBeInTheDocument()
  expect(screen.getByText('요즘 일정 어때?')).toBeInTheDocument()
})

it('shows only the one sentence, with no toggle, when the expression has no dialogue', () => {
  render(<ExpressionsTab items={[{ ...items[0], korean_example: sentence }]} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
  expect(screen.queryByRole('group', { name: '연습 방식' })).toBeNull()
  expect(screen.getByText('마감이 계속 바뀌어.')).toBeInTheDocument()
})
```

`describe('ExpressionsTab with someone else in the session', ...)` 안에:

```tsx
it('switches the mode and flips the dialogue with them', async () => {
  const both = [{ ...items[0], korean_example: { korean: '목표가 자꾸 바뀌어.', english: 'It is a moving target.' }, korean_dialogue: [
    { korean: '요즘 일정 어때?', english: 'How is the schedule?' },
    { korean: '목표가 자꾸 바뀌어.', english: 'It is a moving target.' },
  ] }]
  const { socket } = renderInRoom(tab(both))
  someoneSets(socket, 'mode:21', 'solo')
  expect(screen.queryByText('요즘 일정 어때?')).toBeNull()
  someoneSets(socket, 'mode:21', 'dialogue')
  someoneSets(socket, 'dialogue:21', true)
  expect(screen.getByText('How is the schedule?')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '한 문장' }))
  expect(viewsSent(socket)).toEqual([{ key: 'mode:21', value: 'solo' }])
})
```

- [ ] **Step 3: 실패 확인**

Run: `cd frontend && npx vitest run src/components/ExpressionsTab.test.tsx 2>&1 | grep -E "FAIL|✓|×|Tests "`
Expected: 새 테스트 6개 FAIL, 기존 테스트는 통과.

- [ ] **Step 4: 구현**

`ExpressionsTab`과 `KoreanExample`에 GitNexus `impact`를 돌린 뒤, 위 Interfaces와 CSS 설명대로 `types.ts`, `ExpressionsTab.tsx`, `ExpressionsTab.css`를 고친다. `tab-brief`는 Global Constraints의 문구로 바꾼다.

- [ ] **Step 5: 통과 확인**

Run: `cd frontend && npx vitest run 2>&1 | grep -E "FAIL|Test Files|Tests "`, `npx tsc -b --noEmit`, `npm run lint`
Expected: 실패 없음 (기준선 531 + 6), 타입 오류 없음, lint 경고 없음.

- [ ] **Step 6: 화면 확인**

이 호스트의 `backend/data/sessions.db`는 운영 DB다 (`compose.yaml`이 `./backend/data`를 마운트한다). 건드리지 않고 사본으로 본다.

1. 사본: `cp backend/data/sessions.db <scratchpad>/sessions.db` (scratchpad는 세션 임시 폴더).
2. 사본의 아무 세션에 든 표현 하나에 대화문을 넣는다: `cd backend && DB_PATH=<scratchpad>/sessions.db .venv/bin/python -c "..."`로 `Database(path).expressions.set_dialogue(id, [KoreanLine(...), KoreanLine(...)])`. 로그인은 같은 `DB_PATH`로 `python -m app.accounts.reset_password EMAIL`을 사본에 돌려 얻는다.
3. backend: `cd backend && DB_PATH=<scratchpad>/sessions.db .venv/bin/uvicorn --factory app.main:default_app --host 127.0.0.1 --port 8765`. frontend: `cd frontend && npx vite` (5173은 운영 컨테이너가 쓰므로 vite가 다음 포트를 고른다. 출력된 주소를 쓴다).
4. `example-skills:webapp-testing`으로 그 세션의 Expressions 탭을 연다. 데스크톱 폭과 360px 폭에서 라벨 줄, 토글, 두 줄 카드, 뒤집은 면의 형광펜을 스크린샷으로 본다. 끝나면 두 서버를 끈다.

- [ ] **Step 7: 문서**

`2026-10-25-sqlite-schema-redesign-design.md` 155줄을 이렇게 바꾼다:

"- 한국어로 해 보기: 표현마다 한 문장 예문(`korean_example`)과 A, B 두 줄 대화문(`korean_dialogue`). 카드의 영어 예문 아래에 한국어로 보이고, 둘이 영어로 말해 본 뒤 누르면 영어 모범 답안(표현에 형광펜)으로 바뀐다. 대화는 두 줄이 한꺼번에 바뀌고, 표현은 적어도 한 줄에 든다. 둘 다 있으면 라벨 옆 토글(한 문장 | 대화, 기본 대화)로 고르고, 하나만 있으면 그것만 보인다. 모드(`mode:{id}`)와 뒤집기(`example:{id}`, `dialogue:{id}`)는 presence로 세션 모두가 같이 보고 저장하지 않는다. 앱에는 쓰는 경로가 없다. 대화문은 `python -m app.generation.korean_dialogues`가 Claude로 만들어 `--apply`로 빈 것만 채운다. 한 문장 예문을 만들던 로컬 스크립트는 남아 있지 않다."

- [ ] **Step 8: 커밋**

`detect-changes`를 돌린 뒤:

```bash
git add frontend/src/types.ts frontend/src/components/ExpressionsTab.tsx frontend/src/components/ExpressionsTab.css frontend/src/components/ExpressionsTab.test.tsx backend/tests/test_presence_room.py docs/superpowers/specs/2026-10-25-sqlite-schema-redesign-design.md
git commit -m "feat: each expression card toggles between the one sentence and a two-line dialogue, flipped for everyone"
```

---

### Task 4: 마무리, 합치기, 채우기

- [ ] **Step 1: 전체 테스트**

Run: `cd backend && .venv/bin/pytest -q 2>&1 | grep -E "FAILED|passed|failed"`
Run: `cd frontend && npx vitest run 2>&1 | grep -E "FAIL|Test Files|Tests "`, `npx tsc -b --noEmit`, `npm run lint`
Expected: 실패 없음. 하나라도 실패하면 여기서 멈춘다.

- [ ] **Step 2: 최종 리뷰**

새 서브에이전트 하나에게 `git diff main...feat/korean-dialogue`와 spec을 주고 브랜치 전체를 리뷰받는다 (executing-plans의 마지막 리뷰). 고친 것은 따로 커밋한다.

- [ ] **Step 3: spec 상태와 합치기**

spec 머리의 상태를 "구현됨 (2026-11-19). 구현 계획: `docs/superpowers/plans/2026-11-19-korean-dialogue.md`."로 바꿔 커밋한 뒤:

```bash
node .gitnexus/run.cjs detect-changes --scope compare --base-ref main --repo .
git switch main
git merge --ff-only feat/korean-dialogue
scripts/bump-version patch
```

- [ ] **Step 4: 배포와 채우기 (사용자가 말할 때만)**

사용자가 배포를 말하면, 이 호스트의 repo 루트에서:

1. 도는 세션 생성이 없는지 본다: `docker compose logs backend --since 10m | grep -c 'POST /api/sessions HTTP'`와 관리자 `GET /api/jobs`. 있으면 끝날 때까지 기다린다. 재시작은 job과 presence 방을 끊는다.
2. `docker compose up -d --build`. backend 로그에서 `upgraded ... from schema v16 to v17`과 백업 파일 이름을 확인한다.
3. 미리보기: `docker compose exec backend uv run --no-dev python -m app.generation.korean_dialogues --limit 10`. 출력을 사용자에게 보여 주고, 계속할지 묻는다.
4. 사용자가 좋다고 하면: `docker compose exec backend uv run --no-dev python -m app.generation.korean_dialogues --apply`. 932개, 묶음 20개면 Claude 실행 47번이다. 끝 줄의 `wrote N, skipped M`을 보고한다. 건너뛴 것이 있으면 같은 명령을 한 번 더 돌린다.
5. push는 사용자가 말할 때 `git push --follow-tags`.
