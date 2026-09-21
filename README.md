# english-speaking-claude

- 목표: 친구와 하루 30분 영어 회화 연습. 매 세션 표현 5개 + 짧은 아티클(CS · 산업공학 · AI · 문학 · 세계사 · 세계 이슈 · 한국 · 연구 생활) + B2~C1+ 어휘 10개를 Claude가 생성.
- 상태: 진행 중 (v1 동작, Read aloud는 Azure 판정기 위에서 돎)
- 다음 할 일: Read aloud를 실제로 읽어 문단 위 표시와 클릭 시 코치 반응 확인(`../read-aloud-coach/evals/cases.md` 2번, 7번, 14번). 임계값 튜닝은 `docs/2026-09-21-assessor-benchmark.md`

## 실행

```sh
cp .env.example .env               # 처음 한 번. 키는 비워 두고 앱의 ⚙ 설정 모달에서 넣어도 된다
docker compose up -d --build
```

`http://localhost:5173` 접속. 두 컨테이너는 `restart: unless-stopped`라 컴퓨터를 재시작해도 Docker가 뜨면 같이 뜬다. `docker compose stop`으로 직접 끈 경우에만 재부팅 후에도 꺼진 채로 남는다. 주제를 비워 두면 풀(`backend/app/topics.py`)에서 최근 10회에 안 나온 주제를 자동으로 고른다.

홈 화면 추천 주제 12개는 하루 단위로 바뀐다. 3개는 그날 뉴스에서 새로 뽑고(`FRESH_COUNT`), 9개는 고정 풀에서 날짜를 씨앗으로 고른다(`POOL_COUNT`). 고정 풀은 8개 카테고리(컴퓨터과학 · 산업공학 · AI · 문학 · 세계사 · 세계 이슈 · 한국 · 연구 생활, 각 40개 이상)이고, 하루치는 카테고리를 한 바퀴 돌며 하나씩 뽑으므로 세 전공 카테고리가 매일 최소 하나씩 나온다. 같은 날에는 몇 번을 새로고침해도 같은 12개가 나오고, 자정을 넘기면 바뀐다. 라벨 옆 `↻`를 누르면 그 자리에서 다시 뽑는다: 고정 풀 9개는 바로 새 조합으로 바뀌고, 뉴스 3개는 백그라운드로 다시 가져오는 동안 이전 목록이 남아 있다가 도착하면 바뀐다(`POST /api/topics/refresh`).

주제마다 카테고리(`news` · `korea` · `research` · `cs` · `ie` · `ai` · `literature` · `history` · `world`)가 붙어 `/api/topics`에 `{text, category}`로 내려간다. 칩 색은 카테고리별로 다르고, 칩 아래 범례가 그날 나온 카테고리만 이름으로 보여준다. 색 정의는 `frontend/src/styles.css`의 `[data-category=...]` 규칙에 모여 있다.

뉴스 3개는 그날 처음 `/api/topics`를 호출할 때 백그라운드로 `claude` CLI를 한 번 돌려 받아 `topic_days` 테이블에 저장한다(하루 1회). 주요 외신 1면·톱 수준으로 크게 다뤄진 기사만 받는다(독립된 주요 매체 2곳 이상이 비중 있게 다룬 것이 기준). 3개 중 1개는 한국 기사로, 영문 국내 매체(연합뉴스, 코리아헤럴드, 중앙데일리, 코리아타임스) 톱 기준으로 고른다(`KOREA_COUNT`). 칩 문구는 다른 풀과 맞춰 7단어 이하 명사구로 받고, 의문사로 시작하는 문장은 금지한다. 웹 검색이 막혔거나 기준을 넘은 기사가 없으면 빈 목록을 돌려받고, 그날치를 저장하지 않아 다음 요청에서 다시 시도한다. 도착 전이나 실패했을 때는 12개 전부 고정 풀에서 채우므로 화면이 비지 않는다. `pending`은 백그라운드 fetch가 실제로 도는 동안만 참이다(실패하면 바로 거짓, 다음 페이지 로드에서 재시도). 프론트는 `pending`이 참인 동안 15초 간격으로 최대 3분간 다시 물어보고, 그 뒤엔 새로고침 버튼을 다시 연다. fetch가 실패하면 `error`에 이유(CLI 오류 메시지, 또는 검색 결과 없음)가 실려 오고, 홈 화면의 Today's topic 아래에 그대로 표시된다. 표현 5개는 주제와 무관한 B2~C1+ 범용 표현이고, 어휘 10개는 주제 연관 단어로 아티클 밖에서도 고른다. 최근 40세션에서 이미 나온 표현·단어는 프롬프트에 제외 목록으로 넘긴다. 각 항목은 10% 확률로 목록에서 빠져 가끔 다시 나올 수 있다(`JobRunner.REPEAT_ALLOWANCE`).

생성은 로컬 `claude` CLI(`claude -p --json-schema --output-format stream-json`)를 서브프로세스로 호출한다. `POST /api/sessions`는 202로 작업 ID를 돌려주고, 프론트가 `GET /api/jobs/{id}`를 1초마다 폴링해 단계(스킬 로드 → 웹 검색 n회 → 작성 → 구조 확인)와 진행 바를 보여준다. 작업은 서버 메모리에 살아 있으므로 홈에 다시 들어오면 `GET /api/jobs`(진행 중인 작업 목록)로 찾아 같은 진행 바를 이어서 보여준다. 퍼센트는 단계 하한 + 경과 시간(최근 5회 중앙값 기준) 추정이다. API 키 불필요, Claude 구독으로 처리. 1회 생성 약 1~2분(opus 기준). CLI에는 `Skill`, `Read`, 내장 `WebSearch`/`WebFetch`, firecrawl MCP(`firecrawl_search`, `firecrawl_scrape`)가 열려 있다. 검색은 firecrawl을 먼저 쓰고, firecrawl이 없거나(OAuth 만료 등) 실패하면 내장 `WebSearch`로 넘어간다. 아티클은 최대 3회 웹 검색으로 사실을 확인하고 최근 이슈를 각도로 잡는다. firecrawl은 호스트에서 `claude mcp add --transport http firecrawl https://mcp.firecrawl.dev/v2/mcp-oauth` 후 한 번 OAuth 로그인해 두면 된다. 토큰이 만료되면(`claude mcp list`가 `Needs authentication`을 보임) 호스트에서 `claude`를 열어 `/mcp` → firecrawl → Authenticate로 다시 로그인하고, `docker compose restart backend`로 자격증명을 다시 복사한다(컨테이너는 시작할 때 호스트 `.credentials.json`을 복사한다).

| 환경변수 | 기본값 | 용도 |
|---|---|---|
| `VOICE_PROVIDER` | `openai` | 음성 코치 3종의 provider. `openai`(GPT-Live, WebRTC) 또는 `gemini`(Gemini Live, WebSocket) |
| `VOICE_MODEL` | provider별 | 비우면 `gpt-live-1` / `gemini-3.8-live-extended-thinking` |
| `VOICE_THINKING` | `low` | `gemini-3.8-live-extended-thinking`의 thinking 수준. `low`, `medium`, `high` |
| `VOICE_NAME` | `Kore` | Gemini 음성. Gemini API에 목록 조회 API가 없어 TTS 문서의 30개(Live native audio 모델과 공유)를 코드에 두고 모달에서 고른다. OpenAI는 각 코치 `session.json`의 voice를 쓴다 |
| `GEMINI_API_KEY` | 비움 | Gemini Live용. provider가 `gemini`인데 비어 있으면 세 버튼이 503 |
| `AZURE_SPEECH_KEY` | 비움 | Read aloud 판정기(Azure Pronunciation Assessment). 비어 있으면 Read aloud 버튼이 503 |
| `AZURE_SPEECH_REGION` | `koreacentral` | Azure Speech 리소스 리전 |
| `ASSESS_WORD_SCORE` | `60` | 단어 AccuracyScore가 이 값 아래면 발음 교정 |
| `ASSESS_BREAK_CONFIDENCE` | `0.75` | 단어 앞 UnexpectedBreak confidence가 이 값 위면 끊어읽기 교정 |
| `CLAUDE_MODEL` | `opus` | 생성 모델. `sonnet`이면 더 빠름 |
| `CLAUDE_EFFORT` | `xhigh` | reasoning effort. `low`, `medium`, `high`, `xhigh`, `max` |
| `CLAUDE_SKILLS` | 비움 | 생성 전에 호출할 스킬. 쉼표 구분. 예: `stop-slop,cotidie:write-like-me` |
| `DB_PATH` | `backend/data/sessions.db` | SQLite 파일 |
| `OPENAI_API_KEY` | 비움 | GPT-Live 코치(provider가 `openai`일 때)와 Summary 탭 텍스트 추출용 |
| `READ_ALOUD_AGENT_DIR` | `../read-aloud-coach` | 발음·끊어 읽기 코치 정의 폴더(프롬프트, 세션 설정) |
| `EXAMPLE_AGENT_DIR` | `../example-coach` | Your turn / Practice 코치 정의 폴더 |
| `PHRASE_AGENT_DIR` | `../phrase-coach` | 표현 코치 정의 폴더 |
| `SUMMARY_MODEL` | `gpt-5.6-luna` | Summary 탭에서 transcript를 정리하는 텍스트 모델 |
| `TOPICS_MODEL` | `sonnet` | 하루 한 번 뉴스에서 추천 주제를 뽑는 모델 |
| `TOPICS_EFFORT` | `medium` | 그 호출의 reasoning effort |
| `EXAMPLE_MODEL` | `opus` | Your turn / Practice 피드백을 쓰는 `claude` 모델 |
| `EXAMPLE_EFFORT` | `low` | 그 호출의 reasoning effort |
| `IMAGE_PROVIDER` | `openrouter` | Vocabulary 그림을 그리는 MCP: `openrouter` · `comfy` · `off` |
| `OPENROUTER_API_KEY` | 비움 | OpenRouter MCP의 bearer 토큰. provider가 `openrouter`인데 비어 있으면 그림 없이 생성 |
| `COMFY_API_KEY` | 비움 | comfy-cloud MCP의 bearer 토큰. provider가 `comfy`일 때 |
| `IMAGE_MODEL` | 비움 | 이미지 모델. 비우면 provider 기본값(Nano Banana Pro). 설정 모달 메뉴에 GPT-Image 2.5, Nano Banana 2 등이 있다 |
| `IMAGE_STYLE` | `photo` | 그림 스타일: `photo`(사진, 묘사할 거리가 가장 많다) · `cinematic` · `storybook` · `comic` · `sketch` · `flat`. 프롬프트는 `illustrator.STYLES` |

## Vocabulary 그림

세션 생성 마지막 단계(`illustrating`, 진행 바의 "Drawing a picture for each word")에서 단어마다 그 단어가 어울리는 상황을 그린 그림을 한 장씩 만든다. 장면 문장(`scene`)은 세션 생성 프롬프트가 단어와 함께 쓴다(글자가 들어갈 필요 없는 구체적인 상황). 이미지 프롬프트는 `IMAGE_STYLE`의 스타일 문장 + 글자 금지 문장 + 장면 문장이다. `backend/app/illustrator.py`가 그 장면들을 `IMAGE_PROVIDER`의 MCP 서버에 보낸다. MCP 호출은 `backend/app/mcp_client.py`(JSON-RPC over HTTP)가 하고, 인증은 OAuth 로그인 대신 그 provider의 API 키를 bearer 토큰으로 보낸다(OAuth 토큰은 몇 시간에서 7일이면 만료되므로). `claude` 실행은 없다.

| provider | MCP | 호출 | 기본 모델 |
|---|---|---|---|
| `openrouter` | `https://mcp.openrouter.ai/mcp` | 단어마다 `generate-image`를 열 개 동시에, 응답의 inline image 블록(base64) | `google/gemini-3-pro-image` |
| `comfy` | `https://cloud.comfy.org/mcp` | `submit_batch`(한 배치, `confirm: true`; comfy가 열 장을 동시에 그린다) → `wait_for_batch` → `get_batch_output`의 서명 URL을 열 개 동시에 내려받음 | `vertexai/nano-banana-pro` |

OpenAI 모델은 OpenRouter 표기(`openai/gpt-image-2.5-flare`)로 적으면 comfy에서도 통한다(`openai/images-generations` + `params.model`로 바꿔 보낸다). 그림은 `backend/data/images/{job}-{n}.png`에 두고 `/api/images/`로 서빙하며, 세션 content의 각 단어에 `scene`과 `image`가 붙는다. 그림 하나가 실패하면 그 단어만 그림 없이, 전체가 실패하면 경고만 남기고 세션은 그림 없이 저장된다. 카드의 그림 왼쪽 위 `↻`를 누르면 스타일 메뉴가 열리고, 고르면 `POST /api/sessions/{id}/pictures/{index}`(`{style}`)가 텍스트 모델(`EXAMPLE_MODEL`, `illustrator.SceneWriter`)에 이전 장면과 다른 새 장면을 쓰게 한 뒤 그 스타일로 다시 그려 세션 content에 저장한다(새 파일명, 옛 파일 삭제). 별표와 `↻`는 그림 모서리 위에 반투명 원으로 얹혀 있다. 설정 모달의 `Test`가 키를 확인한다(OpenRouter는 `/api/v1/key`, comfy는 MCP initialize). comfy-cloud 구독이 끝나면 `IMAGE_PROVIDER`를 `openrouter`로 둔다. 비용은 각 대시보드에서 확인한다(Nano Banana Pro 기준 장당 $0.1~0.2).

## Article 한국어 번역

세션을 만들 때 아티클 본문을 문장 단위로 번역해 함께 저장한다(`article.translation`, `{en, ko}` 쌍). 화면에서는 숨겨져 있다가 문장을 클릭하면 영어가 가라앉고 그 자리에 한국어가 떠오른다. 다시 클릭하면 영어로 돌아간다. 번역은 모델이 문단 전체를 보면서 문장별로 만들고, `en`이 본문에 글자 그대로 없는 쌍은 backend가 버리므로 그 문장은 영어로만 남는다. 번역이 없는 예전 세션은 클릭해도 아무 일도 없다.

## 설정 모달

모든 페이지 우상단 ⚙(단축키 `,`)가 위 표의 환경변수를 전부 편집하는 모달을 연다(`DB_PATH`, `*_AGENT_DIR`, `FRONTEND_PORT`, `CLAUDE_CODE_OAUTH_TOKEN`처럼 재시작이 필요한 인프라 값은 제외). `.env`는 초기값일 뿐이고, 모달에서 저장한 값은 `PUT /api/settings`로 SQLite `settings` 테이블에 남아 그 뒤로는 그 값이 쓰인다(컨테이너를 다시 만들어도 `backend/data`에 남는다). 저장 직후 backend가 생성기·주제 소스·음성 코치·추출기를 다시 조립하므로 재시작 없이 다음 라운드부터 바뀐 provider와 모델이 쓰인다. API 키는 마스킹(`…끝 4자`)으로만 내려오고 입력칸을 비워 두면 그대로 유지된다. 키 칸 옆 `Test`는 `POST /api/settings/test-key`로 그 provider의 모델 목록을 한 번 조회해 키가 통하는지 바로 보여 준다(입력칸이 비어 있으면 저장된 키를 시험한다).

## 음성 코치 provider (GPT-Live / Gemini Live)

세 코치(Read aloud · Ask · Your turn/Practice)는 같은 `LiveConnection` 인터페이스(`microphone`, `finish`, `say`, `close`) 위에서 돌고, provider는 `frontend/src/lib/live/transport.ts`가 라운드를 열 때 설정을 읽어 고른다. 에이전트 정의 폴더(`prompts/live.md`, `session.json`)는 provider와 무관하게 하나다.

| | OpenAI `gpt-live-1` | Gemini `gemini-3.8-live(-extended-thinking)` |
|---|---|---|
| 전송 | WebRTC. backend가 SDP offer를 중계 (`lib/live/openaiWebrtc.ts`) | WebSocket. backend가 1회용 ephemeral token을 발급하고 setup 메시지를 만들어 줌 (`lib/live/geminiWebsocket.ts`) |
| 오디오 | 브라우저 트랙 그대로 | AudioWorklet 2개(`public/worklets/`): 마이크 → 16 kHz PCM 청크, 24 kHz PCM 수신 → 같은 `<audio>`로 재생 |
| 지시(`say`, `finish`) | `session.instructions.append` | `clientContent` 사용자 턴 |
| 개발자 컨텍스트(문단, 주제, 표현) | `session.json`의 developer 메시지 | `systemInstruction` 끝에 이어 붙임 |
| 자막 | `session.*_transcript.delta` | `inputTranscription`/`outputTranscription`을 같은 이벤트명으로 변환 (`lib/live/geminiEvents.ts`) |
| 초 단위 사용량 | 서버 `usage.seconds` | 프론트 벽시계 |
| 비용 | 분당 $0.05, 15초 최소 과금 | 입력 $0.005/분 + 출력 $0.018/분(thinking 토큰 포함). 최소 과금 없음. 문단 하나 Read aloud 약 $0.05 |

Gemini 세션은 오디오만일 때 15분 상한이며 코치 라운드는 그보다 훨씬 짧다. Extended Thinking은 `VOICE_THINKING`만큼 뒤에서 생각하며 말하고, 즉답이 필요한 발음 교정에는 `low`로 시작한다. 브라우저에는 API 키가 가지 않는다: 소켓 URL의 `access_token`은 1회용이고 모델이 고정되어 있다.

## Read aloud

Article 탭의 문단마다 `Read aloud` 버튼이 있다. 누르면 마이크가 Azure Pronunciation Assessment로만 간다. 음성 코치(GPT-Live 또는 Gemini Live)는 읽는 동안 켜지지 않는다. 판정은 Azure가 한다: 문단을 참조 텍스트로 두고 인식된 구간마다 단어·음소 점수와 단어 앞 휴지 확신도를 돌려준다. 브라우저의 `lib/assessor/judge.ts`가 finding(단어 점수 < `ASSESS_WORD_SCORE`, 또는 UnexpectedBreak > `ASSESS_BREAK_CONFIDENCE`)을 고르고 문단의 그 자리에 표시한다. 표시(단어 밑줄, 구 안 휴지 막대, Phrasing 슬래시)는 문단의 원래 서식 위에 그대로 얹힌다(`components/Sentence.tsx`). 라운드 중이든 끝난 뒤든 문장을 클릭하면 한국어로 바뀌고, 그 문장의 표시는 영어로 돌아올 때까지 숨는다. 코치는 지시를 받았을 때만 말한다. 스스로 판정하지 않는다. 오디오 LLM에게 판정을 맡겼을 때 놓치던 v/b, th, 구 안 멈춤이 이 구조의 이유다(`docs/2026-09-21-pronunciation-coach-research.md`).

| 시점 | 화면 | 코치 |
|---|---|---|
| 읽는 동안 | 문단이 단어 단위로 바뀌고, 틀린 단어에 붉은 밑줄, 구 안 멈춤은 두 단어 사이 붉은 `\|` | 꺼져 있음 |
| 표시 클릭 | 아래에 카드가 바로 뜬다. 발음: "You said /dɪzs…/. It's /hɪst…/." (틀린 소리는 붉게) + 가장 나쁜 소리 하나의 입 모양 한 문장("h as in Hat: Breathe out.", `lib/assessor/sounds.ts` 표). 끊어읽기: "You paused between \"July\" and \"1969\". It's \"July 1969\" in one breath." | 세션 하나를 열어 두 박자 "You said berify. It's verify. Try it."(`Correction:`)만 말하고, 2초 조용하면 끊는다. 코치 마이크는 꺼 둔다 |
| 다시 읽어 맞음 | 표시가 초록 ✓ (Azure가 확인) | |
| `Done` | 마이크와 Azure를 놓는다. 표시는 남아 그 뒤에도, `Close` 뒤에도 클릭할 수 있다. `Read again`으로 새 라운드 | |

문단마다 `Phrasing` 버튼이 있다. 처음 누르면 `POST /api/phrasing`이 `claude` CLI(`EXAMPLE_MODEL`/`EXAMPLE_EFFORT`, 도구 없음)에 `../read-aloud-coach/prompts/phrasing.md`를 넣어 thought group 경계에 ` / `가 들어간 문단을 받고, 단어열이 원문과 같은지 확인한 뒤 경계 인덱스를 `phrasings` 테이블에 캐시한다(문단당 한 번, 약 5~10초). 화면에는 파란 슬래시로 보이고 다시 누르면 숨는다. 켜 둔 채 Read aloud를 하면 슬래시 자리에서 멈춘 것은 끊어읽기 오류로 표시하지 않는다.

라운드가 끝나면 `POST /api/readings`에 `corrections`로 함께 저장된다. Summary 탭은 `GET /api/readings`로 그 목록을 읽는다. 텍스트 모델로 transcript를 정리하던 단계는 없앴다.

Azure 키는 backend에만 있다. `GET /api/assessor/token`이 10분짜리 토큰과 임계값·피드백 시점을 내주고, 브라우저는 `microsoft-cognitiveservices-speech-sdk`로 직접 스트리밍한다(구간 무음 400 ms, en-US, IPA, prosody on). 무료 F0 리소스는 월 5시간, 동시 1세션. 문단 하나 약 1~2분. 에이전트 정의(프롬프트, 세션 설정, 검증 시나리오)는 `../read-aloud-coach/`에 있고 backend는 그 폴더를 읽기만 한다.

## Ask (GPT-Live)

어느 페이지에서든 화면 맨 아래 가는 선의 `Ask`를 누르거나 `A` 키를 치면 표현 코치가 붙는다. 입력칸에 커서가 있으면 단축키는 무시한다. "눈치 좀 챙기라는 말 영어로 어떻게 해?"처럼 한국어로 물어도 되고, 자기가 쓴 영어가 어색한지 확인해도 된다. 답은 표현 하나, 부연이 붙어도 짧은 한 문장, 10초 이내. 말하는 동안 막대 5칸짜리 표시가 마이크 입력 크기를 보여준다. 코치가 5초간 조용하면 라운드가 자동으로 끝나고, `Done`이나 `Esc`로 바로 끝내도 된다. 한 번에 약 $0.015.

말할 타이밍을 놓쳤거나 엉뚱하게 들어갔으면 `Retry`(`R`)로 그 자리에서 다시 시작한다. 앞 라운드는 버려지고 새 세션이 열리므로 15초 최소 과금이 다시 붙는다.

라운드가 끝나면 자막 두 줄이 쪽지에 남고, `Save`(`Enter`)를 눌러야 `asks` 테이블에 들어간다. 쓸모없는 답은 `Discard`(`Esc`)로 버린다. 세션 안에서 물었으면 그 세션에 묶이고, 홈에서 물었으면 세션 없이 남는다.

에이전트 정의는 `../phrase-coach/`에 있다. `../read-aloud-coach/`와 같은 규약이고, backend의 같은 `LiveAgent`가 둘 다 읽는다.

## Your turn / Practice (GPT-Live + claude CLI)

Expressions 탭의 표현마다 노란 `Your turn: one sentence each.` 라벨이, Vocabulary 탭의 카드마다 `Practice` 버튼이 있다. 둘 다 같은 `Practice` 컴포넌트다. 누르면 마이크가 붙고 참가자가 그 표현이나 단어로 문장 하나를 말한다. GPT-Live는 듣기와 읽어 주기만 맡는다: 문장이 끝나면 "Got it." 한마디, 그 첫 발화를 신호로 프론트가 사용자 transcript를 `POST /api/example/feedback`에 보낸다. backend는 `claude` CLI(`EXAMPLE_MODEL`, 기본 opus, `EXAMPLE_EFFORT` 기본 low, 도구 없음)에 `../example-coach/prompts/feedback.md`를 넣어 `paraphrase`(원어민이 말하는 대로 바꿔 말한 문장, 고칠 곳은 모두 고침)와 `feedback`(고친 곳마다 짧은 문장 하나씩의 목록) 두 필드를 받는다. 쪽지에서는 목록을 불릿으로 보여 준다. 답이 오는 동안 쪽지에 `Writing the native version…`이 뜨고 라운드는 닫히지 않는다(약 10초). 답이 오면 화면에 두 줄로 보이고, 같은 문장을 `session.instructions.append`로 넘겨 코치가 그대로 소리 내어 읽는다. 코치가 5초간 조용하면 라운드가 끝나고 `Keep`으로 그 표현 아래에 쌓인다. 쪽지 위의 `↻`는 처음부터 다시, `✕`는 듣는 중이든 끝난 뒤든 버린다. 텍스트 모델이 실패하면 오류가 쪽지에 그대로 뜨고 Keep은 잠긴다.

Vocabulary 카드의 Practice는 판단 프롬프트가 `../example-coach/prompts/feedback-word.md`로 바뀐다(`kind: "word"`, 그림 설명 `scene`을 함께 보낸다). 사용자는 카드의 그림을 보며 그 단어로 한 문장을 말하고, `paraphrase`는 가벼운 교정이 아니라 원어민이 그 그림을 그 단어로 묘사하는 문장(자유로운 의역)이며, `feedback`의 첫 줄은 언제나 단어 사용에 대한 것이다. 그림이 없는 예전 세션에서는 문장만 보고 판단한다.

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

탭을 처음 열 때 텍스트 모델이 한 번 돌아 Ask transcript를 카드로 정리하고 결과를 각 행에 캐시한다. 두 번째부터는 호출하지 않는다. 프롬프트와 스키마는 `phrase-coach/cards.schema.json`에 있다. Read aloud 교정은 라운드가 끝날 때 판정기 finding으로 이미 저장돼 있어 모델 호출이 없다.

홈의 `Asks` 링크는 세션과 무관하게 지금까지 물어본 표현 전체를 보여준다.

## Docker

인증은 호스트의 `~/.claude/.credentials.json`(claude.ai 로그인 + firecrawl OAuth)을 컨테이너 시작 시 복사한다. 호스트에서 로그인이 바뀌면 `docker compose restart backend`. 호스트 로그인과 분리하려면 `claude setup-token` 값을 `.env`의 `CLAUDE_CODE_OAUTH_TOKEN`에 넣는다.

포트가 겹치면 `.env`의 `FRONTEND_PORT`를 바꾼다.

| 서비스 | 내용 |
|---|---|
| backend | python 3.13 + uv + Claude Code 바이너리. `backend/data`를 `/data`로 마운트해 SQLite 유지 |
| frontend | Vite 빌드를 nginx로 서빙. `/api`를 backend:8765로 프록시, 타임아웃 600초 |

스킬은 호스트의 `~/.claude/skills`와 `~/.claude/plugins`를 읽기 전용으로 같은 경로에 마운트한다(플러그인 매니페스트가 절대경로를 쓰므로 컨테이너 HOME을 호스트와 맞춘다). 호스트 `settings.json`에서는 `enabledPlugins`만 가져오므로 훅과 권한 설정은 컨테이너 안에서 돌지 않는다. MCP는 `--strict-mcp-config`로 firecrawl(HTTP)만 붙인다.

### 개발

```sh
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

`compose.dev.yaml`이 소스를 bind mount하고 backend는 `uvicorn --reload`, frontend는 Vite dev 서버(`Dockerfile`의 `dev` 스테이지, `/api`는 `backend:8765`로 프록시)로 띄운다. 파일을 저장하면 둘 다 바로 반영된다. 같은 포트 `5173`을 쓴다.

## 세션 진행 (30분)

| 단계 | 시간 | 방법 |
|---|---|---|
| Expressions | 10분 | 표현 5개. 예문 읽고 용례 합의, 각자 문장 하나씩 |
| Article | 10분 | 3분 묵독 후 각자 요약, 질문 3개로 토론. 앞 2개는 본문 확인용, 마지막 1개는 의견 교환용 |
| Vocabulary | 10분 | 단어 + 예문만 보고 뜻을 영어로 설명, 카드 클릭해 확인 |
| Summary | 끝나고 | 별표한 표현·단어, 만든 문장, 물어본 표현, 지적받은 발음을 한 화면에서 확인 |

타이머 `Start 30 min`을 누르면 10분마다 탭이 자동으로 넘어간다.

## 구조

```
backend/   FastAPI. app/{main,wiring,settings,generator,claude_cli,daily_topics,live,cards,store,topics,models}.py, tests/
           wiring.py가 설정으로 서비스를 조립하고, settings.py가 env + SQLite 오버라이드를 합친다
frontend/  React 19 + Vite + TS. src/{pages,components,lib}. lib/live/가 provider별 전송(openaiWebrtc, geminiWebsocket)
compose.yaml      사용용. compose.dev.yaml을 겹치면 개발용(핫 리로드)
```

## 테스트

개발 overlay가 떠 있는 상태에서:

```sh
docker compose exec backend uv run pytest      # 처음 한 번 pytest를 내려받는다
docker compose exec frontend npm test
```

설계 문서: `docs/superpowers/specs/2026-09-10-english-speaking-claude-design.md`
