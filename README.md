# english-speaking-claude

- 목표: 친구와 하루 30분 영어 회화 연습. 매 세션 표현 6개 + 짧은 아티클(기술 · 문학 · 세계사 · 최근 세계 이슈) + B2~C1+ 어휘 12개를 Claude가 생성.
- 상태: 진행 중 (v1 동작)
- 다음 할 일: 며칠 써보고 표현 난이도와 아티클 길이 조정

## 실행

```sh
./dev.sh          # backend :8765 + frontend :5173
```

`http://localhost:5173` 접속. 주제를 비워 두면 풀(`backend/app/topics.py`)에서 최근 10회에 안 나온 주제를 자동으로 고른다.

홈 화면 추천 주제 12개는 하루 단위로 바뀐다. 절반은 그날 뉴스에서 새로 뽑고, 절반은 고정 풀(기술 · 문학 · 세계사 · 세계 이슈)에서 날짜를 씨앗으로 고른다. 같은 날에는 몇 번을 새로고침해도 같은 12개가 나오고, 자정을 넘기면 바뀐다. 라벨 옆 `↻`를 누르면 그 자리에서 다시 뽑는다: 고정 풀 절반은 바로 새 조합으로 바뀌고, 뉴스 절반은 백그라운드로 다시 가져오는 동안 이전 목록이 남아 있다가 도착하면 바뀐다(`POST /api/topics/refresh`).

주제마다 카테고리(`news` · `tech` · `literature` · `history` · `world`)가 붙어 `/api/topics`에 `{text, category}`로 내려간다. 칩 색은 카테고리별로 다르고, 칩 아래 범례가 그날 나온 카테고리만 이름으로 보여준다. 색 정의는 `frontend/src/styles.css`의 `[data-category=...]` 규칙에 모여 있다.

뉴스 절반은 그날 처음 `/api/topics`를 호출할 때 백그라운드로 `claude` CLI를 한 번 돌려 받아 `topic_days` 테이블에 저장한다(하루 1회). 주요 외신 1면·톱 수준으로 크게 다뤄진 기사만 받는다(독립된 주요 매체 2곳 이상이 비중 있게 다룬 것이 기준). 웹 검색이 막혔거나 기준을 넘은 기사가 없으면 빈 목록을 돌려받고, 그날치를 저장하지 않아 다음 요청에서 다시 시도한다. 도착 전이나 실패했을 때는 12개 전부 고정 풀에서 채우므로 화면이 비지 않는다. `pending`은 백그라운드 fetch가 실제로 도는 동안만 참이다(실패하면 바로 거짓, 다음 페이지 로드에서 재시도). 프론트는 `pending`이 참인 동안 15초 간격으로 최대 3분간 다시 물어보고, 그 뒤엔 새로고침 버튼을 다시 연다. fetch가 실패하면 `error`에 이유(CLI 오류 메시지, 또는 검색 결과 없음)가 실려 오고, 홈 화면의 Today's topic 아래에 그대로 표시된다. 표현 6개는 주제와 무관한 B2~C1+ 범용 표현이고, 어휘 12개는 주제 연관 단어로 아티클 밖에서도 고른다. 최근 40세션에서 이미 나온 표현·단어는 프롬프트에 제외 목록으로 넘긴다. 각 항목은 10% 확률로 목록에서 빠져 가끔 다시 나올 수 있다(`JobRunner.REPEAT_ALLOWANCE`).

생성은 로컬 `claude` CLI(`claude -p --json-schema --output-format stream-json`)를 서브프로세스로 호출한다. `POST /api/sessions`는 202로 작업 ID를 돌려주고, 프론트가 `GET /api/jobs/{id}`를 1초마다 폴링해 단계(스킬 로드 → 웹 검색 n회 → 작성 → 구조 확인)와 진행 바를 보여준다. 작업은 서버 메모리에 살아 있으므로 홈에 다시 들어오면 `GET /api/jobs`(진행 중인 작업 목록)로 찾아 같은 진행 바를 이어서 보여준다. 퍼센트는 단계 하한 + 경과 시간(최근 5회 중앙값 기준) 추정이다. API 키 불필요, Claude 구독으로 처리. 1회 생성 약 1~2분(opus 기준). CLI에는 `Skill`, `Read`, 내장 `WebSearch`/`WebFetch`, firecrawl MCP(`firecrawl_search`, `firecrawl_scrape`)가 열려 있다. 검색은 firecrawl을 먼저 쓰고, firecrawl이 없거나(OAuth 만료 등) 실패하면 내장 `WebSearch`로 넘어간다. 아티클은 최대 3회 웹 검색으로 사실을 확인하고 최근 이슈를 각도로 잡는다. firecrawl은 호스트에서 `claude mcp add --transport http firecrawl https://mcp.firecrawl.dev/v2/mcp-oauth` 후 한 번 OAuth 로그인해 두면 된다. 토큰이 만료되면(`claude mcp list`가 `Needs authentication`을 보임) 호스트에서 `claude`를 열어 `/mcp` → firecrawl → Authenticate로 다시 로그인하고, `docker compose restart backend`로 자격증명을 다시 복사한다(컨테이너는 시작할 때 호스트 `.credentials.json`을 복사한다).

| 환경변수 | 기본값 | 용도 |
|---|---|---|
| `CLAUDE_MODEL` | `opus` | 생성 모델. `sonnet`이면 더 빠름 |
| `CLAUDE_EFFORT` | `xhigh` | reasoning effort. `low`, `medium`, `high`, `xhigh`, `max` |
| `CLAUDE_SKILLS` | 비움 | 생성 전에 호출할 스킬. 쉼표 구분. 예: `stop-slop,cotidie:write-like-me` |
| `DB_PATH` | `backend/data/sessions.db` | SQLite 파일 |
| `OPENAI_API_KEY` | 비움 | Read aloud 코치와 Ask 위젯용. 비우면 두 버튼이 503을 돌려준다 |
| `READ_ALOUD_AGENT_DIR` | `../read-aloud-coach` | 발음·끊어 읽기 코치 정의 폴더(프롬프트, 세션 설정) |
| `EXAMPLE_AGENT_DIR` | `../example-coach` | Your turn / Practice 코치 정의 폴더 |
| `PHRASE_AGENT_DIR` | `../phrase-coach` | 표현 코치 정의 폴더 |
| `SUMMARY_MODEL` | `gpt-5.6-luna` | Summary 탭에서 transcript를 정리하는 텍스트 모델 |
| `TOPICS_MODEL` | `sonnet` | 하루 한 번 뉴스에서 추천 주제를 뽑는 모델 |
| `TOPICS_EFFORT` | `medium` | 그 호출의 reasoning effort |
| `EXAMPLE_MODEL` | `opus` | Your turn / Practice 피드백을 쓰는 `claude` 모델 |
| `EXAMPLE_EFFORT` | `low` | 그 호출의 reasoning effort |

## Article 한국어 번역

세션을 만들 때 아티클 본문을 문장 단위로 번역해 함께 저장한다(`article.translation`, `{en, ko}` 쌍). 화면에서는 숨겨져 있다가 문장을 클릭하면 영어가 가라앉고 그 자리에 한국어가 떠오른다. 다시 클릭하면 영어로 돌아간다. 번역은 모델이 문단 전체를 보면서 문장별로 만들고, `en`이 본문에 글자 그대로 없는 쌍은 backend가 버리므로 그 문장은 영어로만 남는다. 번역이 없는 예전 세션은 클릭해도 아무 일도 없다.

## Read aloud (GPT-Live)

Article 탭의 문단마다 `Read aloud` 버튼이 있다. 누르면 브라우저 마이크가 GPT-Live(`gpt-live-1`)에 WebRTC로 붙고, 읽는 동안 원어민 코치가 듣다가 이상한 발음이나 구 안에서 잘못 끊어 읽은 곳이 나오면 문장 끝을 기다리지 않고 바로 끼어들어 고친다. 이 두 가지만 본다. 억양은 보지 않고 문단을 대신 읽어 주지도 않는다. `Finish`를 누르면 코치가 인사하고 끝내며, `Stop`은 바로 세션 종료. 분당 $0.05, 문단 하나에 약 $0.10.

에이전트 정의(프롬프트, 세션 설정, 검증 시나리오)는 `../read-aloud-coach/`에 있고 backend는 그 폴더를 읽기만 한다. backend `POST /api/read-aloud/sessions`가 브라우저의 SDP offer를 `POST https://api.openai.com/v1/live/sessions`에 중계한다. API 키는 backend 환경변수에만 둔다.

## Ask (GPT-Live)

어느 페이지에서든 화면 맨 아래 가는 선의 `Ask`를 누르거나 `A` 키를 치면 표현 코치가 붙는다. 입력칸에 커서가 있으면 단축키는 무시한다. "눈치 좀 챙기라는 말 영어로 어떻게 해?"처럼 한국어로 물어도 되고, 자기가 쓴 영어가 어색한지 확인해도 된다. 답은 표현 하나, 부연이 붙어도 짧은 한 문장, 10초 이내. 말하는 동안 막대 5칸짜리 표시가 마이크 입력 크기를 보여준다. 코치가 5초간 조용하면 라운드가 자동으로 끝나고, `Done`이나 `Esc`로 바로 끝내도 된다. 한 번에 약 $0.015.

말할 타이밍을 놓쳤거나 엉뚱하게 들어갔으면 `Retry`(`R`)로 그 자리에서 다시 시작한다. 앞 라운드는 버려지고 새 세션이 열리므로 15초 최소 과금이 다시 붙는다.

라운드가 끝나면 자막 두 줄이 쪽지에 남고, `Save`(`Enter`)를 눌러야 `asks` 테이블에 들어간다. 쓸모없는 답은 `Discard`(`Esc`)로 버린다. 세션 안에서 물었으면 그 세션에 묶이고, 홈에서 물었으면 세션 없이 남는다.

에이전트 정의는 `../phrase-coach/`에 있다. `../read-aloud-coach/`와 같은 규약이고, backend의 같은 `LiveAgent`가 둘 다 읽는다.

## Your turn / Practice (GPT-Live + claude CLI)

Expressions 탭의 표현마다 노란 `Your turn: one sentence each.` 라벨이, Vocabulary 탭의 카드마다 `Practice` 버튼이 있다. 둘 다 같은 `Practice` 컴포넌트다. 누르면 마이크가 붙고 참가자가 그 표현이나 단어로 문장 하나를 말한다. GPT-Live는 듣기와 읽어 주기만 맡는다: 문장이 끝나면 "Got it." 한마디, 그 첫 발화를 신호로 프론트가 사용자 transcript를 `POST /api/example/feedback`에 보낸다. backend는 `claude` CLI(`EXAMPLE_MODEL`, 기본 opus, `EXAMPLE_EFFORT` 기본 low, 도구 없음)에 `../example-coach/prompts/feedback.md`를 넣어 `paraphrase`(원어민이 말하는 대로 바꿔 말한 문장, 고칠 곳은 모두 고침)와 `feedback`(고친 곳마다 짧은 문장 하나씩의 목록) 두 필드를 받는다. 쪽지에서는 목록을 불릿으로 보여 준다. 답이 오는 동안 쪽지에 `Writing the native version…`이 뜨고 라운드는 닫히지 않는다(약 10초). 답이 오면 화면에 두 줄로 보이고, 같은 문장을 `session.instructions.append`로 넘겨 코치가 그대로 소리 내어 읽는다. 코치가 5초간 조용하면 라운드가 끝나고 `Keep`으로 그 표현 아래에 쌓인다. 쪽지 위의 `↻`는 처음부터 다시, `✕`는 듣는 중이든 끝난 뒤든 버린다. 텍스트 모델이 실패하면 오류가 쪽지에 그대로 뜨고 Keep은 잠긴다.

쌓인 문장은 `examples` 테이블에 세션·표현별로 남고, 새로고침해도 그 자리에 다시 나온다. 코치 줄은 Live transcript가 아니라 텍스트 모델의 두 필드를 `paraphrase`와 `feedback` 항목들을 공백으로 이은 한 줄로 저장한다. 첫 문장이 예문, 나머지가 피드백이라는 형식은 그대로다.

에이전트 정의는 `../example-coach/`에 있다. 다른 두 코치와 같은 규약이고, backend `POST /api/example/sessions`가 표현·뜻·노트를 채워 중계한다.

## Summary 탭

레일의 네 번째 항목. 세션이 남긴 것을 네 섹션으로 보여준다.

| 섹션 | 내용 | 원본 |
|---|---|---|
| Starred | 표현: 구문 / 뜻, 단어: 단어 · 품사 / 정의 (예문과 노트는 뺀 축약형) | `stars` 테이블 |
| Sentences you made | 표현·단어 / 참가자 문장 / 코치의 되풀이와 피드백 | `examples` 테이블 |
| Expressions you asked for | 물은 말 / 추천 표현 / 대안 / 노트 | `asks` 테이블 |
| Reading to fix | 들린 대로 / 원래 단어나 구 / 고칠 점. 끊어 읽기 교정은 `phrasing` 표시 | `readings` 테이블 |

Read aloud 라운드는 코치가 한마디라도 했으면 끝날 때 자동으로 `readings`에 저장된다(조용히 넘어간 라운드는 남길 게 없어 저장하지 않는다). Ask와 달리 저장 버튼이 없다.

탭을 처음 열 때 텍스트 모델이 두 번 돌아(카드용, 교정용) transcript를 정리하고 결과를 각 행에 캐시한다. 두 번째부터는 호출하지 않는다. 프롬프트와 스키마는 각 에이전트 폴더에 있다(`phrase-coach/cards.schema.json`, `read-aloud-coach/feedback.schema.json`).

홈의 `Asks` 링크는 세션과 무관하게 지금까지 물어본 표현 전체를 보여준다.

## Docker

```sh
cp .env.example .env               # 모델, 스킬, 포트 기입. 토큰은 비워도 된다
docker compose up -d --build
```

인증은 호스트의 `~/.claude/.credentials.json`(claude.ai 로그인 + firecrawl OAuth)을 컨테이너 시작 시 복사한다. 호스트에서 로그인이 바뀌면 `docker compose restart backend`. 호스트 로그인과 분리하려면 `claude setup-token` 값을 `.env`의 `CLAUDE_CODE_OAUTH_TOKEN`에 넣는다.

`http://localhost:5173` 접속. 포트가 겹치면 `.env`의 `FRONTEND_PORT`를 바꾼다.

| 서비스 | 내용 |
|---|---|
| backend | python 3.13 + uv + Claude Code 바이너리. `backend/data`를 `/data`로 마운트해 SQLite 유지 |
| frontend | Vite 빌드를 nginx로 서빙. `/api`를 backend:8765로 프록시, 타임아웃 600초 |

스킬은 호스트의 `~/.claude/skills`와 `~/.claude/plugins`를 읽기 전용으로 같은 경로에 마운트한다(플러그인 매니페스트가 절대경로를 쓰므로 컨테이너 HOME을 호스트와 맞춘다). 호스트 `settings.json`에서는 `enabledPlugins`만 가져오므로 훅과 권한 설정은 컨테이너 안에서 돌지 않는다. MCP는 `--strict-mcp-config`로 firecrawl(HTTP)만 붙인다.

## 세션 진행 (30분)

| 단계 | 시간 | 방법 |
|---|---|---|
| Expressions | 10분 | 표현 6개. 예문 읽고 용례 합의, 각자 문장 하나씩 |
| Article | 10분 | 3분 묵독 후 각자 요약, 질문 3개로 토론. 앞 2개는 본문 확인용, 마지막 1개는 의견 교환용 |
| Vocabulary | 10분 | 단어 + 예문만 보고 뜻을 영어로 설명, 카드 클릭해 확인 |
| Summary | 끝나고 | 별표한 표현·단어, 만든 문장, 물어본 표현, 지적받은 발음을 한 화면에서 확인 |

타이머 `Start 30 min`을 누르면 10분마다 탭이 자동으로 넘어간다.

## 구조

```
backend/   FastAPI. app/{main,generator,claude_cli,daily_topics,live,cards,store,topics,models}.py, tests/
frontend/  React 19 + Vite + TS. src/{pages,components,lib}. lib/liveClient.ts가 WebRTC
dev.sh     둘 다 띄우는 스크립트
```

## 테스트

```sh
cd backend && uv run pytest
cd frontend && npm test
```

설계 문서: `docs/superpowers/specs/2026-09-10-english-speaking-claude-design.md`
