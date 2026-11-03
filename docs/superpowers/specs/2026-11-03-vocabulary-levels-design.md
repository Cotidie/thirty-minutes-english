# Vocabulary 난이도 설정

- 상태: 구현됨 (2026-11-03).
- 범위: 새 세션의 단어 수준을 관리자 설정으로 고른다. 스키마 변경 없음.
- 구현 계획: `docs/superpowers/plans/2026-11-03-vocabulary-levels.md`

## 목적

새 세션의 단어 8개는 생성 프롬프트에 고정된 "B2 to C1+" 수준으로 뽑힌다 (`backend/app/generation/generator.py`의 `PROMPT_TEMPLATE`). 사용자는 이 수준이 적절하지만, 함께 공부하는 친구는 어렵다고 한다. 두 사람은 같은 세션을 함께 쓴다. 관리자가 설정 화면에서 B1, B2, C1, C2 중 포함할 수준을 골라 새 세션의 단어 수준을 정할 수 있게 한다.

## 사용자가 정한 것

- 설정 값으로 둔다.
- B1부터 C2까지 중에서 포함할 수준을 고른다.
- CEFR의 공식 plus 수준도 고를 수 있다 (구현 중에 더함). CEFR Companion Volume(2020)의 plus 수준은 A2+, B1+, B2+이고, 이 범위에 드는 것은 B1+와 B2+다. C1+는 공식 수준이 아니다.

## 설계자의 판단 (계획 승인으로 함께 승인됨)

| 항목 | 결정 |
|---|---|
| 누가, 어디서 | 관리자 설정 화면 (`/api/settings`, 관리자 전용). 모든 계정의 새 세션에 적용된다 |
| 적용 시점 | 저장하면 서비스가 다시 만들어져 다음 세션부터 적용된다. 이미 돌고 있는 생성은 시작할 때 잡은 생성기를 쓰므로 그대로다 (`api/sessions.py`의 `jobs.start`). 저장된 세션의 단어는 바뀌지 않는다 |
| 고르는 방식 | 체크박스 6개. 비어 있지 않은 어떤 조합이든 된다 (B1과 C1처럼 떨어진 조합 포함). 켜진 것이 하나뿐이면 그 칸은 끌 수 없다 |
| 기본값 | `B2,B2+,C1`. 이전 프롬프트의 "B2 to C1+"와 같은 범위이고, 프롬프트에는 "B2 to C1"로 적힌다 |
| plus 수준의 설명 | `Strong intermediate`, `Strong upper intermediate`. 공식 명칭이 아니라 설정 화면용 설명이다 |
| 섞는 방식 | 둘 이상이면 고른 수준에 단어를 고르게 나누라고 지시한다 (8개에 둘이면 4개씩) |
| 화면 위치 | `Claude generation` 탭의 마지막 줄. Claude가 쓰는 내용을 정하는 값이다 |

## 하지 않는 것

- 기사, 질문, 그림 설명의 난이도.
- 코치 프롬프트의 학습자 수준 문구 ("B2 to C1 level", `agents/example-coach`, `agents/summary-coach`).
- 단어 카드에 수준을 표시하거나 단어별 수준을 검증하는 일. 수준은 Claude에게 주는 지시이고 보장이 아니다.
- 계정별 수준. 설정은 앱 전체에 하나다.

## 설계

### 값

- 저장 형식은 쉼표로 이은 수준 목록이다 (`B2,B2+,C1`). 순서는 늘 `B1, B1+, B2, B2+, C1, C2` 순이다.
- 저장할 때 검사한다: 여섯 수준 중 하나 이상이 위 순서대로, 겹침과 공백 없이 쉼표로 이어져 있어야 한다. 아니면 400과 `VOCABULARY_LEVELS must name one or more of B1, B1+, B2, B2+, C1, C2, in that order, joined by commas`. 하나라도 틀리면 아무것도 저장하지 않는다 (기존 규칙).
- 읽을 때는 너그럽다: 공백과 소문자를 받아 주고, 모르는 조각은 버리고, 남는 것이 없으면 기본값이다. 환경변수로 들어온 값은 저장 검사를 거치지 않기 때문이다.
- 설정 화면에는 날것이 아니라 앱이 읽은 값을 보낸다. `.env`에 `b2, c1`이 있으면 화면은 `B2,C1`을 받아, 생성기가 쓰는 수준과 같은 칸이 켜진다.

### 수준 이름

| 수준 | 설명 (설정 화면) |
|---|---|
| B1 | Intermediate |
| B1+ | Strong intermediate |
| B2 | Upper intermediate |
| B2+ | Strong upper intermediate |
| C1 | Advanced |
| C2 | Proficient |

### 프롬프트

하나면 `2. vocabulary: 8 words at CEFR level B1 connected to the topic.`, 둘 이상이면 `8 words at CEFR levels B2, B2+ and C1 connected to the topic. Spread them about evenly across these levels.`이다. 수준은 범위("B2 to C1")로 줄이지 않고 하나하나 적는다. 범위로 적으면 plus 수준이 그 안에 묻혀 Claude가 건너뛸 수 있기 때문이다 (최종 리뷰 지적).

### 설정 화면

설정 항목에 "여러 개 고름" 성질(`many`)을 더한다. 이 성질이 있으면 화면은 선택지를 체크박스로 그리고, 값은 위 저장 형식의 문자열 그대로 주고받는다. 저장, 되돌리기, 바뀐 개수 세기는 지금처럼 문자열 비교로 한다.

## 남는 한계

- Claude가 수준을 잘못 판단해도 막는 장치가 없다.
- 두 사람이 다른 수준을 원하면 한 값으로 타협해야 한다.
