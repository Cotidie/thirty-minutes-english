# english-speaking-claude

- 목표: 친구와 하루 30분 영어 회화 연습. 매 세션 표현 5개 + 짧은 아티클(AI/CS/IE) + B2~C1 어휘 8개를 Claude가 생성.
- 상태: 진행 중 (v1 동작)
- 다음 할 일: 며칠 써보고 표현 난이도와 아티클 길이 조정

## 실행

```sh
./dev.sh          # backend :8765 + frontend :5173
```

`http://localhost:5173` 접속. 주제를 비워 두면 최근 10회에 안 나온 주제를 자동으로 고른다.

생성은 로컬 `claude` CLI(`claude -p --json-schema`)를 서브프로세스로 호출한다. API 키 불필요, Claude 구독으로 처리. 1회 생성 약 1~2분(opus 기준).

| 환경변수 | 기본값 | 용도 |
|---|---|---|
| `CLAUDE_MODEL` | `opus` | 생성 모델. `sonnet`이면 더 빠름 |
| `DB_PATH` | `backend/data/sessions.db` | SQLite 파일 |

## 세션 진행 (30분)

| 단계 | 시간 | 방법 |
|---|---|---|
| Expressions | 10분 | 표현 5개. 예문 읽고 용례 합의, 각자 문장 하나씩 |
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
