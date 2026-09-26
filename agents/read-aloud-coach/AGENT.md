# Read-Aloud Coach

읽는 사람이 화면의 표시를 클릭했을 때, 그 단어 하나를 말로 바로잡는 음성 에이전트. 읽는 동안에는 켜지지 않는다: 호스트 쪽 판정기(Azure Pronunciation Assessment)가 문단 위에 **단어 발음**과 **구 안에서 끊어 읽기** 두 가지를 표시하고, 클릭마다 짧은 세션 하나를 열어 교정 한 줄을 듣고 끊는다. 억양, 속도, 의미는 건드리지 않고 문단을 대신 읽어 주지도 않는다.

| 항목 | 값 |
|---|---|
| 모델 | `gpt-live-1` 또는 Gemini Live. 오디오 출력, transcript 텍스트 동봉. 입력 마이크는 꺼 둔다 |
| 세션 | `session.json`의 `{{paragraph}}`를 채우고 `instructions`에 `prompts/live.md` 원문 |
| 길이 | 클릭 하나에 세션 하나. 교정 한 줄(4초) 뒤 2초 침묵이면 호스트가 끊는다. GPT-Live는 15초 최소 과금 |

## 한 번의 호출

1. 호스트가 세션을 열고 마이크 트랙을 끈다.
2. `session.started`에 지시 하나를 보낸다: `Correction: "verified", heard b for v.` 또는 `Correction: "as long", paused between "as" and "long".`
3. 코치가 두 박자로 말한다: "You said berify. It's verify. Try it." / "You paused between July and 1969. Put them together: July nineteen sixty-nine. Try it." 인사도 마무리도 없다.
4. 코치 transcript가 2초간 멈추면 호스트가 `close`. 최대 15초.

GPT-Live는 `session.instructions.append`, Gemini는 text turn으로 보낸다. 자막은 `session.output_transcript.delta`를 이어 붙인다(Gemini의 `<no speech>` 태그는 호스트가 지운다).

## 한계

- 판정은 판정기의 몫이다. 코치가 지시 밖의 말을 하면 프롬프트 버그다. 임계값은 호스트 설정(`ASSESS_WORD_SCORE`, `ASSESS_BREAK_CONFIDENCE`).
- 따라 읽기 확인도 판정기가 한다(표시가 초록으로 바뀜). 코치는 듣지 않는다.

## 프롬프트를 고칠 때

`prompts/live.md`가 유일한 원본. 규칙은 원칙으로, 문구는 sample phrases로. 고친 뒤 `evals/cases.md`에서 해당 번호만 다시 읽어 확인한다.
