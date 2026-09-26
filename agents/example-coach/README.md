# example-coach

- 목표: 방금 배운 표현이나 단어로 참가자가 말한 문장 하나를 듣고, 원어민이 말하는 대로 바꿔 말해 준 뒤 고친 곳마다 피드백 한 문장을 붙이는 코치. 듣기와 읽어 주기는 GPT-Live, 판단은 텍스트 모델. 어떤 앱에든 붙일 수 있게 독립 정의
- 상태: 진행 중. `english-speaking-claude` Expressions 탭의 `Your turn`과 Vocabulary 탭의 `Practice` 버튼에 연결됨, 실제 발화 검증 전
- 다음 할 일: `evals/cases.md` 10개 시나리오를 직접 말해 프롬프트 튜닝

## 파일

| 파일 | 내용 |
|---|---|
| `AGENT.md` | 에이전트 계약. 역할, 입력, 한 라운드의 진행, 호스트 앱이 할 일, 한계 |
| `session.json` | `POST /v1/live/sessions`에 넣는 `session` 객체. `{{expression}}`, `{{meaning}}`, `{{usage_note}}` 자리를 채운다 |
| `prompts/live.md` | GPT-Live `instructions` 원문. 듣고 "Got it.", 넘겨받은 문장을 그대로 읽는다 |
| `prompts/feedback.md` | 텍스트 모델 프롬프트. `{{expression}}`, `{{meaning}}`, `{{usage_note}}`, `{{sentence}}`를 채우면 `paraphrase`(문장), `feedback`(고친 곳마다 한 문장씩의 목록) 두 필드를 돌려준다 |
| `evals/cases.md` | 프롬프트를 고칠 때 사람이 직접 말해 확인하는 시나리오 10개 |
