# 판정 API 성능 비교: Azure vs ELSA vs Speechace

상태: 계획. 실행 전. 결과가 나오면 이 문서에 표를 채우고 `docs/superpowers/specs/2026-09-21-read-aloud-assessor-design.md`의 판정 API를 확정한다.

## 공개된 수치는 비교가 안 된다

| API | 벤더 주장 | 독립 연구 | 왜 비교 불가 |
|---|---|---|---|
| Azure PA | 인간 평가와 Pearson > 0.5 (수치 하나, 언어·점수 종류 불명) | Won 2025: 한국 초등학생 190개 낭독, 음소 점수가 인간 평가와 중간 상관. arXiv 2503.11229: speechocean762 문장 정확도 0.70 | 유일하게 공개 벤치마크 수치가 있음 |
| Speechace | IELTS 인간 채점과 0.68점 이내, hold-out Pearson 0.9 | Arabic L1 학습자 연구: 발음 점수 평균이 인간 평가자와 비슷(7.71 vs 7.65) | IELTS 밴드 수준 총점 상관. 단어·음소 판정 정확도 아님 |
| ELSA | 전문가 평가와 ±1 CEFR 밴드 안 93.88% 일치 | IJCALLT 2026 종단 연구: fluency는 인간과 약~중간 상관, 분절음 위주, 초분절은 못 잡음 | CEFR 밴드 일치율. 단어·음소 판정 정확도 아님 |

세 회사가 서로 다른 단위(총점 상관, IELTS 밴드, CEFR 밴드)로 자기 수치를 내므로 문헌만으로는 우열을 못 가린다. 세 API를 같은 녹음에 돌려야 한다.

## 비교 프로토콜

### 녹음 (약 30분)

1. 앱에서 만든 문단 6개(각 3~6문장)를 고른다.
2. 각 문단을 두 번 읽는다. 자연스럽게 한 번, 오류 심어서 한 번. 심을 오류는 미리 대본에 표시한다:
   - 발음: v→b, f→p, r↔l, th→s/d, 강세 위치 이동, 어말 자음 뒤 모음 삽입, 철자대로 읽기. 문단당 4개.
   - 끊어읽기: 작은 단어(the, of, to) 뒤 멈춤 2곳, 형용사-명사 사이 멈춤 1곳. 문단당 3곳.
3. 대조군: 같은 문단을 원어민 TTS(OpenAI tts 또는 Gemini TTS)로 만든다. 오탐(false positive) 기준선.
4. 16 kHz mono WAV로 저장. `recordings/{para}_{clean|planted|tts}.wav`와 `manifest.json`(문단 텍스트, 심은 오류 목록, 단어 인덱스).

### 실행

| API | 모드 | 필요한 것 |
|---|---|---|
| Azure PA | SDK 파일 입력, Phoneme granularity, prosody on, miscue on (30초 넘으면 continuous) | F0 무료 리소스, 리전 |
| Speechace | `POST /api/scoring/text/v9/json`, `include_fluency=1`, `include_intonation=1` | Pro 트라이얼 (45초 상한: 문단이 길면 문장 단위로 자름) |
| ELSA | `POST /api/v2/score_audio` scripted | 트라이얼 키 (영업 문의 필요, 무료 티어 없음) |

### 측정

| 지표 | 계산 |
|---|---|
| 발음 recall | 심은 오류 중 API가 단어 오류로 표시한 비율 (Azure: ErrorType 또는 AccuracyScore < 60, Speechace: quality_score < 70, ELSA: decision ≠ correct) |
| 발음 precision | API가 표시한 단어 중 실제 심은 오류 비율 (clean 녹음 + TTS에서 표시된 것은 전부 오탐) |
| 끊어읽기 recall / precision | Azure: UnexpectedBreak > 0.75. Speechace·ELSA: 휴지 목록에서 구두점 없는 자리의 휴지 > 300 ms를 오류로 간주해 파생 |
| 임계 민감도 | Azure 단어 점수 40/50/60/70, break 0.6/0.75/0.9에서 precision-recall |
| 지연 | 요청당 왕복 시간 (파일 길이 대비) |
| 비용 | 문단 1개당 청구 금액 |

### 합격 기준

- 발음 recall ≥ 0.7, clean/TTS 오탐 ≤ 문단당 1개.
- 끊어읽기: 심은 3곳 중 2곳 이상 탐지, 오탐 ≤ 1.
- 두 기준을 통과하는 API 중 끊어읽기 신호를 단어 단위로 직접 주는 쪽을 택한다. 전부 통과하면 Azure(스트리밍, 무료 티어). 전부 실패하면 설계를 사후 채점 방식(문단 끝나고 한 번에)으로 바꾼다.

## 하니스

`05-apps/assessor-bench/` (신규 미니 프로젝트, README부터).

| 파일 | 역할 |
|---|---|
| `manifest.json` | 문단, 심은 오류(단어 인덱스, 종류), 녹음 파일명 |
| `bench.py --api azure\|speechace\|elsa` | 녹음 전부를 그 API에 돌리고 `results/{api}.json`에 원본 응답 저장 |
| `judge.py` | 각 API 응답을 공통 `Finding` 형식으로 정규화 (앱의 `judge.ts` 규칙과 동일) |
| `report.py` | manifest와 대조해 지표 표를 markdown으로 출력 → 이 문서에 붙인다 |

키는 `.env`. 소요: 하니스 반나절, 녹음 30분, 실행·정리 1시간.

## 다음 할 일

1. Azure Speech F0 리소스 만들기 (키, 리전).
2. Speechace Pro 트라이얼 신청.
3. ELSA API 트라이얼 문의 (답이 없으면 Azure vs Speechace 둘만 비교).
4. 하니스 구현 → 녹음 → 실행 → 결과를 이 문서에 기록.
