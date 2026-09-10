# english-speaking-claude

- 목표: 친구와 하루 30분 영어 회화 연습. 매 세션 표현 6개 + 짧은 아티클(기술 · 문학 · 세계사) + B2~C1+ 어휘 12개를 Claude가 생성.
- 상태: 진행 중 (v1 동작)
- 다음 할 일: 며칠 써보고 표현 난이도와 아티클 길이 조정

## 실행

```sh
./dev.sh          # backend :8765 + frontend :5173
```

`http://localhost:5173` 접속. 주제를 비워 두면 기술 · 문학 · 세계사 풀(`backend/app/topics.py`)에서 최근 10회에 안 나온 주제를 자동으로 고른다. 표현 6개는 주제와 무관한 B2~C1+ 범용 표현이고, 어휘 12개는 주제 연관 단어로 아티클 밖에서도 고른다. 최근 40세션에서 이미 나온 표현·단어는 프롬프트에 제외 목록으로 넘긴다. 각 항목은 10% 확률로 목록에서 빠져 가끔 다시 나올 수 있다(`JobRunner.REPEAT_ALLOWANCE`).

생성은 로컬 `claude` CLI(`claude -p --json-schema --output-format stream-json`)를 서브프로세스로 호출한다. `POST /api/sessions`는 202로 작업 ID를 돌려주고, 프론트가 `GET /api/jobs/{id}`를 1초마다 폴링해 단계(스킬 로드 → 웹 검색 n회 → 작성 → 구조 확인)와 진행 바를 보여준다. 퍼센트는 단계 하한 + 경과 시간(최근 5회 중앙값 기준) 추정이다. API 키 불필요, Claude 구독으로 처리. 1회 생성 약 1~2분(opus 기준). CLI에는 `Skill`, `Read`와 firecrawl MCP(`firecrawl_search`, `firecrawl_scrape`)만 열려 있다. 아티클은 최대 3회 웹 검색으로 사실을 확인하고 최근 이슈를 각도로 잡는다. firecrawl은 호스트에서 `claude mcp add --transport http firecrawl https://mcp.firecrawl.dev/v2/mcp-oauth` 후 한 번 OAuth 로그인해 두면 된다.

| 환경변수 | 기본값 | 용도 |
|---|---|---|
| `CLAUDE_MODEL` | `opus` | 생성 모델. `sonnet`이면 더 빠름 |
| `CLAUDE_EFFORT` | `xhigh` | reasoning effort. `low`, `medium`, `high`, `xhigh`, `max` |
| `CLAUDE_SKILLS` | 비움 | 생성 전에 호출할 스킬. 쉼표 구분. 예: `stop-slop,cotidie:write-like-me` |
| `DB_PATH` | `backend/data/sessions.db` | SQLite 파일 |

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
| Article | 10분 | 3분 묵독 후 각자 요약, 질문 3개로 토론 |
| Vocabulary | 10분 | 단어 + 예문만 보고 뜻을 영어로 설명, 카드 클릭해 확인 |

타이머 `Start 30 min`을 누르면 10분마다 탭이 자동으로 넘어간다.

## 구조

```
backend/   FastAPI. app/{main,generator,store,topics,models}.py, tests/
frontend/  React 19 + Vite + TS. src/{pages,components,lib}
dev.sh     둘 다 띄우는 스크립트
```

## 테스트

```sh
cd backend && uv run pytest
cd frontend && npx vitest run
```

설계 문서: `docs/superpowers/specs/2026-09-10-english-speaking-claude-design.md`
