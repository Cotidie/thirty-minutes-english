# Example Coach

방금 배운 표현이나 단어로 사용자가 만든 문장 하나를 듣고, 두 가지를 순서대로 말해 주는 코치: 그 문장을 원어민이 말하는 대로 바꿔 말하기(paraphrase), 그리고 고친 곳마다 짧은 피드백 한 문장. 그걸로 끝이다. 되묻거나 새 문장을 지어 주지 않는다. 문장 하나가 한 라운드다.

단어(Vocabulary)일 때는 판단 프롬프트가 `prompts/feedback-word.md`로 바뀐다: 사용자는 그 단어에 맞춰 그려진 그림을 보며 문장을 말하고, paraphrase는 가벼운 교정이 아니라 그 그림을 원어민이 그 단어로 묘사하는 문장(자유로운 의역)이 되며, feedback의 첫 줄은 언제나 단어 사용에 대한 것이다. 호스트는 `{{word}}`, `{{pos}}`, `{{meaning}}`, `{{scene}}`(그림 설명), `{{sentence}}`를 채운다.

두 부분으로 나뉜다. 귀와 입은 GPT-Live 음성 에이전트(`prompts/live.md`): 문장을 끝까지 듣고 "Got it." 한마디, 그 뒤 호스트가 넘겨주는 문장을 그대로 읽는다. 판단은 텍스트 모델(`prompts/feedback.md`): 문장 transcript를 받아 `paraphrase`(문장)와 `feedback`(고친 곳마다 한 문장씩 담은 목록) 두 필드를 돌려준다. 호스트 앱이 둘을 잇는다.

| 항목 | 값 |
|---|---|
| 모델 | `gpt-live-1` (full duplex, 오디오 입출력) |
| 엔드포인트 | `POST /v1/live/sessions` (WebRTC) |
| 음성 | `gleam` (북미 영어). 세션 시작 후 못 바꾼다 |
| 백엔드 위임 | 없음 (`delegation.type: client`, 위임 이벤트는 무시) |
| 비용 | 분당 $0.05, 초 단위. 한 문장 15~20초면 약 $0.015 |
| 응답 형태 | 음성 + 같은 내용의 transcript 텍스트. 기록에는 transcript가 아니라 텍스트 모델의 두 필드를 쓴다 |
| 텍스트 모델 | 호스트가 정한다. `english-speaking-claude`는 `claude` CLI(기본 opus, effort low, 도구 없음)에 `prompts/feedback.md`를 넣고 JSON 스키마 `{paraphrase, feedback}`으로 받는다 |

## 입력

| 이름 | 형식 | 비고 |
|---|---|---|
| `expression` | 구문 또는 단어 | `session.json`의 developer 메시지에 넣는다 |
| `meaning` | 짧은 뜻풀이 | 같은 메시지. 표현을 잘못 쓴 문장을 알아보는 기준 |
| `usage_note` | 한 줄 | 같은 메시지. 전치사·격식 같은 학습자가 자주 틀리는 점, 단어라면 품사. 없으면 빈 문자열 |
| 마이크 | 브라우저 `getUserMedia` 오디오 트랙 | 누가 말하는지 구분하지 않는다 |

## 한 라운드

1. 호스트가 `session.json`의 자리를 채우고 `instructions`에 `prompts/live.md` 원문을 넣어 세션을 만든다.
2. `session.started`가 오면 호스트는 "말하세요" 표시만 한다. 인사말 없음.
3. 사용자가 그 표현으로 문장 하나를 말한다. 끝날 때까지 에이전트는 침묵한다. 중간에 멈추거나 다시 시작해도 기다린다.
4. 문장이 끝나면 에이전트가 "Got it." 한마디. 호스트는 이 첫 발화를 신호로 사용자 transcript를 텍스트 모델에 보낸다(`prompts/feedback.md`의 `{{expression}}`, `{{meaning}}`, `{{usage_note}}`, `{{sentence}}`를 채운다). 답이 올 때까지 라운드를 닫지 않는다.
5. 호스트가 `session.instructions.append`로 "Now say exactly this, word for word, then stop: <paraphrase> <feedback>"을 보낸다. 에이전트는 그 문장을 보통 속도로 한 번 읽고 멈춘다.
6. 따라 말하면 "Good" 한마디. 새 문장이 오면 3번부터 다시.
7. 사용자가 "done"이라 하거나 호스트가 종료 지시를 보내면 "Goodbye" 한마디. 호스트가 `session.close`를 보내고 `session.closed`를 기다린다.

## 텍스트 모델의 판단

- 뜻과 표현은 그대로 두고 원어민이 다르게 말할 곳을 모두 고친다(관사, 전치사, 어색하거나 무거운 단어, 어순, 군더더기). 가장 큰 것 하나만 고르지 않는다. 이미 자연스러우면 그대로 되풀이하고 그렇다고 말한다.
- 피드백은 고친 곳마다 짧은 문장 하나, 중요한 것부터. 전체 40단어 안팎. 표현을 잘못 썼으면(전치사, 뜻, 격식) 바꿔 말한 문장에서 바로잡고 피드백에서 먼저 짚는다.
- 문장에 표현이 없으면 바꿔 말한 뒤 표현이 빠졌다고만 한다.
- 두 필드 모두 소리 내어 읽히므로 말하듯 쓴다. 따옴표로 문장 전체를 감싸지 않는다.

## 호스트 앱이 할 일

이벤트와 명령은 `../read-aloud-coach/AGENT.md`의 표와 같다. 라운드가 끝나면 사용자 문장과 텍스트 모델의 두 필드(`paraphrase`와 `feedback` 항목들을 공백으로 이은 한 줄)를 표현과 함께 저장한다. 화면에서는 `feedback` 항목을 불릿으로 보여 준다. 첫 문장이 바꿔 말한 예문, 나머지가 피드백이라는 기록 형식은 그대로다.

## 한계

- 판정은 "원어민이 이렇게 말한다" 수준이다. 문법 설명은 하지 않는다.
- 문장 하나까지다. 두 문장을 이어 말하면 마지막 문장만 다룬다.
- 세션 시작 시 WebRTC는 15초 분량을 먼저 과금하고 실제 사용량에서 상계한다.
- 마이크는 `localhost` 또는 HTTPS에서만 열린다.

## 프롬프트를 고칠 때

판단 규칙은 `prompts/feedback.md`에만 있다. 규칙 하나를 바꾸면 `evals/cases.md`에서 그 규칙에 해당하는 번호만 다시 확인한다(기대 반응은 텍스트 모델의 두 필드로 본다). `prompts/live.md`는 듣기·"Got it."·받아 읽기만 맡고, 섹션 구조는 OpenAI 음성 프롬프트 권장 형태(Role & Objective, Context, Instructions, Conversation Flow, Language)를 따른다. 바꿔 말하기와 피드백 한 문장 외의 일(문법 강의, 발음 교정, 새 예문 만들기)을 추가하지 않는다.

참고: [GPT-Live 시작](https://developers.openai.com/api/docs/guides/live), [프롬프트 작성](https://developers.openai.com/api/docs/guides/live-prompting)
