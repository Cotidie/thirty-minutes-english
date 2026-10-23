# 검증 시나리오

프롬프트나 `transcription.json`을 고칠 때마다 사람이 아래 10개를 직접 말해 보고 확인한다. 한 시나리오는 30초, 전체 약 6분.

문단 예시(모든 시나리오 공통): "Seoul scrapped its trams in 1968 to make room for cars. Now the city is laying tracks again: a 5.4-kilometer line in Wirye is due next year, a year behind schedule. Supporters say trams cost far less than a subway; critics say a bus could run the same route without new tracks."

| # | 말하는 방식 | 기대 반응 |
|---|---|---|
| 1 | "Seoul got rid of its trams in 1968, and now it's building a new line because trams are much cheaper than a subway." (핵심 맞음, 자연스러움) | Missed 없음. Say it better 0~1개. 모범답안이 말한 것보다 짧다 |
| 2 | "...because trams are faster than a subway." (핵심 틀림) | Missed에 "cheaper than a subway, not faster" 꼴 한 줄 |
| 3 | 문단 첫 문장을 그대로 읽기 | Say it better가 읽어 내린 부분을 짚는다. 모범답안은 문단을 베끼지 않는다 |
| 4 | "Seoul was remove the tram at 1968 and now making again." (번역투, 전치사) | Say it better 정확히 2개 이하, 예: was remove → got rid of |
| 5 | "Seoul is building a new 노면전차 line in Wirye." (한국어 단어 섞기) | transcript에 한글이 한글로 남고, 영어·한국어 밖의 언어가 없다 |
| 6 | "Wirye"를 넣어 말하기 | transcript에 문단 표기대로 Wirye |
| 7 | 문장 중간에 5초 멈췄다가 마저 말하기 | 라운드가 닫히지 않고 두 발화가 공백 하나로 이어진다 |
| 8 | 마지막 문장을 말하는 도중에 Done | 마지막 문장까지 transcript에 있다 |
| 9 | 60단어 넘게 길게 말하기 | 피드백이 여전히 4줄 이하, 모범답안 25단어 이하 |
| 10 | 아무 말 없이 Done | "Nothing came through". 판단 모델을 부르지 않는다 |

실패 기준:

| 실패 | 먼저 고칠 곳 |
|---|---|
| 피드백이 4줄을 넘거나 한 줄이 한도를 넘음 | `prompts/feedback.md`의 해당 필드 줄, `prompts/feedback.schema.json`의 `maxItems` |
| 모범답안이 말한 것보다 김 | `prompts/feedback.md` `summary:`의 "Shorter than what they said" |
| 2번에서 Missed가 비어 있음 | `prompts/feedback.md` `missed:` |
| 1번에서 없는 문제를 만들어 냄 | `prompts/feedback.md` `fixes:`의 "Empty when it already sounded native" |
| transcript에 영어·한국어 밖의 언어 | `transcription.json`의 `languageCodes` |
| 6번에서 고유명사가 틀리게 적힘 | 호스트의 어휘 목록(문단 단어 고르는 규칙) |
| 8번에서 마지막 문장이 빠짐 | 호스트의 Done 처리(`audioStreamEnd` 뒤 대기) |
| 피드백이 20초 넘게 걸림 | 설정 `SUMMARY_EFFORT`, `SUMMARY_MODEL` |
