# 발음·끊어읽기 코치 조사 (2026-09-21)

Read aloud 코치가 발음 오류와 구 안에서 멈춤을 잘 못 잡는 원인과, 이를 고치기 위해 남들이 쓰는 구조를 조사한 기록. 세 갈래: 오픈소스 사례, 평가 API 비교, 실시간 음성 에이전트 스택.

## 원인

| 사실 | 근거 |
|---|---|
| GPT-Live, Gemini Live 모두 툴에 오디오를 넘기지 않는다. 툴은 transcript 텍스트만 받는다 | OpenAI live-delegation 문서, Gemini live-guide |
| 두 API 모두 음소·휴지 관련 기능이 없다 | 모델 문서 |
| 오디오 LLM에 음소 판정을 시키면 신뢰도가 낮다. GPT-4o는 speechocean762에서 41~48% 발화에 결과를 못 냈고 문장 정확도 상관 0.47 (Azure PA 0.70) | arXiv 2503.11229, 2509.14187 |
| 그러므로 지금 구조(S2S 모델이 귀로 듣고 판정)는 프롬프트를 아무리 다듬어도 한계가 있다 | |

## 공통 패턴 (오픈소스 8곳)

1. 읽을 텍스트를 알고 있으므로 scripted assessment. 텍스트를 G2P(espeak-ng, g2p_en)로 음소열로 만든다.
2. 오디오를 음소열에 강제 정렬(Charsiu, wav2vec2 CTC, WhisperX, Azure).
3. 음소별 GOP = log P(기대 음소) − log P(경쟁 음소). 2025~26에는 정렬 없는 CTC-forward GOP가 기준선.
4. 유창성은 단어 타임스탬프나 VAD에서 나온 휴지 통계(휴지 비율, WPM). 휴지 "위치" 오류를 단어 단위로 내는 건 Azure뿐.
5. LLM은 맨 뒤에서 점수 JSON을 받아 코칭 문장 1~3줄만 쓴다. 판정은 절대 LLM이 하지 않는다 (PTE-Coach, Lingua_Pro가 이 경계를 명시).
6. 거의 전부 발화 단위 사후 처리(3~20초). 실시간 세션 안에서 코치를 돌리는 건 Speak.com(LiveKit Agents) 정도.

대표 저장소: OpenPronounce (MIT, wav2vec2+DTW, 음소만, 73★), echoic (WhisperX+wav2vec2, 60★), speaklab (faster-whisper+GOP+Ollama), PTE-Coach (규칙 엔진 먼저, LLM 마지막), Thiagohgl/ai-pronunciation-trainer (520★, AGPL, 기본선). 끊어읽기 위치를 판정하는 오픈소스는 없다. 논문은 있다: Interspeech 2023 "Assessing Phrase Break of ESL Speech" (정렬 → 휴지 토큰 삽입 → PLM이 위치별 판정), 코드 미공개.

## 평가 API 비교

| API | 음소 점수 | 단어 오류 | 끊어읽기 위치 | 스트리밍 | 가격 |
|---|---|---|---|---|---|
| **Azure Pronunciation Assessment** | 0~100, IPA, NBest 5 | Mispronunciation/Omission/Insertion, AccuracyScore | **단어별 `UnexpectedBreak`·`MissingBreak` confidence (권장 임계 0.75), `Monotone`.** en-US만 | SDK 연속 인식, 브라우저 마이크 직접 | STT 요금(약 $1.3/h) + prosody 추가요금(미확인, 약 $0.3/h). 무료 F0 월 5시간 |
| Speechace | ARPABET 음소, 강세 점수 | quality_score | 휴지 목록만, 위치 판정 없음 | 파일 업로드만 | $40~125/월 |
| ELSA API | nativeness 0~100 | correct/incorrect | intonation_score, 휴지 정보, 위치 판정 없음 | WebSocket | $0.008~0.01/15초 |
| SpeechSuper | 음소 점수 | 있음 | 리듬, 강세, 휴지 수, 위치 판정 미확인 | HTTP, WS | $0.006/문장, 월 $20 최소 |
| Google STT, Deepgram, AssemblyAI, ElevenLabs Scribe, OpenAI transcribe | 없음 | 타임스탬프·confidence만 | 없음 | 있음 | 채점 용도 아님 |
| Gemini / GPT audio | 프롬프트 의존 | 프롬프트 의존 | 없음 | Live | 판정용 부적합 (위 근거) |

한국인 학습자 근거: Won (2025, J. Second Language Pronunciation) 한국 초등학생 190개 낭독에서 Azure 음소 점수는 인간 평가와 중간 상관, Kaldi GOP는 무상관. 벤더별 L1 한국어 특화 자료는 없다.

## 실시간 스택

| 항목 | GPT-Live | Gemini Live | Pipecat / LiveKit (자체 호스팅 cascade) |
|---|---|---|---|
| 외부 신호로 끼어들기 | `session.instructions.append`가 현재 발화를 끊는다 (문서화) | 텍스트 턴 전송만 가능, 끊기 원시 명령 없음 | `broadcast_interruption()` + `TTSSpeakFrame`, `session.say()` |
| 마이크 오디오 분기 | 브라우저에서 MediaStream 복제 | 브라우저에서 PCM 복제 | 파이프라인 프로세서가 프레임을 본다 |
| 비용 | $0.05/분 | $0.023/분 | $0.07~0.13/분 (STT+LLM+TTS) |
| 지연 | S2S p50 540~580ms | 동일급 | p50 610~810ms |
| Claude | 텍스트 LLM으로만. 2026-09 기준 오디오 입력 API 없음 | | |

## 결론

- 판정은 Azure Pronunciation Assessment. 끊어읽기 위치 신호를 단어 단위로 주는 유일한 API이고 브라우저에서 바로 스트리밍된다.
- 코치 음성(입)은 기존 S2S 연결을 유지하되 "귀" 역할을 뺀다. 코치는 판정 결과를 받아서 말만 한다.
- 오디오 LLM에게 판정을 맡기는 프롬프트 튜닝은 중단한다.

## 출처

- Azure PA: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-pronunciation-assessment
- Azure 한계·상관: https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/speech-service/pronunciation-assessment/characteristics-and-limitations-pronunciation-assessment
- OpenPronounce: https://github.com/Halleck45/OpenPronounce
- PTE-Coach: https://github.com/LiFAN-WUST/PTE-Coach
- Phrase break 논문: https://arxiv.org/abs/2306.04980
- LLM 판정 한계: https://arxiv.org/html/2503.11229v1 , https://arxiv.org/html/2509.14187v1
- Speak.com 플랫폼: https://www.speak.com/blog/building-speaks-voice-agent-platform
- GPT-Live delegation: https://developers.openai.com/api/docs/guides/live-delegation
- Pipecat interruption: https://reference-server.pipecat.ai/en/latest/api/pipecat.processors.frame_processor.html
- Korean learners: https://www.jbe-platform.com/content/journals/10.1075/jslp.25012.won
