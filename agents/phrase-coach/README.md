# phrase-coach

- 목표: 대화 중 "이거 영어로 어떻게 말해?"에 원어민이 실제로 쓰는 표현 하나로 답하는 GPT-Live 에이전트. 어떤 앱에든 붙일 수 있게 독립 정의
- 상태: 진행 중. `english-speaking-claude`의 Ask 위젯에 연결됨, 실사용 검증 전
- 다음 할 일: `evals/cases.md` 12개 시나리오를 직접 말해 보며 프롬프트 튜닝

## 파일

| 파일 | 내용 |
|---|---|
| `AGENT.md` | 에이전트 계약. 역할, 입력, 세션 설정, 한 라운드의 진행, 호스트 앱이 처리할 이벤트, 한계, 비용, 통합 절차 |
| `session.json` | `POST /v1/live/sessions`에 넣는 `session` 객체. `{{topic}}` 자리만 채운다 |
| `prompts/live.md` | GPT-Live `instructions` 원문 |
| `prompts/summarize.md` | 라운드 transcript를 복습 카드로 정리하는 텍스트 모델 프롬프트 |
| `cards.schema.json` | 복습 카드 JSON 스키마 |
| `evals/cases.md` | 프롬프트를 고칠 때 사람이 직접 말해 확인하는 시나리오 12개 |

`read-aloud-coach`와 같은 규약이다. 두 폴더의 `session.json`·`prompts/live.md`는 backend의 같은 `LiveAgent` 코드가 읽는다.
