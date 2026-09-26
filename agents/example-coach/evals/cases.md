# 검증 시나리오

프롬프트를 고칠 때마다 사람이 아래 10개를 직접 말해 보고 확인한다. 한 시나리오는 20초, 전체 약 5분.

표현 예시(모든 시나리오 공통): `read too much into something`, 뜻 "to find a meaning in something that probably isn't there", 노트 "takes 'into,' not 'in.'"

| # | 말하는 방식 | 기대 반응 |
|---|---|---|
| 1 | "Don't read too much into his short reply." (자연스러움) | 그대로 되풀이하고 자연스럽다는 한마디. 10초 이내 |
| 2 | "Don't read too much in his silence." (전치사) | 바꿔 말한 문장에 into. 피드백은 into 한 문장, 고친 게 그것뿐이니 그걸로 끝 |
| 3 | "I think you read too much into about the email." (군더더기) | about 없이 되풀이. 피드백은 about 한 문장 |
| 4 | "My boss read too much into the report so he fired me." (뜻은 맞지만 어색한 연결) | 자연스러운 연결로 되풀이. 고친 곳마다 한 문장, 고치지 않은 것은 언급 없음 |
| 5 | "I was really tired yesterday." (표현 없음) | 되풀이한 뒤 표현이 빠졌다고만 함. 새 문장을 지어 주지 않음 |
| 6 | 문장 중간에 3초 멈췄다가 마저 말하기 | 끊지 않고 끝까지 기다렸다 답 |
| 7 | "He didn't... um... he didn't reply, but don't read too much into it." (재시작) | 마지막 버전만 다룸. 머뭇거림 언급 없음 |
| 8 | 답을 듣고 따라 말하기 | "Good" 한마디 |
| 9 | 바로 두 번째 문장 말하기 | 새 문장에 답. 앞 문장으로 돌아가지 않음 |
| 10 | "done" | "Goodbye" 한마디 |

실패 기준:

| 실패 | 먼저 고칠 곳 |
|---|---|
| 답이 10초를 넘거나 피드백이 두 문장 | `## The feedback` |
| 1번에서 없는 개선안을 만듦 | `## The paraphrase`의 "Already natural" |
| 5번에서 예문을 지어 줌 | `## The sentence has no expression in it` |
| 바꿔 말한 문장이 사용자 뜻을 바꿈 | `## The paraphrase`의 "Add nothing" |
| 피드백이 문법 용어를 씀 | `## The feedback`의 "No grammar terms" |
| 6·7번에서 끼어듦 | `## 1) The sentence`의 "Wait" |
