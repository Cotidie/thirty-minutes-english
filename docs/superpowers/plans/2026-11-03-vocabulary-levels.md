# Vocabulary 난이도 설정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 태스크를 이 세션에서 직접 실행하고, 끝에 새 서브에이전트 리뷰를 한 번만 한다 (사용자가 정한 방식). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자가 설정 화면에서 B1, B2, C1, C2 중 포함할 수준을 골라 새 세션의 단어 수준을 정한다.

**Architecture:** 수준 목록은 새 모듈 `app/generation/levels.py`가 갖는다. 설정 항목 `VOCABULARY_LEVELS`는 "여러 개 고름"(`Spec.many`) 성질로 저장 검사와 화면의 체크박스를 얻는다. `build_services`가 그 값을 `ClaudeGenerator(levels=...)`로 넘기고, 생성기는 프롬프트의 수준 문장을 그 값으로 쓴다.

**Tech Stack:** FastAPI, pydantic, pytest, React 19, react-aria-components 1.21 (`CheckboxGroup`, `Checkbox`), vitest.

**Spec:** `docs/superpowers/specs/2026-11-03-vocabulary-levels-design.md`

## Global Constraints

- 브랜치 `feat/vocabulary-levels`에서 작업한다 (이 문서가 이미 그 위에 있다). `main`에는 `--ff-only`로 합치고, 그 뒤 `scripts/bump-version patch`만 쓴다. minor나 major는 올리지 않는다. push와 배포는 사용자가 말할 때만 한다.
- 심볼을 고치기 전에 GitNexus `impact`(`node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .` 또는 MCP `impact`), 커밋 전에 `detect-changes --scope all`. HIGH 이상은 보고한다. `risk: UNKNOWN`은 텍스트 검색으로 확인한다.
- 커밋 메시지는 제목과 본문뿐이다. `Co-Authored-By`를 넣지 않는다.
- 새 Python, npm 의존성이 없다. 새 셸 스크립트를 만들지 않는다.
- 수준 이름과 설명은 `backend/app/generation/levels.py`에만 적는다. 프런트는 설정 API의 `options`로 받고 하드코딩하지 않는다.
- 코드, 주석, 테스트 이름, 화면 문구는 영어다. 함수 하나는 한 추상화 수준만 말한다 (`/home/humanoid/CLAUDE.md`).
- 백엔드 테스트: `cd backend && .venv/bin/pytest -q` (약 5분). 프런트: `cd frontend && npx vitest run`과 `npx tsc -b --noEmit`. 시작 기준선은 백엔드 560 passed, 프런트 53 files / 481 tests passed다.
- 테스트는 따로 돌리고 결과를 읽은 뒤에 커밋한다. `;`로 잇거나 `tail -1`로 자르지 않는다. 실패 이름은 `grep -E "FAILED|passed|failed"`로 남긴다.
- 운영 서버에서 Create session을 누르지 않는다. 비밀값을 출력하지 않는다.

## Review Focus

1. 환경변수로 들어온 소문자, 공백, 모르는 수준 (`b1, c2`, `A1`): 너그럽게 읽고, 남는 것이 없으면 `B2,C1`. (Task 1)
2. 순서를 뒤섞어 고름 (C2, B1 순으로 켬): 값은 늘 `B1,…,C2` 순서다. (Task 3)
3. 켜진 것을 하나만 남김: 그 칸은 끌 수 없고, 다른 칸을 켜면 다시 끌 수 있다. (Task 3)
4. 체크박스를 바꾼 뒤 Discard: 저장된 `B2,C1`로 돌아온다. (Task 3)
5. 저장 직후 다음 세션: 재시작 없이 새 수준을 쓴다. `put_settings`의 서비스 재생성은 기존 테스트가 고정하고, 이 계획은 `build_services`가 값을 넘기는지 고정한다. (Task 2)

---

### Task 1: 수준 모듈과 설정 항목

**Files:**
- Create: `backend/app/generation/levels.py`
- Modify: `backend/app/config/settings.py` (`Spec`, `SPECS`, `validate`, `Settings`), `backend/app/api/schemas.py` (`SettingField`), `backend/app/api/settings.py` (`field_of`)
- Test: `backend/tests/test_settings.py`

**Interfaces:**
- Produces: `LEVELS: tuple[str, ...] = ("B1", "B2", "C1", "C2")`, `LEVEL_LABELS: dict[str, str] = {"B1": "Intermediate", "B2": "Upper intermediate", "C1": "Advanced", "C2": "Proficient"}`, `DEFAULT_LEVELS = ("B2", "C1")`, `parse_levels(value: str) -> tuple[str, ...]` (in `levels.py`); `Spec.many: bool = False`; `Settings.vocabulary_levels -> tuple[str, ...]` (property); `SettingField.many: bool = False`.

- [ ] **Step 1: Write the failing tests in `backend/tests/test_settings.py`**

```python
def test_vocabulary_levels_take_any_set_of_known_levels(store):
    store.settings.save({"VOCABULARY_LEVELS": "B1,C2"})
    store.settings.save({"VOCABULARY_LEVELS": "C2"})
    for bad in ("", "A2", "B2,B2", "B2,X"):
        with pytest.raises(InvalidSetting, match="VOCABULARY_LEVELS must name one or more of B1, B2, C1, C2"):
            store.settings.save({"VOCABULARY_LEVELS": bad})
    assert store.settings.load()["VOCABULARY_LEVELS"] == "C2"


def test_vocabulary_levels_read_in_level_order_and_fall_back_to_b2_and_c1():
    assert Settings({}, {}).vocabulary_levels == ("B2", "C1")
    assert Settings({}, {"VOCABULARY_LEVELS": "C1,B2"}).vocabulary_levels == ("B2", "C1")
    assert Settings({"VOCABULARY_LEVELS": "b1, c2"}, {}).vocabulary_levels == ("B1", "C2")
    assert Settings({"VOCABULARY_LEVELS": "A1"}, {}).vocabulary_levels == ("B2", "C1")


def test_vocabulary_levels_show_as_named_checkboxes_on_the_claude_tab(tmp_path):
    with settings_client(tmp_path, {}) as c:
        fields = {f["key"]: f for f in c.get("/api/settings").json()["fields"]}
    levels = fields["VOCABULARY_LEVELS"]
    assert (levels["group"], levels["value"], levels["default"], levels["many"], levels["free"]) == ("claude", "B2,C1", "B2,C1", True, False)
    assert [(o["id"], o["description"]) for o in levels["options"]] == [
        ("B1", "Intermediate"), ("B2", "Upper intermediate"), ("C1", "Advanced"), ("C2", "Proficient"),
    ]
    assert fields["VOICE_NAME"]["many"] is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_settings.py -k vocabulary_levels`
Expected: 3 failed (`unknown setting VOCABULARY_LEVELS`, `no attribute 'vocabulary_levels'`, `KeyError: 'VOCABULARY_LEVELS'`).

- [ ] **Step 3: Create `backend/app/generation/levels.py`** with `LEVELS`, `LEVEL_LABELS`, `DEFAULT_LEVELS` and `parse_levels(value: str) -> tuple[str, ...]`: split on `,`, strip and upper-case each piece, keep the known ones in `LEVELS` order without repeats, `DEFAULT_LEVELS` when none is left. Module docstring: the CEFR levels a session's words are drawn from. The module imports nothing from the app.

- [ ] **Step 4: Change `backend/app/config/settings.py`**
  - `Spec`: add `many: bool = False  # the value is one or more of `choices`, joined with commas` after `labels`.
  - `validate`: for a `many` spec, split the value on `,` and strip each piece; raise `InvalidSetting(f"{key} must name one or more of {', '.join(spec.choices)}")` when there is no piece, a piece is not in `spec.choices`, or a piece repeats. Keep the single-choice check for specs without `many`. Keep the body at one level: put the many-value check in a private helper `_is_many_of(value: str, choices: tuple[str, ...]) -> bool`.
  - `SPECS`: after `SUMMARY_EFFORT`, before `IMAGE_PROVIDER`:
    `Spec("VOCABULARY_LEVELS", "claude", ",".join(DEFAULT_LEVELS), choices=LEVELS, labels=LEVEL_LABELS, many=True, help="The CEFR levels a new session's words come from. Sessions already made keep their words.")`
  - `Settings`: property `vocabulary_levels` returning `parse_levels(self.get("VOCABULARY_LEVELS"))`.

- [ ] **Step 5: Pass `many` through the API**
  `backend/app/api/schemas.py` `SettingField`: `many: bool = False  # several of `options` at once, joined with commas`. `backend/app/api/settings.py` `field_of`: `many=spec.many`.

- [ ] **Step 6: Run the settings tests**

Run: `cd backend && .venv/bin/pytest -q tests/test_settings.py tests/test_setting_specs.py`
Expected: all pass, including `test_rejects_unknown_key_and_bad_choice` and `test_get_masks_secrets_and_carries_the_rules_the_modal_applies` (every field still has `help`, every group still has a field).

- [ ] **Step 7: Commit**

```bash
git add backend/app/generation/levels.py backend/app/config/settings.py backend/app/api/schemas.py backend/app/api/settings.py backend/tests/test_settings.py
git commit -m "feat: VOCABULARY_LEVELS setting, one or more of B1 to C2"
```

### Task 2: 생성 프롬프트가 설정된 수준을 쓴다

**Files:**
- Modify: `backend/app/generation/levels.py` (`describe_levels`), `backend/app/generation/generator.py` (`PROMPT_TEMPLATE`, `ClaudeGenerator.__init__`, `ClaudeGenerator.build_prompt`), `backend/app/wiring.py` (`build_services`)
- Test: `backend/tests/test_generator.py`, `backend/tests/test_settings.py`

**Interfaces:**
- Consumes: `DEFAULT_LEVELS`, `LEVELS`, `Settings.vocabulary_levels` (Task 1).
- Produces: `describe_levels(levels: tuple[str, ...]) -> str`; `ClaudeGenerator(model, effort, firecrawl_key, timeout_s, levels: tuple[str, ...] = DEFAULT_LEVELS)` with attribute `levels`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_generator.py`:

```python
@pytest.mark.parametrize(
    ("levels", "asked", "spread"),
    [
        (("B2", "C1"), "8 words at B2 to C1 level connected to the topic.", " Spread them about evenly across B2 to C1."),
        (("B1",), "8 words at B1 level connected to the topic.", None),
        (("B1", "C1"), "8 words at B1 and C1 level", " Spread them about evenly across B1 and C1."),
        (("B1", "C1", "C2"), "8 words at B1, C1 and C2 level", " Spread them about evenly across B1, C1 and C2."),
        (("B1", "B2", "C1", "C2"), "8 words at B1 to C2 level", " Spread them about evenly across B1 to C2."),
    ],
)
def test_the_words_come_from_the_levels_set(levels, asked, spread):
    prompt = ClaudeGenerator(model="m", levels=levels).build_prompt("t")
    assert asked in prompt and "C1+" not in prompt
    assert ("Spread them" in prompt) == (spread is not None)
    assert spread is None or spread in prompt


def test_a_generator_told_no_levels_asks_for_b2_to_c1():
    assert "8 words at B2 to C1 level" in ClaudeGenerator(model="m").build_prompt("t")
```

In `backend/tests/test_settings.py` (import `agent_dirs` and `build_services` from `app.wiring`):

```python
def test_the_writer_of_new_sessions_takes_the_saved_levels(tmp_path):
    services = build_services(Settings({}, {"VOCABULARY_LEVELS": "B1"}), agent_dirs({}, tmp_path))
    assert services.generator.levels == ("B1",)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_generator.py tests/test_settings.py -k "levels"`
Expected: the new generator and wiring tests fail with `unexpected keyword argument 'levels'` or `no attribute 'levels'`; the default-levels test fails on `B2 to C1+`.

- [ ] **Step 3: Add `describe_levels` to `levels.py`**: one level gives `"B1"`; levels that sit next to each other in `LEVELS` give `"<first> to <last>"`; otherwise `"B1 and C1"`, `"B1, C1 and C2"` (commas, then `and` before the last).

- [ ] **Step 4: Change the generator**
  - In `PROMPT_TEMPLATE`, the vocabulary line becomes exactly `2. vocabulary: {vocabulary_count} words at {vocabulary_levels} level connected to the topic.{level_spread} Draw from the \` (the rest of the paragraph is unchanged).
  - `ClaudeGenerator.__init__` takes `levels: tuple[str, ...] = DEFAULT_LEVELS` last and keeps it as `self.levels`.
  - `build_prompt` fills `vocabulary_levels=describe_levels(self.levels)` and `level_spread` from a private helper `_spread(levels) -> str` that gives `f" Spread them about evenly across {describe_levels(levels)}."` for two or more levels and `""` for one.

- [ ] **Step 5: Pass the setting in `build_services`**: `ClaudeGenerator(..., levels=settings.vocabulary_levels)`.

- [ ] **Step 6: Run the whole backend suite**

Run: `cd backend && .venv/bin/pytest -q 2>&1 | grep -E "FAILED|ERROR|passed|failed"`
Expected: `570 passed` (560 + 10 new: 3 in Task 1, 7 here), no FAILED line. `test_a_session_teaches_exactly_eight_words` still passes (`2. vocabulary: 8 words`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/generation/levels.py backend/app/generation/generator.py backend/app/wiring.py backend/tests/test_generator.py backend/tests/test_settings.py
git commit -m "feat: new sessions draw their words from the levels in settings"
```

### Task 3: 설정 화면의 체크박스

**Files:**
- Modify: `frontend/src/types.ts` (`SettingField`), `frontend/src/components/Choice.tsx`, `frontend/src/components/Choice.css`, `frontend/src/components/SettingsModal.tsx` (`Control`)
- Test: `frontend/src/components/SettingsModal.test.tsx`

**Interfaces:**
- Consumes: `SettingField.many` from the API (Task 1).
- Produces: `ChoiceChecks({ labelledBy, options, value, onChange }: { labelledBy: string; options: SettingOption[]; value: string; onChange: (value: string) => void })` exported from `Choice.tsx`.

- [ ] **Step 1: Write the failing tests in `SettingsModal.test.tsx`**
  - `field()` gets `many: false` in its defaults.
  - `FIELDS` gets, after `CLAUDE_EFFORT`:
    `field({ key: 'VOCABULARY_LEVELS', group: 'claude', value: 'B2,C1', default: 'B2,C1', many: true, help: 'The CEFR levels a new session\'s words come from.', options: [opt('B1', 'Intermediate'), opt('B2', 'Upper intermediate'), opt('C1', 'Advanced'), opt('C2', 'Proficient')] })`

```tsx
function levelBox(level: string): HTMLInputElement {
  const group = screen.getByRole('group', { name: 'VOCABULARY_LEVELS' })
  return within(group).getByRole('checkbox', { name: new RegExp(`^${level}`) }) as HTMLInputElement
}

it('picks vocabulary levels as checkboxes, keeps one at least, and saves them in level order', async () => {
  await open()
  await showTab('Claude generation')
  expect(['B1', 'B2', 'C1', 'C2'].map((l) => levelBox(l).checked)).toEqual([false, true, true, false])
  await userEvent.click(levelBox('C2'))
  await userEvent.click(levelBox('B2'))
  await userEvent.click(levelBox('C1'))
  expect(levelBox('C2')).toBeChecked()
  expect(levelBox('C2')).toBeDisabled()
  await userEvent.click(levelBox('B1'))
  expect(levelBox('C2')).toBeEnabled()
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(api.putSettings).toHaveBeenCalledTimes(1))
  expect(vi.mocked(api.putSettings).mock.calls[0][0]).toEqual({ VOCABULARY_LEVELS: 'B1,C2' })
})

it('brings the saved levels back on Discard', async () => {
  await open()
  await showTab('Claude generation')
  await userEvent.click(levelBox('B1'))
  expect(screen.getByText('1 unsaved change')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Discard' }))
  expect(['B1', 'B2', 'C1', 'C2'].map((l) => levelBox(l).checked)).toEqual([false, true, true, false])
})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/components/SettingsModal.test.tsx`
Expected: the 2 new tests fail (no `group` named `VOCABULARY_LEVELS`); `tsc` would also flag `many` until Step 3.

- [ ] **Step 3: Add `many: boolean` to `SettingField` in `frontend/src/types.ts`** with the doc comment `/** Several of `options` at once: the value joins their ids with commas. */`.

- [ ] **Step 4: Write `ChoiceChecks` in `Choice.tsx`** with `CheckboxGroup` and `Checkbox` from `react-aria-components`. The picked ids are `value.split(',').filter(Boolean)`. On change, pass `options` ids that are picked, in `options` order, joined with `,`. A checkbox is disabled when it is the only one picked. Each checkbox shows a box (class `choice-check-box`, a check mark when selected), the id in `<b>`, a space, and the description in a `<span>`. Group class `choice-checks`, checkbox class `choice-check`.

- [ ] **Step 5: Style in `Choice.css`**: `.choice-checks` is a wrapping row with `gap: 0.5rem 1rem`. `.choice-check` lines up the box and text with `gap: 0.4rem` and `cursor: pointer`. `.choice-check-box` is an 18px square with `1px solid var(--line)`, `border-radius: 4px`, `background: #fff`; `[data-selected]` turns it `var(--ink)` with a white mark; `[data-disabled]` sets `cursor: default` and `opacity: 0.6`; `[data-focus-visible]` shows `outline: 2px solid var(--ink)` on the box. Description text in `var(--muted)`. Use only tokens already in `frontend/src/styles/base.css`.

- [ ] **Step 6: In `SettingsModal.tsx` `Control`, add first: `if (field.many) return <ChoiceChecks labelledBy={labelledBy} options={menu.options} value={value} onChange={onChange} />`.** Save, Discard and the change count stay as they are.

- [ ] **Step 7: Run the frontend checks**

Run: `cd frontend && npx vitest run 2>&1 | grep -E "FAIL|Test Files|Tests "` and `npx tsc -b --noEmit`
Expected: `53 passed (53)` files, `483 passed (483)` tests, `tsc` exit 0.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types.ts frontend/src/components/Choice.tsx frontend/src/components/Choice.css frontend/src/components/SettingsModal.tsx frontend/src/components/SettingsModal.test.tsx
git commit -m "feat: settings pick vocabulary levels with checkboxes"
```

### Task 4: 실제 화면 확인과 마무리

**Files:** 없음 (코드 변경 없음). 확인 중 고칠 것이 나오면 해당 태스크의 파일에서 TDD로 고친다.

- [ ] **Step 1: Run the app on a scratch database.** The Vite dev proxy sends `/api` to `127.0.0.1:8765` (`frontend/vite.config.ts`); the production containers do not take that host port, but the production frontend holds 5173. Backend: `cd backend && DB_PATH=<scratchpad>/levels.db ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=<a throwaway password of at least the length `backend/app/accounts/admin.py` requires> .venv/bin/uvicorn app.main:app --port 8765`, run in the background. Frontend: `cd frontend && npx vite --port 5199`, in the background. Do not print the password in a report.
- [ ] **Step 2: In the browser, as the admin, open Settings, `Claude generation`.** Expect checkboxes B1 to C2 with B2 and C1 on. Turn on B1, turn off B2 and C1, Save. Reload the page and reopen Settings. Expect only B1 on. Do not create a session.
- [ ] **Step 3: Stop both servers** (`pkill -f "[u]vicorn app.main:app --port 8765"`, `pkill -f "[v]ite --port 5199"`) and delete the scratch database.
- [ ] **Step 4: Final review, then finish.** Full suites as in Task 2 Step 6 and Task 3 Step 7, `detect-changes`, one fresh reviewer on the whole branch (executing-plans), then `superpowers:finishing-a-development-branch`. After a merge into `main`: `scripts/bump-version patch`.
