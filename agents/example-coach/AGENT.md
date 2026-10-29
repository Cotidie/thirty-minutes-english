# Example Coach

방금 배운 단어로 사용자가 만든 문장 하나를 듣고, 두 가지를 순서대로 말해 주는 코치: 그 단어에 맞춰 그려진 그림을 원어민이 그 단어로 묘사하는 문장(paraphrase), 그리고 고친 곳마다 짧은 피드백 한 문장. 그걸로 끝이다. 되묻거나 새 문장을 지어 주지 않는다. 문장 하나가 한 라운드다.

두 부분으로 나뉜다. 귀와 입은 Gemini Live 음성 에이전트(`prompts/live.md`): 문장을 끝까지 듣고 "Got it." 한마디, 그 뒤 호스트가 넘겨주는 문장을 그대로 읽는다. 판단은 텍스트 모델(`prompts/feedback.md`): 문장 transcript를 받아 `paraphrase`(문장)와 `feedback`(고친 곳마다 한 문장씩 담은 목록) 두 필드를 돌려준다. 호스트 앱이 둘을 잇는다.

| 항목 | 값 |
|---|---|
| 모델 | 호스트 설정의 Gemini Live 모델 (`english-speaking-claude`는 `VOICE_MODEL`, 오디오 입출력) |
| 연결 | 호스트가 일회용 토큰을 받아 넘기고, 브라우저가 WebSocket으로 붙는다 |
| 음성 | 호스트 설정의 Gemini 음성 (`VOICE_NAME`). 세션 시작 후 못 바꾼다 |
| 응답 형태 | 음성 + 같은 내용의 transcript 텍스트. 기록에는 transcript가 아니라 텍스트 모델의 두 필드를 쓴다 |
| 텍스트 모델 | 호스트가 정한다. `english-speaking-claude`는 `claude` CLI(기본 opus, effort low, 도구 없음)에 `prompts/feedback.md`를 넣고 JSON 스키마 `{paraphrase, feedback}`으로 받는다 |

## 입력

| 이름 | 형식 | 비고 |
|---|---|---|
| `word` | 단어 | `prompts/context.md`와 `prompts/feedback.md`에 넣는다 |
| `meaning` | 짧은 뜻풀이 | 같은 두 곳. 단어를 잘못 쓴 문장을 알아보는 기준 |
| `pos` | 품사 | 같은 두 곳 |
| `scene` | 그림 설명 한 줄 | `prompts/feedback.md`에만. 그림이 없으면 "no picture; go by the sentence" |
| 마이크 | 브라우저 `getUserMedia` 오디오 트랙 | 누가 말하는지 구분하지 않는다 |

## 한 라운드

1. 호스트가 `prompts/context.md`의 자리를 채워 `prompts/live.md` 원문 뒤에 붙이고, 그 둘을 system instruction으로 세션을 연다.
2. `session.started`가 오면 호스트는 "말하세요" 표시만 한다. 인사말 없음.
3. 사용자가 그림을 보며 그 단어로 문장 하나를 말한다. 끝날 때까지 에이전트는 침묵한다. 중간에 멈추거나 다시 시작해도 기다린다.
4. 문장이 끝나면 에이전트가 "Got it." 한마디. 호스트는 이 첫 발화를 신호로 사용자 transcript를 텍스트 모델에 보낸다(`prompts/feedback.md`의 `{{word}}`, `{{pos}}`, `{{meaning}}`, `{{scene}}`, `{{sentence}}`를 채운다). 답이 올 때까지 라운드를 닫지 않는다.
5. 호스트가 text turn으로 "Now say exactly this, word for word, then stop: <paraphrase> <feedback>"을 보낸다. 에이전트는 그 문장을 보통 속도로 한 번 읽고 멈춘다.
6. 따라 말하면 "Good" 한마디. 새 문장이 오면 3번부터 다시.
7. 사용자가 "done"이라 하거나 호스트가 종료 지시를 보내면 "Goodbye" 한마디. 호스트가 세션을 닫고 `session.closed`를 기다린다.

## 텍스트 모델의 판단

- paraphrase는 가벼운 교정이 아니라 그 그림을 원어민이 그 단어로 묘사하는 문장이다. 뜻은 지키되 자연스러운 표현, 단어가 보통 어울리는 짝(연어), 어순으로 자유롭게 바꾼다. 이미 자연스러우면 그대로 되풀이한다.
- 단어는 반드시 들어가고, 원어민이 쓰는 대로 쓰인다(뜻, 품사, 전치사, 연어). 문장에 단어가 없으면 알맞은 자리에 넣는다.
- 그림이나 문장에 없는 내용은 더하지 않는다. 한 문장.
- feedback의 첫 줄은 언제나 단어 사용에 대한 것이다. 그다음 고친 곳마다 한 문장, 고치지 않은 것은 말하지 않는다. 전체 40단어 안팎, 문법 용어 없음.
- 두 필드 모두 소리 내어 읽히므로 말하듯 쓴다. 따옴표로 문장 전체를 감싸지 않는다.

## 호스트 앱이 할 일

이벤트와 명령은 `../read-aloud-coach/AGENT.md`의 표와 같다. 라운드가 끝나면 사용자 문장과 텍스트 모델의 두 필드(`paraphrase`와 `feedback` 항목들을 공백으로 이은 한 줄)를 단어와 함께 저장한다. 화면에서는 `feedback` 항목을 불릿으로 보여 준다. 첫 문장이 바꿔 말한 예문, 나머지가 피드백이라는 기록 형식은 그대로다.

## 한계

- 판정은 "원어민이 이렇게 말한다" 수준이다. 문법 설명은 하지 않는다.
- 문장 하나까지다. 두 문장을 이어 말하면 마지막 문장만 다룬다.
- 마이크는 `localhost` 또는 HTTPS에서만 열린다.

## 프롬프트를 고칠 때

판단 규칙은 `prompts/feedback.md`에만 있다. 규칙 하나를 바꾸면 `evals/cases.md`에서 그 규칙에 해당하는 번호만 다시 확인한다(기대 반응은 텍스트 모델의 두 필드로 본다). `prompts/live.md`는 듣기·"Got it."·받아 읽기만 맡고, 섹션 구조(Role & Objective, Context, Instructions, Conversation Flow, Language)를 지킨다. 바꿔 말하기와 피드백 외의 일(문법 강의, 발음 교정, 새 예문 만들기)을 추가하지 않는다.
