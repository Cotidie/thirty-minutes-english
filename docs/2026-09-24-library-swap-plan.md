# 표준 라이브러리 → 통용 라이브러리 교체 계획

- 상태: 계획. 백엔드 구조 리팩터링(`backend-modules` 브랜치)이 끝나고 테스트가 통과한 뒤 시작한다.
- 원칙: 라이브러리 하나당 커밋 하나. 순서는 아래 번호대로.

## 교체 대상

| # | 현재 | 교체 | 줄어드는 것 | 시간 | 위험 |
|---|---|---|---|---|---|
| 1 | `urllib` 7곳 (net, live, assessor, keycheck, cards, mcp_client, illustrator) | `httpx` (동기) | `net.py`의 예외 변환, timeout·HTTPError·URLError 분기 | 30분 | 낮음 |
| 2 | `coaching/cards.py`의 Responses 요청 JSON 직접 조립, `_output_text` 파싱 | `openai` SDK `responses.parse(text_format=PhraseCards)` | 수작업 파싱, `phrase-coach/cards.schema.json` 의존(Pydantic 모델이 스키마) | 20분 | 낮음 |
| 3 | `voice/live.py` `GeminiVoice`의 ephemeral token 본문 직접 조립 | `google-genai` `client.auth_tokens.create(live_connect_constraints=…)` | RFC3339 포맷, 본문 조립 | 20분 | 중간: setup 고정 필드 확인 필요 |
| 4 | `mcp_client.py` 118줄 (JSON-RPC, SSE 파싱, 세션 ID) | 공식 `mcp` SDK `streamablehttp_client` + `ClientSession` | 파일 전체. 화가의 병렬 10장은 스레드 풀 → `asyncio.gather` | 1시간 | 중간: async 전용 |
| 5 | `claude_cli.py` 145줄 (subprocess, stream-json 파싱, 타임아웃 스레드) + `generation/progress.py` `StreamTracker` | `claude-agent-sdk` `query()` | subprocess·파싱·타임아웃. `StreamTracker`는 타입 있는 메시지를 읽게 됨 | 1~1.5시간 | 중간: async, 컨테이너 안 자격증명 경로 확인 필요 |

5번은 문서에서 확인한 옵션: `output_format={"type": "json_schema", "schema": …}`, `ResultMessage.structured_output`, `effort`, `mcp_servers`(http), `strict_mcp_config`, `allowed_tools`.

## 유지 (교체하지 않음)

| 코드 | 후보 | 이유 |
|---|---|---|
| `db/` raw SQL, 저장소 4개 | SQLModel / SQLAlchemy | 테이블 8개가 작고 대부분 Pydantic 모델을 JSON 컬럼으로 저장한다. ORM 설정이 줄어드는 코드보다 많다 |
| `config/settings.py` | pydantic-settings | env 부분만 대체된다. 저장값 > env > 기본값 계층, 모달용 choices·labels·group은 여전히 직접 짜야 해 줄어드는 게 적다 |
| `pictures/`의 `fetch_url` 3회 재시도 | tenacity | 10줄 한 곳이라 의존성 추가가 과하다 |
| `generation/jobs.py`의 `ThreadPoolExecutor` | Celery, arq | 단일 프로세스, 진행률은 메모리에 있다. 큐 서버는 과하다 |

## 결정할 것

- 4·5번은 async SDK다. 이 둘을 쓰는 라우트(세션 생성, redraw, feedback, phrasing)를 `async def`로 바꾸고, `jobs`의 스레드 풀을 `asyncio` 태스크로 바꾼다.
- 적용 범위(1~5 전부 / 일부)는 구조 리팩터링이 끝난 뒤 정한다.

## 검증

- 커밋마다 `uv run pytest -q` 전체 통과.
- 1~3번 뒤: 설정 모달 `Test`로 각 키 확인, Ask·Read aloud 라운드 하나씩 열기.
- 4번 뒤: redraw 한 장.
- 5번 뒤: 세션 하나 생성해 진행 바 단계(스킬 → 검색 → 작성 → 구조 확인 → 그림)가 전처럼 움직이는지 확인.
