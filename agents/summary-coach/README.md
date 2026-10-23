# summary-coach

- 목표: 문단을 보며 영어로 요약해 말하면, 받아 적어서 한눈에 읽히는 세 줄 피드백(놓친 핵심, 고칠 표현, 모범답안)을 돌려주는 코치. 받아 적기는 Gemini 전사 모델, 판단은 텍스트 모델
- 상태: 진행 중. `english-speaking` Article 탭의 Summarize 버튼에 연결됨. 세 줄 형식은 실제 발화 검증 전
- 다음 할 일: `evals/cases.md` 10개 시나리오를 직접 말해 확인

## 파일

| 파일 | 내용 |
|---|---|
| `AGENT.md` | 에이전트 계약. 역할, 입력, 한 라운드의 세 단계, 피드백 형식, 호스트 앱이 할 일, 한계 |
| `transcription.json` | 귀. Gemini Live 설정(`BidiGenerateContentSetup`): 전사 모델과 언어. 호스트가 `customVocabulary`만 채운다 |
| `prompts/feedback.md` | 판단 프롬프트. `{{paragraph}}`, `{{summary}}`를 채운다 |
| `prompts/feedback.schema.json` | 판단 출력의 JSON 스키마: `missed`(0~1), `fixes`(0~2, `said`·`better`), `summary` |
| `evals/cases.md` | 프롬프트나 설정을 고칠 때 사람이 직접 말해 확인하는 시나리오 10개 |
