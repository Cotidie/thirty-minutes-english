# Phrase Coach

대화 중 막힌 표현을 음성으로 묻고 답 하나를 받는 에이전트. 한국어로 물어도 되고, 자기가 쓴 영어가 이상한지 확인해도 된다. 답은 표현 하나, 부연은 붙어도 짧은 한 문장, 10초 이내. 되묻거나 잡담하지 않는다. 한 질문이 한 라운드다. 호스트 앱은 마이크와 현재 대화 주제만 넘기면 된다.

| 항목 | 값 |
|---|---|
| 모델 | `gpt-live-1` (full duplex, 오디오 입출력) |
| 엔드포인트 | `POST /v1/live/sessions` (WebRTC) |
| 음성 | `gleam` (북미 영어). 세션 시작 후 못 바꾼다 |
| 백엔드 위임 | 없음 (`delegation.type: client`, 위임 이벤트는 무시) |
| 비용 | 분당 $0.05, 초 단위. 한 질문 10~20초면 약 $0.015 |
| 응답 형태 | 음성 + 같은 내용의 transcript 텍스트 |

## 입력

| 이름 | 형식 | 비고 |
|---|---|---|
| `topic` | 짧은 문구 | `session.json`의 developer 메시지에 넣는다. 질문이 애매할 때 어느 쪽 표현을 고를지 판단하는 데만 쓴다. 없으면 일반 대화로 둔다 |
| 마이크 | 브라우저 `getUserMedia` 오디오 트랙 | 누가 말하는지 구분하지 않는다 |

## 한 라운드

1. 호스트가 `session.json`에 `topic`을 채우고 `instructions`에 `prompts/live.md` 원문을 넣어 세션을 만든다.
2. `session.started`가 오면 호스트는 "물어보세요" 표시만 한다. 인사말 없음.
3. 사용자가 묻는다. 한국어, 어색한 영어, 확인용 영어, 중간에 막힌 조각 다 받는다. 질문이 끝날 때까지 에이전트는 침묵한다.
4. 표현 하나를 두 번 말한다. 부연은 짧은 한 문장까지, 쓸 자리가 달라질 때만 붙이고 아니면 생략한다. 필요할 때만 대안 하나. 10초 이내. 이미 자연스러운 영어면 그렇다고만 한다.
5. 애매하면 한 번 되묻고 기다린다. 두 해석을 다 답하지 않는다.
6. 따라 말하면 "That's it" 한마디. 새 질문이 오면 3번부터 다시.
7. 사용자가 "고마워"라 하거나 호스트가 종료 지시를 보내면 "Goodbye" 한마디. 호스트가 `session.close`를 보내고 `session.closed`를 기다린다.

## 호스트 앱이 처리할 이벤트

`read-aloud-coach`와 동일하다. 이벤트 이름은 GPT-Live 공식 이름 그대로다.

| 이벤트 | 호스트 동작 |
|---|---|
| `session.started` | "물어보세요" 상태로 전환. `session.id` 보관 |
| `session.input_transcript.delta` | 사용자 자막 행에 `delta`를 순서대로 이어 붙인다. 공백 정리 금지 |
| `session.output_transcript.delta` | 코치 자막 행에 이어 붙인다 |
| `session.usage.updated` | `usage.seconds`를 화면에 표시(누적 스냅샷, 더하지 않는다) |
| `session.delegation.created` | 무시. 이 에이전트는 백엔드가 없다 |
| `error` | `error.message`를 표시하고 `session.closed`를 기다린다 |
| `session.closed` | 마이크 트랙과 peer connection 정리. 자막 두 줄을 기록으로 저장 |

호스트가 보낼 수 있는 명령:

| 명령 | 용도 |
|---|---|
| `session.instructions.append` `{ delegation_id: null, content: "The round is over. Say your closing now." }` | 사용자가 닫을 때. "Goodbye"를 받고 끝낸다 |
| `session.close` | 라운드 종료. `session.closed`가 올 때까지 연결을 유지한다 |

## 복습 카드

라운드가 끝나면 자막 두 줄을 그대로 보관한다. 카드는 나중에 한 번에 만든다: 텍스트 모델(`gpt-5.6-luna`, reasoning `low`)에 `prompts/summarize.md`와 라운드 목록을 넣고 `cards.schema.json`으로 받는다. 한 번 만든 카드는 캐시하고 다시 만들지 않는다. GPT-Live는 구조화 출력을 지원하지 않으므로 이 단계가 필요하다.

## 한계

- 판정은 "원어민이 이렇게 말한다" 수준이다. 사용 빈도 통계나 코퍼스 근거는 없다.
- 문법 설명은 하지 않는다. 표현을 주는 것이 일이다.
- 긴 문장 통째 번역에는 맞지 않는다. 한 표현, 한 문장까지다.
- 세션 시작 시 WebRTC는 15초 분량을 먼저 과금하고 실제 사용량에서 상계한다. 10초짜리 질문도 15초를 낸다. 질문을 몰아서 하면 싸다.
- 마이크는 `localhost` 또는 HTTPS에서만 열린다.

## 통합 절차

1. 서버: `POST /api/phrase/sessions`. 본문 `{ sdp, topic? }`. `session.json`을 채워 OpenAI로 중계하고 응답을 그대로 돌려준다. API 키는 서버 환경변수 `OPENAI_API_KEY`에만 둔다.
2. 브라우저: 전역 Ask 버튼. 누르면 마이크 트랙 추가, `oai-events` 데이터 채널 생성, SDP offer를 1번 엔드포인트로 보내고 answer를 적용한다.
3. 브라우저: 라운드가 끝나면 자막 두 줄을 `POST /api/asks`에 저장한다.
4. 검증: `evals/cases.md`의 12개 시나리오를 직접 말해 본다. 약 12분.

`english-speaking-claude`가 이 절차대로 붙어 있다. 프롬프트와 세션 설정은 이 폴더에서만 읽는다(`PHRASE_AGENT_DIR`).

## 프롬프트를 고칠 때

`prompts/live.md`가 유일한 원본이다. 규칙 하나를 바꾸면 `evals/cases.md`에서 그 규칙에 해당하는 번호만 다시 확인한다. 섹션 구조는 OpenAI 음성 프롬프트 권장 형태(Role & Objective, Context, Instructions, Conversation Flow, Language)를 따른다. 이 뼈대는 유지하고 문장만 바꾼다. 규칙은 원칙으로 쓰고 문구는 sample phrases로 보여 준다. 표현을 주는 일 외의 기능(문법 강의, 발음 교정, 잡담)을 추가하지 않는다. 발음 교정은 `../read-aloud-coach`가 한다.

참고: [GPT-Live 시작](https://developers.openai.com/api/docs/guides/live), [프롬프트 작성](https://developers.openai.com/api/docs/guides/live-prompting), [세션 관리](https://developers.openai.com/api/docs/guides/live-conversations)
