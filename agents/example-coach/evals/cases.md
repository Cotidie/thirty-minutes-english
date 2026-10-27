# 검증 시나리오

프롬프트를 고칠 때마다 사람이 아래 10개를 직접 말해 보고 확인한다. 한 시나리오는 20초, 전체 약 5분.

단어 예시(모든 시나리오 공통): `bottleneck` (noun), 뜻 "the slowest point that holds everything else up", 그림 "cars queuing at a single open toll booth"

| # | 말하는 방식 | 기대 반응 |
|---|---|---|
| 1 | "The single toll booth is the bottleneck holding up all the traffic." (자연스러움) | 그대로 되풀이. 피드백은 "Good use of the word."와 "That's how a native speaker would say it." 10초 이내 |
| 2 | "The toll gate is bottleneck of the traffic." (관사·연어) | the bottleneck, holding up 같은 연어로 바꿔 말함. 첫 피드백은 단어(관사, in/for) |
| 3 | "There is a bottleneck about the toll booth." (전치사) | at the toll booth로 바꿔 말함. 첫 피드백은 단어 쓰임, 그다음 전치사 한 문장 |
| 4 | "Many cars are waiting at the booth." (단어 없음) | 바꿔 말한 문장에 bottleneck을 넣음. 첫 피드백은 단어가 빠졌다는 한마디 |
| 5 | "The cars make a bottleneck and the drivers are angry and late for work." (그림에 없는 내용) | 그림에 없는 내용(화남, 지각)을 더 키우지 않고 한 문장으로 묘사 |
| 6 | 문장 중간에 3초 멈췄다가 마저 말하기 | 끊지 않고 끝까지 기다렸다 답 |
| 7 | "The... um... the booth is, the booth is the bottleneck." (재시작) | 마지막 버전만 다룸. 머뭇거림 언급 없음 |
| 8 | 답을 듣고 따라 말하기 | "Good" 한마디 |
| 9 | 바로 두 번째 문장 말하기 | 새 문장에 답. 앞 문장으로 돌아가지 않음 |
| 10 | "done" | "Goodbye" 한마디 |

실패 기준:

| 실패 | 먼저 고칠 곳 |
|---|---|
| 답이 10초를 넘거나 피드백이 40단어를 넘음 | `prompts/feedback.md`의 feedback 규칙 |
| 1번에서 없는 개선안을 만듦 | paraphrase의 "Already natural" |
| 4번에서 단어를 넣지 않음 | paraphrase의 "The word is missing" |
| 5번에서 그림에 없는 내용을 더함 | paraphrase의 "Do not add details" |
| 첫 피드백이 단어 이야기가 아님 | feedback의 "The first entry is always about the word" |
| 피드백이 문법 용어를 씀 | feedback의 "No grammar terms" |
| 6·7번에서 끼어듦 | `prompts/live.md`의 `## 1) The sentence` |
