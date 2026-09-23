# 표준 라이브러리 → 통용 라이브러리 교체 계획

- 상태: 1번 완료(`claude-agent-sdk`, firecrawl·entrypoint·호스트 파일 복사 제거, 배제 목록은 in-process 도구 `check_items`로). 2번 완료(공식 `mcp` SDK `Client`, 그림 병렬은 `asyncio.gather`, firecrawl 검색 MCP를 키 없이 우선 사용). 3·4번 남음. 3번은 `mcp`가 쓰는 `httpx2`로 한다.
- 원칙: 라이브러리 하나당 커밋 하나. 순서는 아래 번호대로.
- async SDK는 동기 메서드 안에서 `asyncio.run(...)`으로 감싼다. 라우트와 `generation/jobs.py`의 스레드 풀은 그대로 둔다. 각 호출은 워커 스레드에서 돌기 때문에 이벤트 루프가 겹치지 않는다.

## 교체 대상

| # | 현재 | 교체 | 줄어드는 것 | 시간 | 위험 |
|---|---|---|---|---|---|
| 1 | `claude_cli.py` 157줄(subprocess, stream-json 파싱, 타임아웃 스레드, `build_command`), `generation/progress.py`의 이벤트 dict 해석, Dockerfile의 `claude` 설치 | `claude-agent-sdk` `query()`. 문서 확인: `output_format`, `ResultMessage.structured_output`, `effort`, `model`, `tools`(`[]`로 전부 끔), `allowed_tools`, `skills`, `setting_sources`, `mcp_servers`(http), `strict_mcp_config`, CLI 동봉 | subprocess 전부. `StreamTracker`는 타입 있는 메시지(`AssistantMessage`, `ToolUseBlock`)를 읽는다. 타임아웃은 `asyncio.timeout` | 1시간 | 중간 |
| 2 | `mcp_client.py` 118줄(JSON-RPC, SSE 파싱, 세션 ID) | 공식 `mcp` SDK `streamablehttp_client(url, headers=…)` + `ClientSession` | 파일 전체. `OpenRouterPainter`의 병렬 10장은 스레드 풀 → `asyncio.gather` 한 번 | 45분 | 중간 |
| 3 | `net.py`, `pictures/painters.py`의 `fetch_url`, `voice/assessor.py`·`config/keycheck.py`의 `urllib.request.Request` | `httpx`(1·2번 SDK가 끌어오는 버전을 쓴다. HTTP 클라이언트를 둘 두지 않는다) | 예외 분기(`HTTPError`/`URLError`), 요청 객체 조립. 테스트 5개 파일의 `urlopen` monkeypatch → `httpx.MockTransport` | 30분 | 낮음 |
| 4 | `coaching/cards.py`의 Responses 요청 조립, `_output_text` | `openai` SDK `responses.create(...).output_text` | 20줄 정도. 스키마는 계속 `phrase-coach/cards.schema.json`에서 읽는다(에이전트 폴더 규약 유지) | 15분 | 낮음. 선택 |

## 확인할 것 (착수 전)

- 1번: SDK 동봉 CLI가 컨테이너의 `~/.claude/.credentials.json`(claude.ai 로그인, firecrawl OAuth)을 그대로 읽는지. 안 되면 `cli_path`로 기존 설치를 가리키고, 그러면 Dockerfile 줄은 남긴다.
- 1번: `--no-session-persistence`에 해당하는 옵션. 없으면 세션 파일이 쌓이는지 보고 정리 방법을 정한다.
- 2번: OpenRouter MCP 앞의 Cloudflare가 요구하는 `User-Agent`를 `headers`로 넘길 수 있는지.
- 3번: 테스트 클라이언트가 쓰는 `httpx2`(dev 의존성)와 SDK가 끌어오는 `httpx`가 같은 패키지인지. 다르면 SDK 쪽을 따른다.

## 제외

| 코드 | 후보 | 이유 |
|---|---|---|
| `voice/live.py` `GeminiVoice` 토큰 발급 | `google-genai` `auth_tokens.create` | 줄어드는 게 15줄 정도인데 의존성이 크다. setup 고정(`bidiGenerateContentSetup`)이 SDK의 `live_connect_constraints`와 같게 동작하는지도 확인되지 않았다 |
| `voice/live.py` `OpenAIVoice` WebRTC 중계 | `openai` SDK | `gpt-live-1`의 `/v1/live/sessions`를 SDK가 다루는지 확인되지 않았다. 3번의 httpx로 충분하다 |
| `db/` raw SQL, 저장소 4개 | SQLModel / SQLAlchemy | 테이블 8개가 작고 대부분 Pydantic 모델을 JSON 컬럼으로 저장한다. ORM 설정이 줄어드는 코드보다 많다 |
| `config/settings.py` | pydantic-settings | env 부분만 대체된다. 저장값 > env > 기본값 계층, 모달용 choices·labels·group은 여전히 직접 짜야 한다 |
| `fetch_url` 3회 재시도 | tenacity | 10줄 한 곳 |
| `generation/jobs.py` 스레드 풀 | Celery, arq | 단일 프로세스, 진행률은 메모리에 있다 |

## 검증

- 커밋마다 `uv run pytest -q` 전체 통과.
- 1번 뒤: 세션 하나 생성. 진행 바가 스킬 → 검색 n회 → 작성 → 구조 확인 → 그림 순으로 움직이는지, Your turn 피드백·Phrasing·redraw 장면 작성이 도는지.
- 2번 뒤: redraw 한 장, 설정 모달 comfy `Test`.
- 3번 뒤: 설정 모달의 키 5개 `Test`, Read aloud 토큰, Ask 라운드 하나.
- 4번 뒤: Summary 탭에서 새 Ask 카드 추출.
