# SQLite 스키마 재설계 + Expression corpus 설계

- 상태: 구현 완료 (2026-10-26, 브랜치 `feat/schema-v2`). 실 데이터 이행은 배포할 때 시작 시 자동으로 일어난다. 구현 계획은 `docs/superpowers/plans/`.
- 범위: `backend/data/sessions.db` 스키마 v2, 그에 맞춘 repo·모델·API·프론트 수정, v1 → v2 마이그레이션. PostgreSQL 아님.

## 목적

| 문제 (v1) | 해결 (v2) |
|---|---|
| `sessions.content_json` 한 덩어리(기사+표현+어휘 14KB). 그림 하나 붙일 때마다 전체 재기록, 표현·어휘를 SQL로 못 봄 | 기사 필드는 컬럼, 단락·어휘·표현 연결은 행 |
| 표현을 세션마다 Claude가 새로 지음 | 미리 구축한 corpus(`expressions`)에서 고름. 세션은 `session_expressions`로 참조 |
| 같은 값이 두 곳: 단락 텍스트(body와 readings/summaries), 그림(파일명은 JSON, 시간·비용은 `image_stats`), `examples.expression` 텍스트, `stars` 텍스트 | 전부 FK 참조 |
| FK 없음, 삭제는 5개 테이블 수동, 세션 삭제 시 그림 파일 잔존 | FK + ON DELETE CASCADE, 삭제가 파일까지 지움 |
| job 단계별 소요시간 이력이 메모리 | `stage_times` 테이블 |
| 레거시 (`_carry_over_costs`, `_drop_removed`, readings "phrasing" 필터, `_json` 접미사) | 삭제. `PRAGMA user_version` 마이그레이션 |

## 원칙

1. **참조 우선.** 다른 곳에서 가리키거나 개별 갱신·조회하는 값은 행 + FK. 같은 값을 두 번 저장하지 않는다.
2. **JSON 컬럼은 통째 값만.** 부모 행과 항상 함께 읽고 쓰며 아무도 가리키지 않는 값(동의어 목록, 질문, 출처, 번역 쌍, 교정 결과, 피드백). 타입은 `TEXT`(SQLite에 JSON형 없음. `JSON`으로 선언하면 NUMERIC 친화성이라 `'3'`이 정수가 됨). 이름은 내용으로, `_json` 접미사 없음.
3. **corpus는 독립.** `expressions`는 표현 자체와 출처만. 배운 기록·별·태그는 다른 테이블.
4. **STRICT 테이블.** 타입 실수를 DB가 잡는다. boolean은 `INTEGER` 0/1.
5. 파생값은 저장하지 않는다. body = 단락 join, 그림 파일명 = `{pictures.id}.png`. 예외: `expressions.key`(정규화 phrase, UNIQUE용 정체성), `translation`의 `en`(한국어를 찾는 열쇠), `corrections` 안의 `word`(평가 결과 문서의 일부).

## 스키마 v2

```sql
PRAGMA foreign_keys = ON;   -- 연결마다
PRAGMA user_version = 2;

-- 세션과 기사. Article의 필드가 컬럼.
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,                -- ISO 8601 UTC
    topic_id    INTEGER NOT NULL REFERENCES topics(id),  -- v4. 직접 입력한 주제도 topics 행(category 'typed')
    title       TEXT    NOT NULL,
    note        TEXT    NOT NULL DEFAULT '',     -- 자유 메모 (v1 notes)
    questions   TEXT    NOT NULL,                -- JSON [{text, evidence: [..]}]
    sources     TEXT    NOT NULL,                -- JSON [{title, url}]
    translation TEXT    NOT NULL                 -- JSON [{en, ko}]
) STRICT;

CREATE TABLE paragraphs (                        -- body = text를 "\n\n"으로 join
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    UNIQUE (session_id, position)
) STRICT;

CREATE TABLE vocabulary (                        -- 그 기사에서 고른 단어, 그 뜻으로. 세션 소유
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position           INTEGER NOT NULL,
    word               TEXT    NOT NULL,
    pos                TEXT    NOT NULL,
    definition         TEXT    NOT NULL,
    synonyms           TEXT    NOT NULL,         -- JSON [str]
    example            TEXT    NOT NULL,
    korean             TEXT,
    scene              TEXT,
    caption            TEXT,
    picture_id         INTEGER REFERENCES pictures(id),   -- scene 그림
    example_picture_id INTEGER REFERENCES pictures(id),   -- example 그림
    starred            INTEGER NOT NULL DEFAULT 0,
    UNIQUE (session_id, position)
) STRICT;

-- corpus. 표현 자체와 출처만.
CREATE TABLE expressions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT    NOT NULL UNIQUE,          -- app.generation.exclusions.key(phrase)
    phrase     TEXT    NOT NULL,                 -- 표시형
    meaning    TEXT    NOT NULL,
    synonyms   TEXT    NOT NULL,                 -- JSON [str], 쉬운 말 풀이
    examples   TEXT    NOT NULL,                 -- JSON [str]
    usage_note TEXT    NOT NULL,
    korean     TEXT,
    setting    TEXT,                             -- casual | workplace | discussion | NULL(모름). 말하는 자리
    source     TEXT    NOT NULL,                 -- 출처 이름. 세션에서 옮긴 것은 'session'
    added_at   TEXT    NOT NULL
) STRICT;

CREATE TABLE session_expressions (               -- 배운 기록. 행이 있으면 가르친 것
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    expression_id INTEGER NOT NULL REFERENCES expressions(id),
    position      INTEGER NOT NULL,
    starred       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (session_id, expression_id),
    UNIQUE (session_id, position)
) STRICT;

-- 그린 그림 하나가 행 하나. 파일은 images/{id}.png. image_stats 대체.
CREATE TABLE pictures (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model      TEXT,                             -- NULL: v1에서 옮긴 그림 (모델 미상)
    seconds    REAL,
    cost       REAL
) STRICT;

-- 연습 기록
CREATE TABLE examples (                          -- 표현 또는 단어로 만든 문장. 둘 중 하나만
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at            TEXT    NOT NULL,
    session_expression_id INTEGER REFERENCES session_expressions(id) ON DELETE CASCADE,
    vocabulary_id         INTEGER REFERENCES vocabulary(id) ON DELETE CASCADE,
    user_text             TEXT    NOT NULL,
    coach_text            TEXT    NOT NULL,
    seconds               REAL    NOT NULL DEFAULT 0,
    CHECK ((session_expression_id IS NULL) <> (vocabulary_id IS NULL))
) STRICT;

CREATE TABLE readings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    paragraph_id INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    user_text    TEXT    NOT NULL,
    seconds      REAL    NOT NULL DEFAULT 0,
    corrections  TEXT                            -- JSON [Correction]; NULL = 교정 저장 전 기록
) STRICT;

CREATE TABLE summaries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    paragraph_id INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    user_text    TEXT    NOT NULL,
    feedback     TEXT    NOT NULL,               -- JSON SummaryFeedback
    seconds      REAL    NOT NULL DEFAULT 0
) STRICT;

-- 앱 상태
CREATE TABLE settings    (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE model_pins  (source TEXT NOT NULL, model TEXT NOT NULL, pinned_at TEXT NOT NULL, PRIMARY KEY (source, model)) STRICT;
CREATE TABLE model_lists (source TEXT PRIMARY KEY, fetched_at REAL NOT NULL, options TEXT NOT NULL) STRICT;  -- options: JSON [Option]
-- v4: 주제는 행. 큐레이션(카테고리별), 그날 뉴스('news'), 세션용 직접 입력('typed'). 텍스트는 한 번만
CREATE TABLE topics     (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL UNIQUE, category TEXT NOT NULL, added_at TEXT NOT NULL) STRICT;
-- v4: 그날의 뉴스 주제 목록을 참조로. 새로고침은 그날 목록을 통째로 바꾼다
CREATE TABLE topic_days (day TEXT NOT NULL, position INTEGER NOT NULL, topic_id INTEGER NOT NULL REFERENCES topics(id), PRIMARY KEY (day, position)) STRICT;
CREATE TABLE stage_times (id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT NOT NULL, seconds REAL NOT NULL, finished_at TEXT NOT NULL) STRICT;
```

인덱스: `paragraphs(session_id)`, `vocabulary(session_id)`, `session_expressions(session_id)`, `session_expressions(expression_id)`, `examples(session_expression_id)`, `examples(vocabulary_id)`, `readings(paragraph_id)`, `summaries(paragraph_id)`, `stage_times(stage, id)`, `sessions(topic_id)`, `topic_days(topic_id)`.

버전: v3에 `figures`, v4(2026-10-26)에 `topics`와 참조형 `topic_days`·`sessions.topic_id`. v3→v4 업그레이드는 날짜 붙은 백업(`.bak-v3-…`)을 남기고, 큐레이션 주제를 넣고(이후엔 코드가 아니라 DB가 원본, `app/topics/curated.py`는 시드), 뉴스 JSON과 세션 주제 텍스트를 참조로 바꾸고, foreign key를 끈 채 `sessions`를 다시 만든 뒤 키를 검사한다.

## 표현 선택 규칙

- 세션 저장 시 corpus에서 5개(`EXPRESSION_COUNT`). 생성기는 더 이상 표현을 쓰지 않는다 (프롬프트·스키마·`Exclusions.expressions` 제거. `check_items`는 단어만).
- 후보 = `session_expressions`에 한 번도 없는 표현. setting별로 돌아가며(NULL도 한 묶음) 무작위로 뽑아 섞는다.
- 안 배운 것이 5개 미만이면 가장 오래전에 배운 것(마지막 `sessions.created_at` 오름차순)으로 채운다. 표현에는 `REPEAT_ALLOWANCE` 안 씀(단어에만).
- corpus가 비어 있으면 표현 0개인 세션. 프론트는 Expressions 탭에 "corpus가 비어 있다" 안내.
- 주제 매칭 없음. 현재 프롬프트도 표현은 주제와 무관. 필요해지면 `expression_tags(expression_id, tag)` 추가.
- 마이그레이션 직후에는 corpus 38개가 전부 이미 배운 것이라, corpus를 채우기 전까지 새 세션은 가장 오래전 세션(12→13→14)의 표현을 다시 가르친다. owner 결정(2026-10-26): 감수한다. 생성기의 표현 코드는 지금 제거하고, 가져오기 도구는 다음 작업.

## 그림 흐름

- painter가 그림 하나당 `Drawn(png, model, seconds, cost)`를 돌려준다. painter는 DB를 건드리지 않고, 예상 시간용으로 `PictureStats.seconds(model)`만 읽는다.
- Illustrator가 `PictureRepo.add(model, seconds, cost)` → id → `PictureFiles.write(id, png)` → 콜백으로 id를 넘기면 JobRunner가 `SessionRepo.replace_picture(vocabulary_id, field, picture_id)`.
- 다시 그리기: 새 행·새 파일, vocabulary가 새 id를 가리킨 뒤 옛 파일 삭제. 옛 `pictures` 행은 남긴다(시간·비용 기록).
- 세션 삭제: `SessionRepo.delete`가 그 세션 vocabulary가 가리키던 picture id를 돌려주고, 라우트가 `PictureFiles.remove`. 행은 남긴다.
- 통계(`stats()`): 모델별 최근 20장 평균, `model IS NULL` 제외.
- 파일 작업은 `app/pictures/files.py`의 `PictureFiles(dir)` 하나가 맡는다. Illustrator와 삭제 라우트가 같이 쓴다. 정적 마운트 `/api/images`는 그대로.

## 모델 (app/models.py)

| 모델 | 역할 |
|---|---|
| `Draft` (topic, article: `ArticleDraft`(title, body, questions, sources, translation), vocabulary: `VocabularyDraft[]`) | 생성기 출력. id·그림·표현 없음 |
| `Session` (id, created_at, topic, content: `SessionContent`) | 저장·제공. `content` 중첩은 프론트 호환용으로 유지 |
| `SessionContent` (topic, expressions: `Expression[]`, article: `Article`, vocabulary: `VocabularyItem[]`) | |
| `Article` (title, paragraphs: `Paragraph(id, text)[]`, questions, sources, translation) | `body` 없음 |
| `Expression` (+ `id` = corpus id) | |
| `VocabularyItem` (+ `id`; `image`, `example_image`는 `"{picture_id}.png"` 파생) | |
| `Stars` (expressions: `int[]` corpus id, words: `int[]` vocabulary id) | |
| `Reading`, `Summary` (`paragraph_id`; `session_id`·`paragraph` 텍스트 없음) | |
| `Example` (`expression_id` corpus id 또는 `vocabulary_id`, 하나만) | |

## API 변경

| 엔드포인트 | 변경 |
|---|---|
| `GET /api/sessions/{id}` | 위 모델대로. `article.paragraphs`, 항목마다 `id` |
| `PUT /api/sessions/{id}/stars` | id 목록 |
| `POST /api/examples` | `{session_id, expression_id?, vocabulary_id?, user_text, coach_text, seconds}`. 하나만 |
| `POST /api/readings`, `POST /api/summaries` | `{paragraph_id, ...}`. `session_id`·`paragraph` 제거 |
| `GET /api/{examples,readings,summaries}?session_id=` | 그대로 |
| `POST /api/sessions/{id}/pictures/{index}` | 그대로 (index 기반) |
| 라이브 라운드(`/api/read-aloud/sessions`, `/api/summary/*`, `/api/example/*`) | 그대로. 단락·표현 텍스트를 코치에게 넘길 뿐 |

## 백엔드 모듈

| 파일 | 내용 |
|---|---|
| `app/db/schema.py` | DDL, 인덱스, `migrate(conn)`: `user_version` 0/1 → 2 |
| `app/db/__init__.py` | `Database`: 연결마다 `foreign_keys=ON`, 시작 시 migrate, repo 묶음 |
| `app/db/sessions.py` | `SessionRepo`: `create(draft, expression_ids)`, `get`, `exists`, `list_all`, `delete → picture ids`, `recent_topics`, `used_words`, `replace_picture`, `get_stars/set_stars`, `get_note/set_note` |
| `app/db/expressions.py` | `ExpressionRepo`: `add(...)`(key로 upsert), `get`, `pick(count, rng)`, `list_all` |
| `app/db/records.py` | `RecordRepo`: examples/readings/summaries, FK id로 |
| `app/db/pictures.py` | `PictureRepo`: `add → id`, `stats`, `seconds(model)` |
| `app/db/stages.py` | `StageRepo`: `add(stage, seconds)`, `recent(stage, n)` |
| `app/db/caches.py`, `pins.py`, `settings.py` | 컬럼명만 맞춤 |
| `app/pictures/files.py` | `PictureFiles(dir)`: `path(id)`, `write(id, png)`, `remove(id)` |
| `app/generation/generator.py` | 표현 제거. 출력 `Draft` |
| `app/generation/exclusions.py` | 단어만 |
| `app/generation/jobs.py` | `_stage_history` deque → `StageRepo`. 세션 생성 시 `expressions.pick` |
| `app/pictures/painters.py`, `illustrator.py` | `Drawn`, `PictureFiles`, `PictureRepo` |
| `app/api/schemas.py`, `records.py`, `sessions.py` | 위 API대로. 삭제 라우트가 파일 제거 |

## 마이그레이션 v1 → v2 (`Database` 시작 시, `user_version < 2`이고 `sessions` 테이블이 있을 때)

1. `sessions.db` → `sessions.db.bak-v1-<날짜>` 복사. 한 트랜잭션.
2. 새 테이블 생성. 옛 `sessions`는 `sessions_v1`로 rename.
3. 세션마다 `content_json` 파싱 → `sessions`(note는 `notes`에서), `paragraphs`(`\n\s*\n`으로 나누고 trim, 빈 것 제외), `vocabulary`(`starred` = `stars`에 word 있음).
4. 표현: `key(phrase)`로 `expressions` upsert(`source='session'`, `setting NULL`, `added_at` = 세션 `created_at`), `session_expressions`(`starred` = `stars`에 phrase 있음).
5. 그림: vocabulary의 `image`/`example_image` 파일명마다 `pictures` 행(`created_at` = 세션, model NULL). 파일이 없으면 FK NULL. `image_stats` 행 → `pictures` 행(파일 없음). 파일 rename(`{id}.png`)은 DB 트랜잭션 커밋 뒤에 한다. rename 실패는 경고 로그.
6. `readings`/`summaries`: 단락 텍스트 → 같은 세션 단락과 trim 비교, 안 맞으면 공백 정규화 비교, 그래도 없으면 버리고 경고 로그.
7. `examples`: `key(expression)` → 그 세션의 `session_expressions`, 아니면 그 세션의 vocabulary word. 없으면 버리고 경고.
8. `model_lists`: `list_json.at` → `fetched_at`, `.options` → `options`. `topic_days.topics_json` → `topics`. `settings` 행은 전부 그대로. v1의 `_drop_removed`가 시작마다 지우던 `SUMMARY_MODEL`은 살아 있는 설정(`config/settings.py`)이라 더는 지우지 않는다.
9. 옛 테이블 drop(`sessions_v1`, `stars`, `notes`, `image_stats`, 옛 records). `user_version = 2`.
10. `images/`에서 아무도 가리키지 않는 파일(지워진 세션의 것, 실 DB에 40개)은 수만 로그. 삭제도 rename도 안 함.

새 파일은 v2로 바로 생성. 레거시 함수 3종과 그 테스트는 삭제, 마이그레이션 테스트(v1 fixture DB 생성 → 열기 → 확인)로 대체.

## 프론트엔드

| 파일 | 변경 |
|---|---|
| `types.ts`, `api.ts` | 위 모델·요청 본문 |
| `ArticleTab.tsx`, `Paragraph.tsx`, `ReadAloud.tsx`, `Summarize.tsx` | `article.paragraphs` 사용, 쪼개기 삭제. `paragraph: {id, text}`. 저장 시 `paragraph_id` |
| `useReadingMarks.ts`, `SummaryTab.tsx` | `paragraph_id`로 키. 라벨은 `content.article.paragraphs`에서 찾음 |
| `useStars.ts`, `SessionPage.tsx`, `ExpressionsTab.tsx`, `VocabularyTab.tsx`, `StarButton` 호출부 | id로 별 토글, id로 examples 필터 |
| `Practice.tsx`, `PracticeTarget` | `expression_id` / `vocabulary_id` 들고 다님 |
| `ExpressionsTab.tsx` | 표현 0개 안내 |
| 테스트 | 위에 맞춤 |

## 실행 방식

- `app.main`은 import할 때 앱을 만들지 않는다. uvicorn은 `--factory app.main:default_app`으로 띄운다 (`backend/Dockerfile`, `compose.dev.yaml`). 테스트가 실제 `backend/data/sessions.db`를 열거나 이행하지 않게 하기 위해서다.
- 첫 기동 때 v1 파일이면 `sessions.db.bak-v1-<날짜>`로 복사한 뒤 이행하고, 결과를 `Report(...)` 한 줄로 로그에 남긴다.

## 비목표

- PostgreSQL. corpus 수집·가져오기 도구(다음 작업. `ExpressionRepo.add`만 제공. 출처 조사는 `docs/plans/2026-10-26-expression-corpus-sources.md`). `expression_tags`. 단어 corpus. 음성 캐시 색인. 실행 중 job 저장(재시작 복구 불가). 고아 그림 파일 삭제.

## 빌더에게 맡기는 것

- SQL 문장·인덱스 세부, 테스트 구성, 프론트 컴포넌트 내부 상태 처리, 마이그레이션 로그 문구.
- 커밋 단위. 권장: 스키마+repo+마이그레이션 / 생성기·그림 흐름 / API / 프론트 순.

## 검증

- `cd backend && uv run pytest`, `cd frontend && npm test`.
- 실제 `backend/data/sessions.db` 복사본으로 마이그레이션 실행 (2026-10-25 기준 수치): 세션 7, 단락 수 = body 단락 합, 표현 38(세션 12·13·14는 6개씩) → corpus 38행(중복 키 0), `image_stats` 133행 → 파일 없는 `pictures` 행, readings 42·summaries 5·examples 3 중 매칭 실패 0, `images/` 110개 중 vocabulary가 가리키는 70개가 `{id}.png`로 바뀌고 고아 40개는 그대로(로그에 수).
- 앱 띄워 세션 열기, 별·메모·읽기·요약·예문 저장, 다시 그리기, 세션 삭제 후 `images/` 파일 줄어듦 확인.
