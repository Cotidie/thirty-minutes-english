# Summary Coach

문단 하나를 보면서 무슨 내용인지 영어로 말하면, 그 말을 받아 적고 한눈에 읽히는 피드백 하나를 돌려주는 코치. 한 번 말하고 한 번 받는 짧은 활동이라 피드백은 언제나 같은 세 줄 형식이다. 되묻거나 대화하지 않고, 소리를 내지 않는다.

두 부분으로 나뉜다. 귀는 Gemini 전사 모델(`transcription.json`): 말을 받아 적기만 하고 프롬프트가 없다. 판단은 텍스트 모델(`prompts/feedback.md`): 문단과 transcript를 받아 `prompts/feedback.schema.json` 모양의 세 필드를 돌려준다. 둘 다 문단을 안다: 귀는 문단의 단어를 어휘 힌트로, 판단은 문단 전문을 받는다. 호스트 앱이 둘을 잇는다.

| 항목 | 값 |
|---|---|
| 전사 모델 | `gemini-3.5-transcribe-live` (Gemini Live API, WebSocket). 텍스트만 내고 음성 출력은 없다 |
| 언어 | `en-US`, `ko-KR`. 다른 언어로 받아 적지 않게 유도한다 |
| 판단 모델 | 호스트가 정한다. `english-speaking`은 `claude` CLI, Opus에 effort medium(설정 `SUMMARY_MODEL`, `SUMMARY_EFFORT`), 도구 없음 |
| 키 | `GEMINI_API_KEY`. 음성 코치의 provider 설정과 상관없다 |
| 길이 | 말하기 1분 안팎. 전사 세션은 최대 10분 |

## 입력

| 이름 | 형식 | 비고 |
|---|---|---|
| `paragraph` | 문단 원문 | 귀에는 단어 목록(`customVocabulary`)으로, 판단에는 `{{paragraph}}`로 들어간다 |
| 마이크 | 16 kHz 16-bit PCM, 100 ms 조각 | 브라우저가 WebSocket으로 직접 보낸다 |

## 한 라운드

말하기, 받아 적기, 판단의 세 단계다. 문단은 처음부터 끝까지 화면에 보인다.

1. **연결.** 호스트가 `transcription.json`을 복사해 `inputAudioTranscription.customVocabulary`에 문단 단어를 넣는다(4글자 이상이거나 대문자 약어, 중복 없이 최대 100개). 서버가 그 설정에 묶인 일회용 토큰을 만들고 브라우저가 연결한다.
2. **말하기와 받아 적기.** 사용자가 말한다. 말이 멈출 때마다 그 발화가 `serverContent.inputTranscription`으로 한 덩어리씩 오고, 호스트는 공백 하나로 잇는다. 대답할 차례가 없으니 침묵이 길어도 라운드는 닫히지 않는다.
3. **Done.** 호스트가 마이크 전송을 멈추고 `realtimeInput.audioStreamEnd`를 보낸다. 말하던 중이면(`voiceActivity`가 `ACTIVITY_START` 뒤 아직 `ACTIVITY_END` 전) 마지막 발화가 올 때까지 최대 3초 기다렸다가 소켓을 닫는다.
4. **판단.** transcript가 비어 있지 않으면 `prompts/feedback.md`의 `{{paragraph}}`, `{{summary}}`를 채워 판단 모델을 한 번 부른다. 출력은 `prompts/feedback.schema.json`으로 묶는다. 비어 있으면 판단하지 않는다.
5. **저장하고 보여 주기.** 판단이 오면 묻지 않고 문단, transcript, 피드백, 말한 시간(초)을 저장한다. 진행 카드는 닫히고, 같은 자리에 저장된 카드가 아래 형식으로 남는다(최신이 위). 다시 하기는 1번부터.

## 피드백 형식

언제나 같은 순서, 같은 모양이다. 빈 줄은 빠지고 모범답안은 늘 있어서, 화면에서 4줄을 넘지 않는다.

| 줄 | 필드 | 한도 |
|---|---|---|
| Missed | `missed`: 빠뜨리거나 틀린 핵심 하나. 틀렸으면 "X, not Y" | 0~1개, 12단어 |
| Say it better | `fixes[]`: `said` → `better` | 0~2개, 6단어 → 8단어 |
| Model answer | `summary`: 사용자가 말한 것을 줄인 모범답안 | 1~2문장, 25단어 |

- 모범답안은 사용자의 요점과 말로 짓고, 고친 표현을 반영하고, 문단의 핵심을 바로 세운다. 사용자가 말한 것보다 길지 않다.
- 칭찬, 문법 설명, 고친 이유는 없다. `said` → `better`만으로 읽힌다.

## 호스트 앱이 할 일

- API 키는 서버에만 둔다. 브라우저는 일회용 토큰이 든 URL과 설정만 받는다.
- 3번의 대기 없이 소켓을 바로 닫으면 마지막 문장이 사라진다.
- 저장한 피드백은 다시 판단하지 않는다. 형식이 바뀌기 전 기록에 남은 필드(`why`)는 읽을 때 버린다.

## 한계

- 언어 지정은 유도다. 드물게 영어·한국어 밖의 언어가 나올 수 있다.
- 어휘 힌트는 받아 적기를 문단의 표기 쪽으로 끌어당긴다. 발음이 틀린 단어도 문단 표기로 적힐 수 있다. 발음 판정은 Read aloud의 몫이다.
- 판단은 transcript만 본다. 억양, 속도, 발음은 다루지 않는다.
- 마이크는 `localhost` 또는 HTTPS에서만 열린다.

## 프롬프트를 고칠 때

판단 규칙은 `prompts/feedback.md`에, 출력 모양은 `prompts/feedback.schema.json`에만 있다. 필드나 개수 한도를 바꾸면 두 파일과 화면을 같이 바꾼다. 고친 뒤 `evals/cases.md`에서 해당 번호만 다시 확인한다. 귀(`transcription.json`)에는 프롬프트가 없다. 바꿀 수 있는 것은 모델과 언어뿐이다.

참고: [Gemini Live 전사](https://ai.google.dev/gemini-api/docs/live-api/live-transcribe)
