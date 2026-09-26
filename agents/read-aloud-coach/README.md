# read-aloud-coach

- 목표: 판정기(Azure Pronunciation Assessment)가 문단 위에 표시한 오류를, 읽는 사람이 클릭했을 때 한 줄로 바로잡는 음성 에이전트. 클릭마다 짧은 세션 하나. 읽는 동안에는 켜지지 않는다
- 상태: 진행 중. `english-speaking-claude` Article 탭에 연결됨. 클릭 시 교정 문구 튜닝 중
- 다음 할 일: `evals/cases.md` 2번(v/b)과 7번(twice as / long)부터 직접 읽어 임계값과 프롬프트 튜닝

## 파일

| 파일 | 내용 |
|---|---|
| `AGENT.md` | 에이전트 계약. 역할, 한 번의 호출, 지시 형식, 한계 |
| `session.json` | `POST /v1/live/sessions`에 넣는 `session` 객체. `{{paragraph}}` 자리만 채운다 |
| `prompts/live.md` | 코치 `instructions` 원문 |
| `prompts/phrasing.md` | 문단에 thought group 경계(` / `)를 넣는 텍스트 프롬프트. 호스트가 파란 슬래시로 그린다 |
| `evals/cases.md` | 프롬프트를 고칠 때 사람이 직접 읽어 확인하는 시나리오 16개 |
