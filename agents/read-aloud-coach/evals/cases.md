# 검증 시나리오

프롬프트나 임계값을 고칠 때마다 사람이 아래 11개를 직접 읽고 확인한다. 한 시나리오는 1~2분, 전체 약 20분. 판정은 Azure가 하므로 각 행의 기대는 두 단계다: 문단의 그 단어에 표시가 뜨는가(판정기), 표시를 클릭했을 때 코치가 두 박자("You said X. It's Y.")로 말하고 끊는가(프롬프트). 읽는 동안 코치는 켜지지 않는다.

문단 예시(모든 시나리오 공통):

> Researchers verified that the new battery lasts twice as long in cold weather. Is it ready for mass production? Not yet, because the factory asked for three more tests, and still needs to solve problems of cost, safety, and supply.

## 발음

| # | 읽는 방식 | 기대 반응 |
|---|---|---|
| 1 | 전부 정확하게 읽기 | 표시 없음. Done을 누르면 기록 없이 끝 |
| 2 | verified를 "버리파이드"로 | 구가 끝난 뒤 verified에 붉은 밑줄. 클릭하면 "You said berify. It's verify. Try it." 4초 이내 |
| 3 | production의 강세를 PRO-duction으로 | 표시. 클릭하면 pro-DUC-tion |
| 4 | factory를 "팩토리"(f→p)로 | 표시. 클릭하면 f 교정 |
| 5 | three를 "쓰리"(th→s)로 | 표시. 클릭하면 th 교정 |
| 6 | asked를 "애스크"로(어말 자음군 탈락) | 표시. 클릭하면 끝소리까지 |

## 그 밖

| # | 읽는 방식 | 기대 반응 |
|---|---|---|
| 7 | "twice as / long"처럼 구 안에서 멈추거나, 쉼표를 무시하고 한 호흡에 읽기 | 침묵. 끊어 읽기는 보지 않음 |
| 8 | 의문문 끝을 내려 읽기 | 침묵. 억양은 보지 않음 |
| 9 | 클릭해 교정받은 단어를 따라 말하기 | 맞으면 표시가 초록 ✓. 코치는 아무 말 없음(이미 끊긴 뒤) |
| 10 | verified를 고친 뒤 뒷문장 solve를 "솔브"(v→b)로 | solve에도 표시 |
| 11 | 옆에서 소음이 나는 채로 battery를 애매하게 읽거나 짧게 머뭇거리기 | 침묵. 확신 없으면 교정하지 않음 |

실패 기준:

| 실패 | 먼저 고칠 곳 |
|---|---|
| 교정 뒤에 인사나 질문이 붙음 | `## Instructions`의 'no greeting, no closing' |
| 2~6번, 10번에 표시가 안 뜸 | `ASSESS_WORD_SCORE`를 70으로 올려 본다 |
| 11번에 표시가 뜸 | `ASSESS_WORD_SCORE`를 50으로 내려 본다 |
| 교정 문구가 매번 똑같음 | `Sample phrases`의 vary 지시 |

교정 한 번이 5초를 넘으면 sample phrase를 더 짧게 바꾼다.
