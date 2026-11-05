# 기사 다단계 작성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 태스크를 이 세션에서 직접 실행하고, 끝에 새 서브에이전트 리뷰를 한 번만 한다 (사용자가 정한 방식). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세션 생성기가 기사를 초안, 소리 내어 읽기용 편집, 다듬기(humanizer + stop-slop), 마무리의 네 Claude 호출로 쓰고, 다듬기 뒤에 코드가 문장과 문단 길이를 검사해 한 번 고치게 한다.

**Architecture:** `readability.py`는 읽기 기준 상수와 길이 검사를 갖는다. `passes.py`는 단계별 출력 모델, JSON schema, `Draft` 조립을 갖고, `prompts.py`는 단계별 프롬프트를 갖는다. `generator.py`의 `ClaudeGenerator.generate`는 단계를 차례로 부르는 흐름만 남는다. 진행 표시는 `StreamTracker.begin(stage)`로 단계를 넘겨받고, 프런트엔드는 같은 단계 값을 표시한다.

**Tech Stack:** Python 3, claude_agent_sdk, pydantic, pytest, jsonschema, React 19, TypeScript, vitest.

**Spec:** `docs/superpowers/specs/2026-11-05-article-passes-design.md`

## Global Constraints

- 브랜치 `feat/article-passes`에서 작업한다 (`git switch -c feat/article-passes`, spec 커밋 `121ad47` 위에서). `main`에는 `--ff-only`로 합치고, 그 뒤 `scripts/bump-version patch`만 쓴다. minor나 major는 올리지 않는다. push와 배포는 사용자가 말할 때만 한다.
- 심볼을 고치기 전에 GitNexus `impact`(`node .gitnexus/run.cjs impact "<symbol>" --direction upstream --repo .` 또는 MCP `impact`), 커밋 전에 `node .gitnexus/run.cjs detect-changes --scope all --repo .`. HIGH 이상은 보고한다. `risk: UNKNOWN`은 텍스트 검색으로 확인한다. 색인이 오래됐으면 먼저 `node .gitnexus/run.cjs analyze --index-only`.
- 커밋 메시지는 제목과 본문뿐이다. `Co-Authored-By`를 넣지 않는다.
- 새 Python, npm 의존성이 없다. 새 셸 스크립트를 만들지 않는다.
- 읽기 기준 값은 `backend/app/generation/readability.py`의 상수에만 둔다: 문장 20단어, 문단 4~5개, 문단 50~65단어, 문단당 수치 2개. 프롬프트는 이 상수로 문구를 만든다.
- 1·2·3·4단계 호출의 실패는 지금처럼 `GenerationError`로 생성 전체를 실패시킨다. 고치기 호출의 `GenerationError`만 3단계 결과로 대신한다. `Cancelled`는 어디서도 잡지 않는다.
- 세션 가격(`backend/app/credits.py`)과 과금(`_bill_session`)은 건드리지 않는다. 새 설정 항목이 없다. DB 스키마가 바뀌지 않는다.
- 코드, 주석, 테스트 이름, 프롬프트, 화면 문구는 영어다. 함수 하나는 한 추상화 수준만 말한다 (`/home/humanoid/CLAUDE.md`).
- 백엔드 테스트: `cd backend && .venv/bin/pytest -q` (약 5분). 프런트: `cd frontend && npx vitest run`과 `npx tsc -b --noEmit`. 시작 기준선(2026-11-05, `121ad47`)은 백엔드 595 passed, 프런트 53 files / 496 tests passed다.
- 테스트는 따로 돌리고 결과를 읽은 뒤에 커밋한다. `;`로 잇거나 `tail -1`로 자르지 않는다. 실패 이름은 `grep -E "FAILED|passed|failed"`로 남긴다.
- 운영 서버에서 Create session을 누르지 않는다. 비밀값을 출력하지 않는다.

## Review Focus

1. 따옴표로 끝나는 문장 (`... the truth."`)과 약어 (`U.S. Ambassador`, `a.m.`), 소수점 (`3.80`): 문장 나누기가 틀리면 멀쩡한 기사가 고치기에 걸리거나 긴 문장을 놓친다. (Task 1)
2. 고치기 호출이 시간 초과나 오류로 끝남: 3단계 결과로 계속하고, 진행 중 취소(`Cancelled`)는 그대로 올라간다. (Task 5)
3. 고친 결과가 오히려 어긋난 곳이 더 많음 (문단을 합쳐 3개가 됨 등): 3단계 결과를 쓴다. (Task 5)
4. 마무리 단계가 후보에 없는 이미지 주소를 냄: 버리고, 남은 이미지가 없으면 지금처럼 그림을 그린다 (`jobs.py`의 `_scenes_to_draw`는 그대로). (Task 3)
5. 진행 막대가 단계가 넷으로 늘어도 뒤로 가지 않고, 실패 문구가 새 단계 이름으로 나온다 ("Failed while writing a draft"). (Task 2)

---

### Task 1: 읽기 기준과 길이 검사

**Files:**
- Create: `backend/app/generation/readability.py`
- Test: `backend/tests/test_readability.py`
- Modify: `backend/tests/conftest.py` (테스트용 `readable_body` 추가)

**Interfaces:**
- Produces (`readability.py`): `MAX_SENTENCE_WORDS = 20`, `PARAGRAPH_COUNT = (4, 5)`, `PARAGRAPH_WORDS = (50, 65)`, `NUMBERS_PER_PARAGRAPH = 2`; `paragraphs(body: str) -> list[str]`; `sentences(paragraph: str) -> list[str]`; `word_count(text: str) -> int`; `problems(body: str) -> list[str]`.
- Produces (`tests/conftest.py`): `readable_body(word: str = "alpha", paragraphs: int = 4) -> str`. 문장 하나는 `" ".join([word.capitalize()] + [word] * 10) + "."` (11단어), 문단 하나는 그런 문장 5개를 공백으로 이은 것 (55단어), 본문은 문단을 `"\n\n"`로 이은 것.

- [ ] **Step 1: 브랜치를 만든다**

Run: `git switch -c feat/article-passes`
Expected: `Switched to a new branch 'feat/article-passes'`.

- [ ] **Step 2: Write the failing tests in `backend/tests/test_readability.py`**

```python
from app.generation.readability import MAX_SENTENCE_WORDS, PARAGRAPH_COUNT, PARAGRAPH_WORDS, paragraphs, problems, sentences, word_count
from tests.conftest import readable_body


def test_the_limits_are_the_ones_the_spec_sets():
    assert (MAX_SENTENCE_WORDS, PARAGRAPH_COUNT, PARAGRAPH_WORDS) == (20, (4, 5), (50, 65))


def test_sentences_end_at_marks_and_closing_quotes():
    assert sentences('Maldonado said it is "difficult." Then he left. Was it right?') == [
        'Maldonado said it is "difficult."', "Then he left.", "Was it right?",
    ]


def test_abbreviations_and_decimals_do_not_end_a_sentence():
    text = "The U.S. Ambassador wrote at 1:30 a.m. that 3.80 was low. Dr. Kim agreed."
    assert sentences(text) == ["The U.S. Ambassador wrote at 1:30 a.m. that 3.80 was low.", "Dr. Kim agreed."]


def test_a_hyphenated_word_counts_once():
    assert word_count("A U.S.-based, 13-episode run.") == 4


def test_paragraphs_split_on_blank_lines_even_with_spaces_in_them():
    assert paragraphs("One.\n\n\nTwo.\n  \nThree.\n") == ["One.", "Two.", "Three."]


def test_a_readable_body_has_no_problems():
    assert problems(readable_body()) == []
    assert problems(readable_body(paragraphs=5)) == []


def test_problems_name_the_paragraph_count_each_long_sentence_and_each_paragraph_out_of_range():
    long = " ".join(["Long"] + ["word"] * 24) + "."  # 25 words
    short = " ".join(["Short"] + ["word"] * 39) + "."  # 40 words, one sentence
    body = "\n\n".join([readable_body(paragraphs=1), long + " " + " ".join(["Fill"] + ["word"] * 29) + ".", short])
    assert problems(body) == [
        "The article has 3 paragraphs (range 4 to 5).",
        f'Sentence of 25 words (limit 20): "{long}"',
        "Sentence of 30 words (limit 20): \"" + " ".join(["Fill"] + ["word"] * 29) + '."',
        f'Sentence of 40 words (limit 20): "{short}"',
        "Paragraph 3 has 40 words (range 50 to 65).",
    ]
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_readability.py`
Expected: collection error, `ModuleNotFoundError: No module named 'app.generation.readability'`.

- [ ] **Step 4: Implement `readability.py` and `readable_body`**

- `word_count`: `len(text.split())`.
- `paragraphs`: `re.split(r"\n\s*\n", body)`, 앞뒤 공백을 지우고 빈 것은 버린다.
- `sentences`: 후보 경계는 `.`, `!`, `?` 뒤에 닫는 따옴표나 괄호(`"`, `'`, `”`, `’`, `)`)가 0개 이상 붙고, 그 뒤에 공백이 오고, 다음 글자가 대문자, 숫자, 여는 따옴표인 곳이다. 경계 앞의 낱말이 `ABBREVIATIONS = ("U.S.", "U.K.", "U.N.", "E.U.", "a.m.", "p.m.", "Dr.", "Mr.", "Mrs.", "Ms.", "St.", "Jr.", "e.g.", "i.e.", "vs.")` 가운데 하나면 나누지 않는다. 소수점은 뒤에 공백이 없으므로 저절로 나뉘지 않는다.
- `problems`: 순서는 문단 개수 항목, 그다음 문단 순서대로 그 문단의 긴 문장들, 그 문단의 길이 항목이다. 문구는 테스트의 세 형식 그대로다: `"The article has {n} paragraphs (range {lo} to {hi})."`, `'Sentence of {n} words (limit {MAX}): "{sentence}"'`, `"Paragraph {i} has {n} words (range {lo} to {hi})."` (문단 번호는 1부터).

- [ ] **Step 5: Run them to verify they pass**

Run: `cd backend && .venv/bin/pytest -q tests/test_readability.py`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/generation/readability.py backend/tests/test_readability.py backend/tests/conftest.py
git commit -m "feat: a readability check names each sentence over 20 words and each paragraph out of range"
```

---

### Task 2: 진행 단계 (백엔드와 프런트엔드)

**Files:**
- Modify: `backend/app/generation/progress.py` (`Stage`, `StreamTracker`), `backend/app/generation/jobs.py:36-43` (`DEFAULT_STAGE_SECONDS`)
- Modify: `frontend/src/lib/progress.ts` (`Stage`, `FLOORS`, `NEXT`, `stageLabel`)
- Test: `backend/tests/test_progress.py`, `backend/tests/test_jobs.py:100,108,111`, `backend/tests/test_schema.py:146-147`, `frontend/src/lib/progress.test.ts`, `frontend/src/components/GenerationProgress.test.tsx:109,133-135`

**Interfaces:**
- Produces: `Stage` 순서 `STARTING="starting"`, `SKILLS="skills"`, `SEARCHING="searching"`, `DRAFTING="drafting"`, `EDITING="editing"`, `POLISHING="polishing"`, `FINISHING="finishing"`, `FINALIZING="finalizing"`, `ILLUSTRATING="illustrating"` (`WRITING`은 없어진다). `StreamTracker.begin(stage: Stage, activity: str = "") -> None`.
- 규칙: tracker는 지금 단계 `_pass`(처음 `Stage.DRAFTING`)와 그 단계의 기본 activity `_pass_activity`(처음 `""`)를 갖는다. `begin`은 둘을 바꾸고 `_stage`와 `_activity`도 그 값으로 둔 뒤, 보이는 값이 바뀌었으면 progress를 알린다. 지금 코드가 `Stage.WRITING`으로 두는 곳은 모두 `self._pass`로 둔다. `SKILLS`와 `SEARCHING`으로 가는 것은 `_pass == DRAFTING`일 때만이다. StructuredOutput은 `_pass == FINISHING`일 때만 `FINALIZING`으로 가고, 그 밖에는 `_pass`에 머문다. 지금 activity를 `""`로 비우는 곳은 `_pass_activity`로 둔다. StructuredOutput 블록이 흐르기 시작할 때의 activity는 FINISHING에서 `"Writing out the session"`, 그 밖에서 `"Writing out the article"`이다.
- `DEFAULT_STAGE_SECONDS` (기록이 쌓이기 전의 추정이며 최근 5회의 중앙값이 대신한다): STARTING 10, SKILLS 10, SEARCHING 40, DRAFTING 70, EDITING 40, POLISHING 60, FINISHING 120, FINALIZING 10, ILLUSTRATING 90.
- 프런트 `FLOORS`: starting 3, skills 8, searching 15, drafting 45, editing 55, polishing 62, finishing 70, finalizing 80, illustrating 84. `NEXT`: starting와 skills는 searching의 floor, 나머지는 다음 단계의 floor, illustrating은 100.
- `stageLabel`: drafting `Writing a draft`, editing `Shortening sentences and evening out paragraphs`, polishing `Taking out machine-sounding phrasing`, finishing `Writing questions, translation, and words`. 나머지는 지금 그대로.

- [ ] **Step 1: Impact 확인**

Run: `node .gitnexus/run.cjs impact "StreamTracker" --direction upstream --repo .` 와 `node .gitnexus/run.cjs impact "Stage" --direction upstream --repo .`
Expected: 호출자는 `generator.py`, `jobs.py`, `api/schemas.py`, 테스트다. 위험도를 보고한다.

- [ ] **Step 2: Write the failing backend tests in `backend/tests/test_progress.py`**

기존 테스트를 고친다. `test_tracks_skill_search_writing_and_finalizing_in_order`는 이름을 `test_the_first_pass_tracks_skills_searches_and_drafting_and_its_output_does_not_finalize`로 바꾸고, 기대값을 `[(Stage.SKILLS, 0), (Stage.SEARCHING, 1), (Stage.SEARCHING, 2), (Stage.DRAFTING, 2)]`로 둔다 (StructuredOutput 뒤에 새 progress가 없다). 다른 테스트의 `Stage.WRITING`은 `Stage.DRAFTING`이다. `test_the_item_check_is_not_a_search_and_text_after_finalizing_does_not_regress`는 첫 줄에 `t.begin(Stage.FINISHING)`을 넣고, 첫 assert를 `Progress(Stage.FINISHING, 0, "Checking picks against past sessions")`로 둔다. `test_a_block_that_starts_streaming_updates_the_label_at_once`도 `t.begin(Stage.FINISHING)`으로 시작하고, thinking 뒤 기대값을 `(Stage.FINISHING, "Thinking")`으로 둔다. 새 테스트:

```python
def test_later_passes_hold_their_stage_and_only_the_finishing_output_finalizes():
    seen: list[Progress] = []
    t = StreamTracker(seen.append)
    t.begin(Stage.EDITING)
    t.feed(assistant(text()))
    t.feed(assistant(tool_use("StructuredOutput")))
    t.begin(Stage.POLISHING)
    t.feed(assistant(tool_use("Skill", skill="english-session:stop-slop")))
    assert (t.progress.stage, t.progress.activity) == (Stage.POLISHING, "Loading the stop-slop skill")
    t.begin(Stage.FINISHING)
    t.feed(assistant(tool_use("StructuredOutput")))
    assert stages(seen) == [(Stage.EDITING, 0), (Stage.POLISHING, 0), (Stage.POLISHING, 0), (Stage.FINISHING, 0), (Stage.FINALIZING, 0)]


def test_a_pass_activity_shows_between_thoughts():
    t = StreamTracker(lambda _: None)
    t.begin(Stage.POLISHING, "Fixing sentence and paragraph lengths")
    t.feed(stream({"type": "content_block_start", "content_block": {"type": "thinking"}}))
    assert t.progress.activity == "Thinking"
    t.feed(assistant(text()))
    assert (t.progress.stage, t.progress.activity) == (Stage.POLISHING, "Fixing sentence and paragraph lengths")


def test_tokens_add_up_across_passes():
    t = StreamTracker(lambda _: None)
    t.feed(assistant(text(), usage={"input_tokens": 100, "output_tokens": 10}, message_id="m1"))
    t.begin(Stage.EDITING)
    t.feed(assistant(text(), usage={"input_tokens": 50, "output_tokens": 5}, message_id="m2"))
    assert (t.progress.input_tokens, t.progress.output_tokens) == (150, 15)
```

`test_jobs.py`: 100행과 111행의 `2 + 4 + 4 * 3`은 `2 + 4 + 4 * 6`이다 (SEARCHING 뒤의 단계가 여섯 개). 108행의 `Stage.WRITING`은 `Stage.DRAFTING`이다. `test_schema.py` 146~147행의 `Stage.WRITING`은 `Stage.DRAFTING`이다.

- [ ] **Step 3: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_progress.py tests/test_jobs.py tests/test_schema.py 2>&1 | grep -E "FAILED|passed|failed|Error"`
Expected: `AttributeError: DRAFTING`, `no attribute 'begin'` 등으로 실패.

- [ ] **Step 4: `Stage`, `StreamTracker.begin`, `DEFAULT_STAGE_SECONDS`를 위 Interfaces대로 바꾼다**

- [ ] **Step 5: Run the backend tests to verify they pass**

Run: `cd backend && .venv/bin/pytest -q tests/test_progress.py tests/test_jobs.py tests/test_schema.py tests/test_generator.py 2>&1 | grep -E "FAILED|passed|failed"`
Expected: `test_generator.py::test_generate_validates_the_payload_and_reports_progress`만 실패한다 (StructuredOutput이 더는 FINALIZING으로 가지 않고 DRAFTING에 머문다). 그 테스트는 Task 5에서 다시 쓰므로, 이 태스크에서는 기대값을 `[Progress(Stage.SEARCHING, 1), Progress(Stage.DRAFTING, 1)]`로 바꿔 둔다. 다시 돌려 모두 통과를 확인한다.

- [ ] **Step 6: Write the failing frontend tests**

`progress.test.ts`의 `creeps through writing ...`은 `creeps through drafting against the usual time of that stage`로 바꾸고 `stage: 'drafting'`, 기대값 50과 54로 둔다. 새 테스트:

```ts
  it('climbs through the passes in order', () => {
    const stages = ['drafting', 'editing', 'polishing', 'finishing', 'finalizing', 'illustrating'] as const
    const floors = stages.map((stage) => percentFor(job({ stage })))
    expect(floors).toEqual([45, 55, 62, 70, 80, 84])
  })
```

`labelFor` 테스트에 `expect(labelFor(job({ stage: 'polishing' }))).toBe('Taking out machine-sounding phrasing')`와 `expect(labelFor(job({ status: 'failed', stage: 'drafting' }))).toBe('Failed while writing a draft')`를 더한다. `GenerationProgress.test.tsx` 109행과 133행의 `'writing'`은 `'drafting'`, 135행의 문구는 `'Failed while writing a draft'`다.

- [ ] **Step 7: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/lib/progress.test.ts src/components/GenerationProgress.test.tsx`
Expected: FAIL (타입 오류 또는 floor 값 불일치).

- [ ] **Step 8: `progress.ts`를 위 Interfaces대로 바꾼다**

- [ ] **Step 9: Run the frontend checks**

Run: `cd frontend && npx vitest run 2>&1 | grep -E "Test Files|Tests|FAIL"` 와 `cd frontend && npx tsc -b --noEmit`
Expected: 모두 통과, 타입 오류 없음.

- [ ] **Step 10: detect-changes 후 Commit**

```bash
node .gitnexus/run.cjs detect-changes --scope all --repo .
git add backend/app/generation/progress.py backend/app/generation/jobs.py backend/tests/test_progress.py backend/tests/test_jobs.py backend/tests/test_schema.py backend/tests/test_generator.py frontend/src/lib/progress.ts frontend/src/lib/progress.test.ts frontend/src/components/GenerationProgress.test.tsx
git commit -m "feat: generation progress shows the draft, edit, polish and finish passes in turn"
```

---

### Task 3: 단계별 출력 모델, schema, Draft 조립

**Files:**
- Create: `backend/app/generation/passes.py`
- Test: `backend/tests/test_passes.py`
- Modify: `backend/tests/conftest.py` (`sample_first_draft`, `sample_finish` 추가)

**Interfaces:**
- Consumes: `app.models`의 `Draft`, `ArticleDraft`, `Source`, `Question`, `SentencePair`, `FigureDraft`, `PictureDraft`, `ParagraphPictureDraft`, `VocabularyDraft`; `app.llm.GenerationError`.
- Produces (`passes.py`):
  - `VOCABULARY_COUNT = 8` (`generator.py`에서 옮긴다. `generator.py`는 이것을 import해서 `from app.generation.generator import VOCABULARY_COUNT`를 쓰는 `jobs.py`와 `conftest.py`가 그대로 돌게 한다).
  - `class ArticleText(BaseModel)`: `title: str`, `body: str`.
  - `class ImageCandidate(BaseModel)`: `image_url: str`, `page_url: str`, `credit: str = ""`, `shows: str`.
  - `class FirstDraft(ArticleText)`: `sources: list[Source] = []`, `images: list[ImageCandidate] = []`.
  - `class Finish(BaseModel)`: `topic: str`, `questions: list[Question]`, `translation: list[SentencePair] = []`, `figures: list[FigureDraft] = []`, `picture: PictureDraft`, `paragraph_picture: ParagraphPictureDraft`, `vocabulary: list[VocabularyDraft]`.
  - `DRAFT_SCHEMA: dict` (required `title`, `body`, `sources`, `images`; sources는 지금 `SESSION_SCHEMA`의 sources 그대로, images는 `maxItems: 4`, 항목 required `image_url`, `page_url`, `credit`, `shows`).
  - `TEXT_SCHEMA: dict` (required `title`, `body`).
  - `FINISH_SCHEMA: dict` (required `topic`, `questions`, `translation`, `figures`, `picture`, `paragraph_picture`, `vocabulary`; 각 항목 schema는 지금 `SESSION_SCHEMA`의 것을 그대로 옮긴다). 모든 object에 `additionalProperties: False`.
  - `parse(model: type[M], payload: dict) -> M`: pydantic `ValidationError`를 `GenerationError(f"structured output failed validation: {e}")`로 바꾼다.
  - `assemble(text: ArticleText, first: FirstDraft, finish: Finish) -> Draft`: title과 body는 `text`, sources는 `first`, 나머지는 `finish`에서 온다. `finish.figures` 가운데 `image_url`이 `first.images`에 없는 것은 버린다.
- Produces (`tests/conftest.py`): `sample_first_draft(body: str | None = None) -> dict` (DRAFT_SCHEMA에 맞는 payload; 기본 body는 `readable_body("draft")`, title `"Twins at Work"`, sources `[{"title": "A page", "url": "https://example.com"}]`, images `[{"image_url": "https://example.com/plant.jpg", "page_url": "https://example.com", "credit": "Example", "shows": "A factory floor with a screen showing its twin."}]`); `sample_finish(figures: list[dict] | None = None) -> dict` (FINISH_SCHEMA에 맞는 payload; `sample_draft()`의 topic, questions, translation, picture, paragraph_picture, vocabulary와 주어진 figures, 기본은 빈 목록).

- [ ] **Step 1: Write the failing tests in `backend/tests/test_passes.py`**

```python
import jsonschema
import pytest

from app.generation.passes import DRAFT_SCHEMA, FINISH_SCHEMA, TEXT_SCHEMA, ArticleText, FirstDraft, Finish, assemble, parse
from app.llm import GenerationError
from tests.conftest import sample_finish, sample_first_draft

CANDIDATE = {"after": 0, "image_url": "https://example.com/plant.jpg", "page_url": "https://example.com", "credit": "Example", "caption": "The plant."}
STRANGER = {**CANDIDATE, "after": 2, "image_url": "https://elsewhere.example/x.jpg"}


def test_sample_payloads_fit_the_schemas_the_model_answers_in():
    jsonschema.validate(sample_first_draft(), DRAFT_SCHEMA)
    jsonschema.validate({"title": "t", "body": "b"}, TEXT_SCHEMA)
    jsonschema.validate(sample_finish([CANDIDATE]), FINISH_SCHEMA)


def test_the_finishing_pass_has_no_way_to_change_the_article():
    assert not {"title", "body", "sources"} & set(FINISH_SCHEMA["properties"])
    assert FINISH_SCHEMA["properties"]["vocabulary"]["minItems"] == FINISH_SCHEMA["properties"]["vocabulary"]["maxItems"] == 8


def test_the_draft_offers_image_candidates_without_placing_them():
    item = DRAFT_SCHEMA["properties"]["images"]["items"]
    assert set(item["required"]) == {"image_url", "page_url", "credit", "shows"} and "after" not in item["properties"]
    assert DRAFT_SCHEMA["properties"]["images"]["maxItems"] == 4


def test_the_session_takes_its_text_from_the_last_edit_its_sources_from_the_draft_and_the_rest_from_the_finish():
    first = parse(FirstDraft, sample_first_draft())
    final = ArticleText(title="Final title", body="Final body.")
    draft = assemble(final, first, parse(Finish, sample_finish([CANDIDATE])))
    assert (draft.article.title, draft.article.body) == ("Final title", "Final body.")
    assert draft.article.sources == first.sources
    assert len(draft.vocabulary) == 8 and draft.article.figures[0].image_url == CANDIDATE["image_url"]


def test_an_image_the_draft_never_saw_is_dropped():
    draft = assemble(ArticleText(title="t", body="b"), parse(FirstDraft, sample_first_draft()), parse(Finish, sample_finish([STRANGER, CANDIDATE])))
    assert [f.image_url for f in draft.article.figures] == [CANDIDATE["image_url"]]


def test_a_payload_that_fails_validation_raises():
    with pytest.raises(GenerationError, match="validation"):
        parse(FirstDraft, {"title": "x"})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_passes.py`
Expected: `ModuleNotFoundError: No module named 'app.generation.passes'`.

- [ ] **Step 3: Implement `passes.py`, move `VOCABULARY_COUNT`, add the two conftest helpers**

Run first: `node .gitnexus/run.cjs impact "VOCABULARY_COUNT" --direction upstream --repo .`

- [ ] **Step 4: Run them to verify they pass**

Run: `cd backend && .venv/bin/pytest -q tests/test_passes.py tests/test_generator.py tests/test_jobs.py 2>&1 | grep -E "FAILED|passed|failed"`
Expected: 모두 통과.

- [ ] **Step 5: detect-changes 후 Commit**

```bash
node .gitnexus/run.cjs detect-changes --scope all --repo .
git add backend/app/generation/passes.py backend/app/generation/generator.py backend/tests/test_passes.py backend/tests/conftest.py
git commit -m "feat: each article pass has its own output, and the session is put together from them"
```

---

### Task 4: 단계별 프롬프트와 스킬

**Files:**
- Create: `backend/app/generation/prompts.py`
- Create: `backend/plugin/skills/stop-slop/` (`/home/humanoid/repositories/study-companion/app/plugin/skills/stop-slop`을 `cp -r`로 그대로 복사)
- Modify: `backend/plugin/skills/session-writing/SKILL.md`
- Test: `backend/tests/test_prompts.py`

**Interfaces:**
- Consumes: `readability`의 네 상수; `passes`의 `ArticleText`, `ImageCandidate`, `VOCABULARY_COUNT`; `app.generation.levels.describe_levels`; `app.pictures.scenes`의 `SCENE_RULES`, `CAPTION_RULES`.
- Produces (`prompts.py`):
  - `APP_SKILL = "english-session:session-writing"`, `HUMANIZER_SKILL = "english-session:humanizer"`, `STOP_SLOP_SKILL = "english-session:stop-slop"` (`generator.py`의 `APP_SKILL`, `ARTICLE_SKILL`을 대신한다).
  - `READER: str`, `CHECK_ITEMS_RULE: str` (`generator.py`에서 그대로 옮긴다), `REPAIR_ACTIVITY = "Fixing sentence and paragraph lengths"`.
  - `limits() -> str`
  - `draft_prompt(topic: str) -> str`
  - `edit_prompt(text: ArticleText) -> str`
  - `polish_prompt(text: ArticleText) -> str`
  - `repair_prompt(text: ArticleText, problems: list[str]) -> str`
  - `finish_prompt(topic: str, text: ArticleText, images: list[ImageCandidate], levels: tuple[str, ...], check_items: bool) -> str`
  - `_named`, `_spread`는 `generator.py`에서 옮긴다.

**프롬프트 문구.** 아래 블록은 확정 문구다. `{...}`는 format 자리다. title과 body는 어느 프롬프트에서나 `Title: {title}\n\nBody:\n{body}` 형식으로 넣는다 (블록의 `Title: ...`, `Body: ...` 자리).

```python
READER = (
    "Who reads this: Korean graduate students at about B2 level. They read the article aloud in turns, "
    "one paragraph each, until the whole article has been read, then discuss it. The article part of the session "
    "lasts ten minutes, reading included. Each sentence must make sense on one reading at speaking pace, and each "
    "paragraph is one person's turn, so the paragraphs stay close in length."
)

def limits() -> str:  # "Limits: every sentence at most 20 words. 4 to 5 paragraphs separated by blank lines, each 50 to 65 words. At most 2 figures per paragraph, not counting a bare year."
```

`draft_prompt` 문구:

```
Before writing, invoke the {APP_SKILL} skill with the Skill tool and follow its instructions.

You are writing the article for a 30-minute English conversation practice session. Topics rotate across computer science, industrial engineering, economics, AI, literature, world history, world affairs, Korean society, travel, and research life; treat each as a general-interest subject, not a specialist one.

{READER}

Today's article topic: {topic}

Write a draft of a short article for a smart general reader. Later passes shorten its sentences and polish it, but write to these limits from the start. {limits()}

Run at most 3 web searches, with firecrawl_search first and WebSearch only when firecrawl_search fails or finds nothing usable, to ground the article in accurate, current facts, and prefer a recent development or debate as the angle; never invent specifics you did not verify. Use a number only when the argument needs it, rounded the way a person would say it aloud. In sources, list only the web pages you actually drew on (page title and exact URL from the search results); leave it empty if you used none. Take a clear angle so there is something to discuss.

Then give images: up to 4 images you saw on the pages you drew on (firecrawl_scrape with the images format lists a page's images): a photo of the place, people, or thing, a diagram, or a map. Never a logo, ad, icon, author photo, or tracking pixel. Look through every page you drew on before giving fewer than 2. Put first the one that best shows what the whole article is about (often the lead photo of the main source). For each give image_url (the exact image address from the page), page_url (the page it was on), credit (the outlet or photographer the page names), and shows (one plain sentence on what the image shows). Leave images empty when no such image turned up.

Use American English. Return only the structured output.
```

`edit_prompt` 문구:

```
You are editing a short article so that it reads well aloud. {READER}

Edit the title and body below and return the whole article.

1. Sentences: at most {MAX_SENTENCE_WORDS} words each. One idea per sentence. At most one inserted phrase per sentence (an appositive, a parenthesis, or a clause set off by commas). Keep the subject close to its verb. Split a long sentence where its ideas divide, and keep the pieces connected so the paragraph does not read like a list of short claims.
2. Numbers: keep only the ones the angle needs, at most {NUMBERS_PER_PARAGRAPH} per paragraph, not counting a bare year. Round them the way a person would say them aloud: "about 150 theaters", "nearly a third", "in 2022". Keep an exact figure only when the exactness is the point. Give the day of a date only when the day matters to the story; otherwise give the year, or the month and year. Drop times of day unless they matter. A rounded figure must stay true: 153 becomes "about 150", never "nearly 200".
3. Names: keep the names the reader needs to follow the argument. A person named once whose name the claim does not need becomes their role ("a historian").
4. Paragraphs: {lo} to {hi} paragraphs separated by blank lines, each {wlo} to {whi} words. Each paragraph is one step of the argument and one reader's turn. Move, merge, or trim sentences to even them out.
5. Facts: you may drop, round, or reorder facts. Never add a fact, name, number, date, quote, or source.
6. Keep the angle stated early, the strongest case for one side, one concrete cost or objection, and an ending that does not settle the question.
7. Words: prefer the common word a B2 reader knows.

Title: ...
Body: ...

Return only the structured output.
```

`polish_prompt` 문구:

```
{READER}

Run the {HUMANIZER_SKILL} skill and then the {STOP_SLOP_SKILL} skill on the title and body below, in embedded mode: return only the final text. The article is a factual, third-person news piece, so its voice stays neutral and plain.

Keep the limits the article already meets. {limits()} Never add a fact, name, number, date, quote, or source, and keep every fact that is there. Keep the paragraphs as they are divided.

Where the skills ask for something these limits forbid, the limits win:
- "Be specific" means naming the actor and the thing. It never means adding a number, name, or date.
- Do not address the reader as "you" and do not put the reader in the scene; the article stays in the third person.
- Cut filler adverbs only, not every adverb.
- Vary sentence length within the {MAX_SENTENCE_WORDS}-word limit.

Title: ...
Body: ...

Return only the structured output.
```

`repair_prompt` 문구 (`problems`는 한 줄에 하나, 앞에 `- `):

```
{READER}

The article below breaks some of these limits. {limits()}

Fix only these problems:
- ...

Split each long sentence where its ideas divide. Bring each paragraph into range by moving a sentence to a neighbor or trimming words. Leave every other sentence word for word. Never add a fact, name, number, date, quote, or source. Do not use em dashes.

Title: ...
Body: ...

Return only the structured output.
```

`finish_prompt` 구성 (순서대로):
1. `Before writing, invoke the {APP_SKILL} skill with the Skill tool and follow its instructions while producing every part of the content.`
2. 지금 `PROMPT_TEMPLATE`의 첫 문단 그대로 ("You are preparing material for a 30-minute ... not a specialist one.").
3. `{READER}`
4. `Today's article topic: {topic}`
5. `The article below is final. Do not change it. Where a part asks you to copy from the article, copy from this text exactly.` 다음에 title과 body.
6. `Image candidates from the pages the article drew on:` 다음에 후보마다 한 줄 `- image_url: ...; page_url: ...; credit: ...; shows: ...`. 후보가 없으면 `Image candidates: none.`
7. `Produce two parts.`
8. `1. article parts:` 다음에 지금 `PROMPT_TEMPLATE`의 문장을 그대로 옮긴다: "Write 3 discussion questions."로 시작하는 질문 부분(지금의 "Then write 3 discussion questions" 문장의 "Then "만 뺌)부터 "Its evidence is an empty list."까지, 그리고 "Then give translation:"부터 "keep names, figures, and dates as they are."까지.
9. figures 문장은 이렇게 바꾼다: `Then give figures: up to 2 of the image candidates above, with image_url, page_url, and credit copied exactly.` 그 뒤에 지금 문장 "The first is the cover, shown under the title:"부터 "Leave figures empty when no such image turned up."까지를 옮기되, "For each give after, image_url (the exact image address from the page), page_url (the page it was on), credit (the outlet or photographer the page names), and caption"은 "For each give after, image_url, page_url, credit, and caption"으로 줄이고, "Leave figures empty when no such image turned up."은 "Leave figures empty when no candidate fits."로 바꾼다.
10. "Always give picture too:"부터 "so that the article always shows exactly 2 images."까지 그대로.
11. "2. vocabulary:" 부분 그대로 (`{vocabulary_count}`, `{vocabulary_levels}`, `{level_spread}`, `{scene_rules}`, `{caption_rules}` 자리 포함).
12. `Set topic to the article topic. Use American English. Return only the structured output.`
13. `check_items`가 참이면 끝에 `CHECK_ITEMS_RULE`.

**`session-writing/SKILL.md` 수정** (나머지 줄은 그대로):
- 8행을 바꾼다: `The readers are Korean graduate students at about B2. They read the article aloud in turns, one paragraph each, until the whole article has been read, then reuse its words and argue about it for ten minutes. Write so that works: clear enough to follow on one reading at a speaking pace, natural enough to copy, concrete enough to argue about.`
- 15행을 바꾼다: `- **Concrete over vague.** Name the actor, the place and the mechanism from your searches. Use a number only when the argument needs it, rounded the way you would say it aloud ("about 150", "nearly a third"). Never invent a figure; drop the claim if you could not verify it.`
- 16행을 바꾼다: `- **Sentence length.** One idea per sentence. Nothing a reader has to parse twice. The prompt gives the sentence and paragraph limits, and they win. Vary the rhythm within them.`
- 55~60행의 제목을 `## Before returning the structured output`으로 바꾸고, 3번 항목("Replace every vague noun ...")을 지운다. 남은 항목 번호를 1~3으로 다시 매긴다.

- [ ] **Step 1: Write the failing tests in `backend/tests/test_prompts.py`**

```python
import pytest

from app.generation.generator import PLUGIN_DIR
from app.generation.passes import ArticleText, ImageCandidate
from app.generation.prompts import (
    APP_SKILL, CHECK_ITEMS_RULE, HUMANIZER_SKILL, READER, STOP_SLOP_SKILL,
    draft_prompt, edit_prompt, finish_prompt, polish_prompt, repair_prompt,
)

TEXT = ArticleText(title="Twins at Work", body="First paragraph.\n\nSecond paragraph.")
IMAGE = ImageCandidate(image_url="https://example.com/plant.jpg", page_url="https://example.com", credit="Example", shows="A factory floor.")
LEVELS = ("B2", "B2+", "C1")


def every_prompt() -> list[str]:
    return [
        draft_prompt("Digital twins"), edit_prompt(TEXT), polish_prompt(TEXT),
        repair_prompt(TEXT, ["Paragraph 1 has 2 words (range 50 to 65)."]), finish_prompt("Digital twins", TEXT, [IMAGE], LEVELS, False),
    ]


def test_every_pass_is_told_who_reads_the_article_and_how():
    assert all(READER in prompt for prompt in every_prompt())
    assert "aloud in turns, one paragraph each" in READER


def test_the_edits_carry_the_limits_from_the_readability_constants():
    for prompt in (edit_prompt(TEXT), polish_prompt(TEXT), repair_prompt(TEXT, ["x"])):
        assert "at most 20 words" in prompt and "50 to 65 words" in prompt and "4 to 5 paragraphs" in prompt
    assert "at most 2 per paragraph, not counting a bare year" in edit_prompt(TEXT)
    assert '"about 150 theaters"' in edit_prompt(TEXT) and "Never add a fact" in edit_prompt(TEXT)


def test_the_article_text_goes_into_the_editing_passes():
    for prompt in (edit_prompt(TEXT), polish_prompt(TEXT), repair_prompt(TEXT, ["x"]), finish_prompt("t", TEXT, [], LEVELS, False)):
        assert "Title: Twins at Work" in prompt and "First paragraph.\n\nSecond paragraph." in prompt


def test_the_polish_runs_both_skills_and_says_where_the_limits_win():
    prompt = polish_prompt(TEXT)
    assert prompt.index(HUMANIZER_SKILL) < prompt.index(STOP_SLOP_SKILL)
    assert '"Be specific"' in prompt and "third person" in prompt and "filler adverbs" in prompt and "embedded mode" in prompt


def test_the_repair_names_each_problem_and_leaves_the_rest_alone():
    prompt = repair_prompt(TEXT, ['Sentence of 25 words (limit 20): "Long."', "Paragraph 2 has 70 words (range 50 to 65)."])
    assert '- Sentence of 25 words (limit 20): "Long."\n- Paragraph 2 has 70 words (range 50 to 65).' in prompt
    assert "word for word" in prompt


def test_the_draft_researches_and_collects_images_but_places_nothing():
    prompt = draft_prompt("Digital twins")
    assert f"invoke the {APP_SKILL} skill" in prompt and "Today's article topic: Digital twins" in prompt
    assert "firecrawl_search first" in prompt and "firecrawl_scrape" in prompt and "Never a logo" in prompt
    assert "after 0" not in prompt and "discussion questions" not in prompt and "vocabulary" not in prompt
    assert "Names, dates, numbers" not in prompt and "(dates, names, figures)" not in prompt


def test_the_finish_keeps_the_article_and_picks_figures_from_the_candidates():
    prompt = finish_prompt("Digital twins", TEXT, [IMAGE], LEVELS, False)
    assert "The article below is final. Do not change it." in prompt
    assert "- image_url: https://example.com/plant.jpg; page_url: https://example.com; credit: Example; shows: A factory floor." in prompt
    assert prompt.index("Write 3 discussion questions") < prompt.index("Then give translation") < prompt.index("Then give figures") < prompt.index("Always give picture") < prompt.index("2. vocabulary")
    assert "after 0" in prompt and "Image candidates: none." in finish_prompt("t", TEXT, [], LEVELS, False)


def test_the_item_check_rule_rides_only_on_the_finish():
    assert CHECK_ITEMS_RULE in finish_prompt("t", TEXT, [], LEVELS, True)
    assert all(CHECK_ITEMS_RULE not in prompt for prompt in every_prompt())


@pytest.mark.parametrize(
    ("levels", "asked"),
    [
        (("B2", "B2+", "C1"), "8 words at CEFR levels B2, B2+ and C1 connected to the topic. Spread them about evenly across these levels."),
        (("B1",), "8 words at CEFR level B1 connected to the topic. Draw"),
    ],
)
def test_the_words_come_from_every_level_set_by_name(levels, asked):
    assert asked in finish_prompt("t", TEXT, [], levels, False)


def test_stop_slop_is_vendored_unchanged_with_its_license():
    skill = PLUGIN_DIR / "skills" / "stop-slop"
    assert (skill / "SKILL.md").read_text().startswith("---\nname: stop-slop\n")
    assert (skill / "LICENSE").is_file() and "hardikpandya/stop-slop" in (skill / "SOURCE.md").read_text()
    assert all((skill / "references" / name).is_file() for name in ("phrases.md", "structures.md", "examples.md"))


def test_session_writing_no_longer_asks_for_more_numbers():
    text = (PLUGIN_DIR / "skills" / "session-writing" / "SKILL.md").read_text()
    assert "Specific over general" not in text and "Mostly 12 to 22 words" not in text
    assert "aloud in turns, one paragraph each" in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_prompts.py`
Expected: `ModuleNotFoundError: No module named 'app.generation.prompts'`.

- [ ] **Step 3: Implement `prompts.py`, copy stop-slop, edit `session-writing/SKILL.md`**

`generator.py`의 `PROMPT_TEMPLATE`, `CHECK_ITEMS_RULE`, `SKILLS_PREAMBLE`, `_named`, `_spread`, `APP_SKILL`, `ARTICLE_SKILL`은 이 태스크에서 옮기거나 지우지 않는다. Task 5가 `generator.py`를 다시 쓰면서 지운다. 이 태스크의 `prompts.py`는 `PROMPT_TEMPLATE`에서 문장을 복사해 만든다.

- [ ] **Step 4: Run them to verify they pass**

Run: `cd backend && .venv/bin/pytest -q tests/test_prompts.py`
Expected: 12 passed.

- [ ] **Step 5: detect-changes 후 Commit**

```bash
node .gitnexus/run.cjs detect-changes --scope all --repo .
git add backend/app/generation/prompts.py backend/plugin/skills/stop-slop backend/plugin/skills/session-writing/SKILL.md backend/tests/test_prompts.py
git commit -m "feat: prompts for the draft, read-aloud edit, polish, repair and finish passes, with stop-slop vendored"
```

---

### Task 5: 생성기가 단계를 차례로 부른다

**Files:**
- Modify: `backend/app/generation/generator.py` (`ClaudeGenerator`, 상수 정리)
- Modify: `backend/tests/fake_claude.py` (`ScriptedQuery` 추가)
- Test: `backend/tests/test_generator.py` (다시 쓴다)

**Interfaces:**
- Consumes: Task 1의 `problems`; Task 2의 `Stage`, `StreamTracker.begin`; Task 3의 `ArticleText`, `FirstDraft`, `Finish`, `DRAFT_SCHEMA`, `TEXT_SCHEMA`, `FINISH_SCHEMA`, `parse`, `assemble`, `VOCABULARY_COUNT`; Task 4의 프롬프트 함수, 스킬 이름, `REPAIR_ACTIVITY`.
- Produces:
  - `ClaudeGenerator.__init__`의 인자는 그대로다 (`model`, `effort`, `firecrawl_key`, `timeout_s`, `levels`). `self.claude`는 없어지고 네 개의 `Claude`가 생긴다. 모두 `model`, `effort`, `timeout_s`, `partial=True`를 쓴다.
    - `self.drafter`: `tools=("Read", *WEB_TOOLS)`, `mcp=(firecrawl(firecrawl_key),)`, `skills=(APP_SKILL,)`, `plugins=(str(PLUGIN_DIR),)`.
    - `self.editor`: 도구, MCP, 스킬, 플러그인 없음. 2단계와 고치기가 쓴다.
    - `self.polisher`: `tools=("Read",)`, `skills=(HUMANIZER_SKILL, STOP_SLOP_SKILL)`, `plugins=(str(PLUGIN_DIR),)`.
    - `self.finisher`: `tools=("Read",)`, `skills=(APP_SKILL,)`, `plugins=(str(PLUGIN_DIR),)`.
  - `generate(topic, on_progress=None, exclude=None) -> Draft`는 아래 흐름만 말한다. 각 단계의 실행, 로그, 파싱은 private 메서드가 맡는다.

```python
tracker = StreamTracker(on_progress or (lambda _: None))
first = self._draft(topic, tracker)
edited = self._edit(first, tracker)
polished = self._polish(edited, tracker)
final = self._fix_lengths(polished, tracker)
finish = self._finish(topic, final, first.images, exclude, tracker)
return assemble(final, first, finish)
```

  - 1단계는 `begin`을 부르지 않는다 (tracker의 첫 단계가 DRAFTING이고, 첫 메시지 전까지는 STARTING이 보인다). 2단계는 `tracker.begin(Stage.EDITING)`, 3단계는 `begin(Stage.POLISHING)`, 고치기는 `begin(Stage.POLISHING, REPAIR_ACTIVITY)`, 4단계는 `begin(Stage.FINISHING)`으로 시작한다.
  - 각 호출 앞에 `log.info("session pass: %s", <단계 이름>)`을 남긴다 (`drafting`, `editing`, `polishing`, `repair`, `finishing`). `Claude.run`의 비용 로그가 그 뒤에 이어진다.
  - `_fix_lengths(text, tracker) -> ArticleText`: `problems(text.body)`가 비면 `log.info("readability: clean after polishing")` 후 `text`. 아니면 고치기를 한 번 부른다. 고치기의 `GenerationError`는 `log.warning`으로 남기고 `text`를 돌려준다. 고친 결과의 항목 수가 원래 항목 수 이하이면 고친 결과, 아니면 `text`를 쓴다. `log.info("readability: %d problems after polishing, %d after repair", ...)`를 남기고, 쓰는 쪽에 항목이 남았으면 `log.warning("readability: still %s", 남은 항목)`.
  - `check_items` MCP 서버는 `exclude`가 있을 때 4단계 호출의 `extra`로만 붙는다 (지금 `check_items_server` 그대로).
  - `generator.py`에서 `PROMPT_TEMPLATE`, `SESSION_SCHEMA`, `SKILLS_PREAMBLE`, `CHECK_ITEMS_RULE`, `_named`, `_spread`, `APP_SKILL`, `ARTICLE_SKILL`을 지운다. `check_items_reply`, `check_items_server`, `PLUGIN_DIR`, `TIMEOUT_S`, `Generator`, `OnProgress`는 남는다. `VOCABULARY_COUNT`는 `passes`에서 import한 이름으로 남는다.
- Produces (`fake_claude.py`): `class ScriptedQuery(FakeQuery)`: `__init__(self, *scripts: tuple)`. `i`번째 호출은 `scripts[i]`의 메시지를 돌려준다. 스크립트보다 호출이 많으면 `AssertionError("more calls than scripts")`. `calls`는 `FakeQuery`처럼 `(prompt, options)`를 쌓는다.

- [ ] **Step 1: Impact 확인**

Run: `node .gitnexus/run.cjs impact "ClaudeGenerator" --direction upstream --repo .` 와 `node .gitnexus/run.cjs impact "generate" --direction upstream --repo .`
Expected: 호출자는 `wiring.py`의 `build_services`와 `jobs.py`의 `_generate`(Protocol 경유)다. `generate`의 시그니처가 바뀌지 않으므로 `jobs.py`는 그대로다. 위험도를 보고한다.

- [ ] **Step 2: Write the failing tests in `backend/tests/test_generator.py`**

파일을 다시 쓴다. `test_check_items_names_close_variants_of_taught_words`는 그대로 남긴다. 레벨 문구 테스트와 humanizer 순서 테스트, schema 테스트는 Task 3·4로 옮겨졌으므로 지운다. 공통 도우미:

```python
def generator_with(fake, **kwargs) -> ClaudeGenerator:
    gen = ClaudeGenerator(model="sonnet", **kwargs)
    for claude in (gen.drafter, gen.editor, gen.polisher, gen.finisher):
        object.__setattr__(claude, "query", fake)
    return gen


def passes(*, draft=None, edit=None, polish=None, repair=None, finish=None) -> ScriptedQuery:
    """One script per call, in order; `repair` only when given."""
    scripts = [
        draft or (result(sample_first_draft()),),
        edit or (result({"title": "Twins at Work", "body": readable_body("edited")}),),
        polish or (result({"title": "Twins at Work", "body": readable_body("polished")}),),
        *([repair] if repair else []),
        finish or (result(sample_finish()),),
    ]
    return ScriptedQuery(*scripts)
```

테스트 (이름과 assert):

```python
def test_the_article_goes_through_draft_edit_polish_and_finish_in_order():
    fake = passes()
    draft = generator_with(fake).generate("Digital twins")
    prompts = [prompt for prompt, _ in fake.calls]
    assert len(prompts) == 4
    assert "Today's article topic: Digital twins" in prompts[0]
    assert readable_body("draft") in prompts[1] and readable_body("edited") in prompts[2] and readable_body("polished") in prompts[3]
    assert draft.article.body == readable_body("polished") and draft.article.sources[0].url == "https://example.com"
    assert "session" not in fake.calls[3][1].mcp_servers  # no past words, no check tool


def test_each_pass_runs_with_its_own_tools_and_skills():
    fake = passes()
    generator_with(fake).generate("x", exclude=Exclusions(("scrutiny",)))
    (_, drafting), (_, editing), (_, polishing), (finishing_prompt, finishing) = fake.calls
    assert drafting.skills == [APP_SKILL] and "WebSearch" in drafting.allowed_tools and "firecrawl" in drafting.mcp_servers
    assert (editing.tools, editing.allowed_tools, editing.mcp_servers, editing.skills) == ([], [], {}, None)
    assert polishing.skills == [HUMANIZER_SKILL, STOP_SLOP_SKILL] and polishing.tools == ["Read", "Skill"]
    assert finishing.skills == [APP_SKILL] and "session" in finishing.mcp_servers and "session" not in drafting.mcp_servers
    assert CHECK_ITEMS_RULE in finishing_prompt and "scrutiny" not in finishing_prompt
    assert all(o.plugins == [{"type": "local", "path": str(PLUGIN_DIR)}] for o in (drafting, polishing, finishing))


def test_every_pass_keeps_the_ten_minute_limit():
    gen = ClaudeGenerator(model="opus")
    assert {c.timeout_s for c in (gen.drafter, gen.editor, gen.polisher, gen.finisher)} == {600}


def test_a_long_sentence_gets_one_repair_that_names_it():
    long = " ".join(["Long"] + ["word"] * 24) + "."
    polished = readable_body("polished").replace("Polished", long + " Polished", 1)
    fake = passes(
        polish=(result({"title": "t", "body": polished}),),
        repair=(result({"title": "t", "body": readable_body("repaired")}),),
    )
    draft = generator_with(fake).generate("x")
    assert len(fake.calls) == 5
    assert f'Sentence of 25 words (limit 20): "{long}"' in fake.calls[3][0]
    assert fake.calls[3][1].skills is None  # the repair runs on the editor
    assert draft.article.body == readable_body("repaired")


def test_a_repair_that_leaves_more_problems_is_set_aside():
    long = " ".join(["Long"] + ["word"] * 24) + "."
    polished = readable_body("polished").replace("Polished", long + " Polished", 1)
    fake = passes(
        polish=(result({"title": "t", "body": polished}),),
        repair=(result({"title": "t", "body": "One.\n\nTwo.\n\nThree."}),),  # 4 problems against the polished 2
    )
    assert generator_with(fake).generate("x").article.body == polished


def test_a_failed_repair_keeps_the_polished_article_and_goes_on():
    long = " ".join(["Long"] + ["word"] * 24) + "."
    polished = readable_body("polished").replace("Polished", long + " Polished", 1)
    fake = passes(polish=(result({"title": "t", "body": polished}),), repair=(result(is_error=True, text="overloaded"),))
    draft = generator_with(fake).generate("x")
    assert draft.article.body == polished and len(fake.calls) == 5


def test_a_cancel_during_the_repair_is_not_swallowed():
    long = " ".join(["Long"] + ["word"] * 24) + "."
    polished = readable_body("polished").replace("Polished", long + " Polished", 1)
    thinking = stream({"type": "content_block_start", "content_block": {"type": "thinking"}})
    fake = passes(polish=(result({"title": "t", "body": polished}),), repair=(thinking, result({"title": "t", "body": polished})))
    seen: list[Progress] = []

    def cancel_in_repair(progress):
        """Lets the repair start, then cancels on its first message, inside the Claude run."""
        seen.append(progress)
        if any(p.activity == REPAIR_ACTIVITY for p in seen[:-1]):
            raise Cancelled

    with pytest.raises(Cancelled):
        generator_with(fake).generate("x", on_progress=cancel_in_repair)


def test_a_failed_edit_fails_the_whole_generation():
    fake = passes(edit=(result(is_error=True, text="overloaded"),))
    with pytest.raises(GenerationError, match="overloaded"):
        generator_with(fake).generate("x")
    assert len(fake.calls) == 2


def test_a_draft_that_fails_validation_raises():
    with pytest.raises(GenerationError, match="validation"):
        generator_with(passes(draft=(result({"title": "x"}),))).generate("x")


def test_progress_runs_through_the_passes_in_order():
    fake = passes(draft=(assistant(tool_use("WebSearch")), assistant(text()), result(sample_first_draft())))
    seen: list[Progress] = []
    generator_with(fake).generate("x", seen.append)
    order = [p.stage for p in seen]
    assert [s for i, s in enumerate(order) if i == 0 or order[i - 1] != s] == [
        Stage.SEARCHING, Stage.DRAFTING, Stage.EDITING, Stage.POLISHING, Stage.FINISHING,
    ]
```

`Cancelled`는 `app.generation.jobs`에서 import한다. `result(is_error=True, text=...)`는 `Claude.run`에서 `GenerationError(result.result)`가 된다.

- [ ] **Step 3: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest -q tests/test_generator.py 2>&1 | grep -E "FAILED|passed|failed|Error"`
Expected: `ImportError` (`ScriptedQuery`, `HUMANIZER_SKILL` 등) 또는 `AttributeError: 'ClaudeGenerator' object has no attribute 'drafter'`.

- [ ] **Step 4: `ScriptedQuery`를 더하고 `ClaudeGenerator`를 위 Interfaces대로 다시 쓴다**

- [ ] **Step 5: Run the whole backend suite**

Run: `cd backend && .venv/bin/pytest -q 2>&1 | grep -E "FAILED|passed|failed"`
Expected: 실패 없음. 숫자가 기준선에서 늘어난 만큼이 새 테스트 수와 맞는지 본다.

- [ ] **Step 6: 남은 이름 확인**

Run: `git grep -n "PROMPT_TEMPLATE\|SESSION_SCHEMA\|ARTICLE_SKILL\|SKILLS_PREAMBLE\|Stage.WRITING\|'writing'" -- backend frontend/src`
Expected: 출력 없음.

- [ ] **Step 7: detect-changes 후 Commit**

```bash
node .gitnexus/run.cjs detect-changes --scope all --repo .
git add backend/app/generation/generator.py backend/tests/fake_claude.py backend/tests/test_generator.py
git commit -m "feat: the generator writes the article in passes and repairs sentence and paragraph lengths once"
```

---

### Task 6: 실제 생성 확인, 문서, 리뷰, 합치기

**Files:**
- Modify: `docs/superpowers/specs/2026-11-05-article-passes-design.md` (상태 줄)

- [ ] **Step 1: 브랜치 코드로 실제 주제 하나를 생성한다**

호스트의 `backend/.venv`에서 돈다. 운영 컨테이너와 DB를 건드리지 않는다. 토큰은 `.env`에서 환경변수로만 넘기고 출력하지 않는다. firecrawl 키 없이도 돈다 (속도 제한만 있다).

```bash
cd backend && env $(grep '^CLAUDE_CODE_OAUTH_TOKEN=' ../.env) .venv/bin/python -c "
import logging; logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
from app.generation.generator import ClaudeGenerator
from app.generation.readability import problems, paragraphs, sentences, word_count
d = ClaudeGenerator().generate('How the EU asylum pact changed Mediterranean crossings')
print(d.article.title); print(d.article.body)
for i, p in enumerate(paragraphs(d.article.body), 1): print(i, word_count(p), [word_count(s) for s in sentences(p)])
print('problems:', problems(d.article.body)); print('figures:', [f.image_url for f in d.article.figures])
"
```

Expected: 단계별 `session pass:` 로그(4줄, 고치기가 돌면 5줄)와 각 `run:` 비용 로그, `readability:` 로그, 본문, 문단별 단어 수, `problems: []` (또는 남은 항목).

- [ ] **Step 2: 결과를 사용자에게 보여준다**

본문, 문단별·문장별 단어 수, 단계별 시간과 비용, 고치기가 돌았는지를 보여준다. 사용자가 기준 값이나 프롬프트를 바꾸자고 하면 그 변경을 해당 태스크의 테스트와 함께 고치고 Step 1을 다시 한다. 사용자의 확인 없이 Step 3으로 가지 않는다.

- [ ] **Step 3: spec 상태 줄을 바꾼다**

`- 상태: 설계 (2026-11-05).`를 `- 상태: 구현됨 (<날짜>).`로, `(작성 예정)`을 지운다. 구현 중 바뀐 것이 있으면 spec 본문도 고친다 (CLAUDE.md "문서와 기록은 항상 유동적이다").

```bash
git add docs/superpowers/specs/2026-11-05-article-passes-design.md docs/superpowers/plans/2026-11-05-article-passes.md
git commit -m "docs: the article passes are implemented"
```

- [ ] **Step 4: 새 서브에이전트 한 명이 브랜치 전체를 리뷰한다**

`superpowers:executing-plans`의 마지막 리뷰. 범위는 `git diff main...feat/article-passes`. 지적이 맞으면 고치고 테스트를 다시 돌린다.

- [ ] **Step 5: 전체 테스트, 합치기, 버전**

Run: `cd backend && .venv/bin/pytest -q 2>&1 | grep -E "FAILED|passed|failed"`, `cd frontend && npx vitest run 2>&1 | grep -E "Test Files|Tests|FAIL"`, `cd frontend && npx tsc -b --noEmit`
Expected: 실패 없음. 그다음에만:

```bash
node .gitnexus/run.cjs detect-changes --scope compare --base-ref main --repo .
git switch main && git merge --ff-only feat/article-passes && scripts/bump-version patch
```

push와 배포(`docker compose up -d --build`)는 사용자가 말할 때만 한다. 배포 전에는 돌고 있는 생성이 없는지 확인한다 (`docker compose logs backend --since 10m | grep -c 'POST /api/sessions HTTP'`와 `GET /api/jobs`).
