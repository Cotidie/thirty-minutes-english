# 기사 다단계 작성 (초안, 소리 내어 읽기용 편집, 마무리)

- 상태: 구현됨 (2026-11-05).
- 범위: 세션 생성기가 Claude를 한 번이 아니라 세 번(길이 검사에 걸리면 네 번) 호출해 기사를 쓴다. 저장 형식, DB 스키마, 설정 항목은 바뀌지 않는다. 생성 진행 표시의 단계는 바뀐다.
- 구현 계획: `docs/superpowers/plans/2026-11-05-article-passes.md`. 계획은 편집과 다듬기를 따로 둔 4단계로 쓰였고, 구현 뒤에 두 단계를 하나로 합쳤다 (아래 "사용자가 정한 것"). 단계 구성은 이 문서가 맞다.

## 목적

사용자가 짚은 문제는 두 가지다.

1. 읽고 이해하기 불편할 만큼 긴 문장이 있다.
2. 수치가 지나치게 구체적이다.

이 글은 한 사람씩 돌아가며 끝까지 소리 내어 읽는다. 앱의 소리 내어 읽기는 문단 단위로 돌아간다 (`frontend/src/components/ReadAloud.tsx`, 한 번의 읽기가 문단 하나). 그래서 문장은 한 번 읽고 이해되어야 하고, 문단은 한 사람의 차례로서 분량이 비슷해야 한다. 기사 단계는 읽기를 포함해 10분이다 (`frontend/src/lib/phases.ts`).

### 최근 세션에서 본 근거

`backend/data/sessions.db`의 세션 27, 28, 30 (2026-11-05에 확인).

- 27단어에 수치 세 개: "Frontex, the EU border agency, reported on October 19 that irregular crossings fell by almost one-third in the first nine months of 2026, to just over 91,000."
- 33단어: "Millions of viewers may now treat 3,000 as a historical fact, while historians still work from diplomatic cables, oral testimony and the nine bodies that townspeople found in the plaza the next morning."
- 지나친 수치: "153 theaters", "3.80 out of 5 across 810 reviews", "4.13", "July 6 to September 28, 2022", "At around 1:30 a.m. on December 6".
- 문단 길이가 한 기사 안에서 53단어부터 77단어까지 벌어진다.

### 예전 구조와 원인

- Claude 호출 한 번이 조사, 초안, humanizer, 질문, 번역, 이미지, 그림 장면, 단어를 모두 만들었다 (예전 `generator.py`의 `PROMPT_TEMPLATE`). humanizer도 같은 호출 안에서 "embedded mode로 돌려라"라는 지시로만 실행되었다. 그런데도 위의 긴 문장이 남았다.
- 앱의 글쓰기 규칙 스킬 `backend/plugin/skills/session-writing/SKILL.md`가 수치를 늘렸다. "Specific over general. Names, dates, numbers and mechanisms from your searches. A named source, a year and a number beat ..." 문장 길이 규칙도 "Mostly 12 to 22 words"라서 22단어까지 허용했다.

## 사용자가 정한 것 (2026-11-05 대화)

- 기사 쓰기를 여러 pass로 나눈다. 처음 제안은 1 pass 초안, 2 pass 긴 문장 끊기와 읽기 편하게 고치기와 문단 분량 조절, 3 pass humanizer와 stop-slop이었다.
- 에이전트에게 "한 사람씩 돌아가며 다 읽는다"는 사실을 알린다. 읽기 편한 문장과 분량으로 쓴다.
- 처음에는 편집, 다듬기(humanizer와 stop-slop), 마무리를 따로 둔 4단계를 승인했다. 구현과 실제 생성(약 700초) 뒤에 "4 pass는 너무 많다"며 3단계로 줄였다. 편집과 다듬기를 한 호출로 합치는 안을 골랐다. 다듬기와 마무리를 합치는 안은 고르지 않았다 (번역이 같은 호출에서 나오면 최종 기사의 길이를 고칠 수 없다).
- 1·2·3단계 호출이 실패하면(시간 초과, SDK 오류, structured output 없음) 생성 전체가 실패하고 크레딧은 돌려준다. 편집되지 않은 기사로 대신 진행하지 않는다. 고치기 호출만 예외다 (아래 "길이 검사와 고치기").
- 세션 가격은 200 크레딧 그대로 둔다 (`backend/app/credits.py`). 호출이 늘어도 바꾸지 않는다.
- 2단계 안에서는 읽기 편집 다음에 humanizer와 stop-slop을 적용한다. 2단계 뒤에 코드가 문장 길이와 문단 길이를 검사한다. 두 스킬의 규칙이 읽기 기준과 부딪히면 읽기 기준이 이긴다. `session-writing`의 수치 규칙을 고친다. 이미지가 어느 문단 아래에 갈지는 문단이 확정된 마무리 단계에서 정한다.

## 목표

- 새 세션의 기사에서 모든 문장이 20단어 이하이고, 문단이 4~5개이며, 각 문단이 50~65단어다. 이 기준은 코드로 검사되고, 어긋나면 한 번 고쳐진다.
- 수치는 주장에 필요한 것만 남고, 소리 내어 말하듯 반올림된다.
- 기사는 예전처럼 관점이 분명하고, 한쪽의 가장 강한 근거와 구체적인 반론 하나를 담는다.
- 질문의 evidence와 번역은 최종 본문에서 그대로 복사된다. 마무리 단계는 본문을 바꿀 수 없다.

## 하지 않는 것

- 질문, 번역, 그림 장면, 단어의 규칙 변경. 예전 프롬프트의 해당 문구를 마무리 단계로 옮기기만 한다.
- 새 설정 항목. 세 호출과 고치기 모두 지금의 `CLAUDE_MODEL`과 `CLAUDE_EFFORT`를 쓴다.
- 세션 가격과 과금 규칙(`backend/app/credits.py`, `backend/app/api/sessions.py`의 `_bill_session`) 변경.
- DB 스키마나 저장 형식 변경, 이미 만든 세션의 수정.
- 기사 품질을 자동으로 채점하는 eval 묶음.
- 수치 개수의 코드 검사. 수치 규칙은 프롬프트로만 전한다.

## 실패로 보는 것

- 모든 문장이 8단어 안팎으로 잘려서 전보처럼 읽히는 기사. 짧게 끊되 문장끼리는 이어져야 한다.
- 편집 단계가 사실을 더하는 것. 사실을 빼거나 반올림하는 것만 허용한다.
- 숫자를 줄이다가 관점이나 반론이 사라진 기사.
- 길이 검사 때문에 생성이 실패하는 것. 검사는 고치기를 한 번 요청할 뿐이고, 그래도 어긋나면 기록만 남기고 진행한다.

## 설계

### 흐름

```
topic
  │
  ▼
1. 초안 (Draft) ── 웹 검색, session-writing ──► title, body, sources, 이미지 후보
  │
  ▼
2. 소리 내어 읽기용 편집 (Edit) ── 읽기 규칙, 그다음 humanizer, stop-slop ──► title, body
  │
  ├─ 길이 검사 (코드) ── 어긋남 있음 ──► 고치기 (Repair) 한 번 ──► title, body
  ▼
3. 마무리 (Finish) ── session-writing, check_items ──► questions, translation, figures,
  │                                                    picture, paragraph_picture, vocabulary
  ▼
코드가 Draft를 조립: 2단계(또는 고치기)의 title과 body + 1단계의 sources + 3단계의 나머지
```

각 단계는 별도의 Claude 호출이다. 앞 단계의 출력이 다음 호출의 프롬프트에 들어간다. 단계 사이에 대화 맥락은 이어지지 않는다.

### 단계별 구성

| 단계 | 도구 | 스킬 | 입력 | 출력 schema |
|---|---|---|---|---|
| 1. 초안 | `Read`, `WEB_TOOLS`, firecrawl MCP | `english-session:session-writing` | topic | title, body, sources (0~5), images (0~4) |
| 2. 편집 | `Read` (스킬의 references 파일을 읽는 데 필요) | `english-session:humanizer`, `english-session:stop-slop` | title, body | title, body |
| 고치기 | 없음 | 없음 | title, body, 어긋난 항목 목록 | title, body |
| 3. 마무리 | `Read` | `english-session:session-writing` | topic, title, body, 이미지 후보 | topic, questions, translation, figures, picture, paragraph_picture, vocabulary |

`check_items` MCP 서버(이미 가르친 단어 확인)는 예전처럼 제외 단어가 있을 때만 붙고, 3단계에만 붙는다. 1단계 이미지 후보의 항목은 `image_url`, `page_url`, `credit`, `shows`(그 이미지가 무엇을 보여주는지 한 문장)다. 문단 위치(`after`)는 없다.

### 독자 상황 문구

1~3단계와 고치기의 프롬프트 모두 같은 독자 상황을 앞에 둔다. 한 상수(`prompts.READER`)에 두고 재사용한다. 문구의 뜻은 다음과 같다.

> Who reads this: Korean graduate students at about B2 level. They read the article aloud in turns, one paragraph each, until the whole article has been read, then discuss it. The article part of the session lasts ten minutes, reading included. Each sentence must make sense on one reading at speaking pace, and each paragraph is one person's turn, so paragraphs stay close in length.

### 읽기 기준 (코드 상수)

| 상수 | 값 | 쓰는 곳 |
|---|---|---|
| 문장 최대 단어 수 | 20 | 1·2단계와 고치기의 프롬프트, 길이 검사 |
| 문단 개수 | 4~5 | 같음 |
| 문단 단어 수 | 50~65 | 같음 |
| 문단당 수치 | 2개까지, 연도만 있는 것은 세지 않음 | 1·2단계 프롬프트만 |

기준 값은 상수 한 곳(`backend/app/generation/readability.py`)에만 두고 프롬프트에 끼워 넣는다. 단어 수는 공백으로 나눈 토큰 수다. 하이픈으로 이은 단어는 하나로 센다. 문장, 문단, 기사 전체 분량(200~325단어)은 이 값에서 따라 나온다. 예전 프롬프트의 "250 to 350 words"와 "3 to 5 paragraphs"는 이 기준으로 바뀌었다.

### 1단계: 초안

예전 `PROMPT_TEMPLATE`의 "1. article" 부분 가운데 조사와 초안에 관한 규칙을 그대로 가져온다. 검색은 3번까지, `firecrawl_search`를 먼저 쓰고 실패할 때만 `WebSearch`를 쓴다. 최근의 사건이나 논쟁을 관점으로 삼는다. 확인하지 않은 구체적 사실은 지어내지 않는다. sources에는 실제로 참고한 페이지만 넣는다. 이미지는 `firecrawl_scrape`의 images 형식으로 참고한 페이지에서 찾고, 로고, 광고, 아이콘, 필자 사진, 추적 픽셀은 제외한다. 2개보다 적게 내기 전에 참고한 모든 페이지를 살핀다. 후보는 4개까지 낸다.

달라지는 점은 두 가지다. 프롬프트가 독자 상황과 읽기 기준을 알리고, 초안이 그 기준을 목표로 쓰이게 한다 (초안이 기준을 완전히 지킬 필요는 없다). 그리고 humanizer, 질문, 번역, 이미지 위치, 그림 장면, 단어에 관한 지시는 1단계에서 빠진다.

### 2단계: 소리 내어 읽기용 편집

입력은 1단계의 title과 body다. 한 호출 안에서 두 걸음으로 고친다.

첫 걸음은 읽기 편집이다. 프롬프트가 지시하는 내용은 다음과 같다.

1. 문장: 20단어 이하. 한 문장에 한 생각. 끼워 넣은 구(동격, 괄호, 쉼표 사이의 절)는 한 문장에 하나까지. 주어와 동사를 가까이 둔다. 긴 문장은 생각이 나뉘는 곳에서 끊고, 끊은 문장끼리는 이어지게 쓴다.
2. 수치: 관점에 필요한 수치만 남긴다. 문단당 2개까지이며, 연도만 있는 것은 세지 않는다. 소리 내어 말하듯 반올림한다 ("about 150 theaters", "nearly a third", "in 2022"). 정확한 값 자체가 요점일 때만 정확한 수치를 둔다. 날짜는 그날이 이야기에 중요할 때만 일까지 쓰고, 아니면 연도나 월과 연도만 쓴다. 시각은 중요할 때만 남긴다. 반올림한 값도 참이어야 한다 (153은 "about 150"이지 "nearly 200"이 아니다).
3. 이름: 주장을 따라가는 데 필요한 이름만 남긴다. 한 번 나오고 빠져도 주장이 서는 사람의 이름은 역할로 바꾼다 ("a historian").
4. 문단: 4~5개, 각 50~65단어. 한 문단은 주장의 한 걸음이고, 한 사람이 한 차례에 읽을 분량이다. 분량을 맞추려고 문장을 옮기거나 줄인다.
5. 사실: 빼기, 반올림, 순서 바꾸기만 허용한다. 사실, 이름, 수치, 날짜, 인용, 출처를 새로 더하지 않는다.
6. 유지할 것: 앞부분에서 밝히는 관점, 한쪽의 가장 강한 근거, 구체적인 반론 하나, 결론을 내리지 않는 끝.
7. 낱말: B2 독자가 아는 흔한 낱말을 고른다.

둘째 걸음은 다듬기다. 편집한 title과 body에 `english-session:humanizer`와 `english-session:stop-slop`을 차례로 적용하고, 두 스킬의 embedded mode처럼 최종 텍스트만 돌려준다. 편집이 남긴 사실은 모두 두고, 편집이 나눈 문단은 그대로 둔다. 두 스킬과 부딪히는 규칙은 다음과 같이 정리하고, 부딪히면 첫 걸음의 규칙이 이긴다.

| 스킬의 규칙 | 이 기사에서 |
|---|---|
| stop-slop "Be specific" | 행위자와 대상을 밝힌다는 뜻이다. 수치, 이름, 날짜를 더하지 않는다 |
| stop-slop "'You' beats 'People'", "Put the reader in the room" | 적용하지 않는다. 기사는 3인칭으로 쓴다 |
| stop-slop "Remove ... all adverbs" | 군더더기 부사만 뺀다 |
| humanizer "Vary sentence length" | 20단어 안에서 길이를 섞는다 |
| humanizer의 목소리 | 사실을 전하는 글이므로 중립적이고 평이하게 쓴다 (humanizer "Voice"의 factual text 규칙) |

### 길이 검사와 고치기

2단계가 끝나면 코드가 body를 검사해 어긋난 항목 목록을 만든다.

- 20단어를 넘는 문장마다 한 항목. 그 문장과 단어 수를 적는다.
- 50~65단어 범위를 벗어난 문단마다 한 항목. 문단 번호(1부터)와 단어 수를 적는다.
- 문단 개수가 4~5가 아니면 한 항목.

문장 나누기는 `.`, `!`, `?` 뒤에서 하되 다음을 지킨다. 닫는 따옴표나 괄호가 붙은 끝(`."`, `.)`)도 문장 끝이다. `U.S.`, `U.K.`, `a.m.`, `p.m.`, `Dr.`, `Mr.`, `Mrs.`, `Ms.`, `St.`, `e.g.`, `i.e.`, `vs.` 같은 약어 뒤와 소수점(`3.80`)에서는 나누지 않는다.

목록이 비어 있으면 3단계로 간다. 목록이 있으면 고치기 호출을 한 번 한다. 고치기는 도구도 스킬도 없는 별도 호출이다. 프롬프트는 독자 상황, 2단계 결과, 어긋난 항목 목록을 주고, 그 항목만 고치게 한다. 긴 문장은 나누고, 문단은 문장을 옮기거나 줄여서 범위에 맞추고, 문단 개수가 틀리면 문단을 나누거나 합친다. 나머지 문장은 그대로 둔다. 사실을 더하지 않고, em dash를 쓰지 않고, 제목과 본문 전체를 돌려준다.

고친 결과는 세 조건을 모두 지킬 때만 쓴다 (`readability.repair_holds`). 어긋난 항목 수가 2단계 결과보다 많지 않다. 문단 개수가 범위에서 더 멀어지지 않는다 (문단을 합쳐 한 사람의 차례가 사라지면 안 된다). 단어 수가 2단계 결과의 85% 이상이다 (내용을 잘라내면 안 된다). 하나라도 어기면 2단계 결과를 쓴다. 그래도 남은 항목은 경고로 기록하고 생성은 계속한다. 고치기 호출 자체가 실패하면(시간 초과, SDK 오류, structured output 없음) 2단계 결과로 계속한다. 이때도 `Cancelled`는 삼키지 않는다.

### 3단계: 마무리

입력은 topic, 최종 title과 body, 1단계의 이미지 후보다. 예전 `PROMPT_TEMPLATE`에서 다음 부분을 옮긴다: 질문 3개와 evidence, 번역, figures, picture, paragraph_picture, "2. vocabulary" 전체, 그리고 `CHECK_ITEMS_RULE`. 바뀌는 점은 다음과 같다.

- 프롬프트가 "기사는 확정되었으니 고치지 말라"고 한다. 출력 schema에 title과 body가 없으므로 본문은 구조적으로 바뀌지 않는다.
- figures는 이미지 후보에서 고른다. cover는 `after` 0, 두 번째는 해당 문단 번호(1부터)이고, caption은 그 이미지와 기사(또는 문단)의 관계를 한 문장으로 쓴다. 후보에 없는 `image_url`은 코드가 버린다.
- 문단 번호는 body의 빈 줄로 나눈 순서로 센다. 프롬프트에 body를 번호 없이 그대로 넣어 evidence와 번역에 번호가 섞이지 않게 한다.

### Draft 조립

코드가 `Draft`를 만든다 (`passes.assemble`). `topic`과 `vocabulary`는 3단계에서, `article.title`과 `article.body`는 2단계(또는 고치기)에서, `article.sources`는 1단계에서, `article.questions`, `translation`, `figures`, `picture`, `paragraph_picture`는 3단계에서 가져온다. 검증 실패는 `GenerationError`가 된다. `Draft`, `ArticleDraft`와 그 뒤의 저장, 이미지 내려받기, 그림 그리기(`backend/app/generation/jobs.py`)는 바뀌지 않는다.

### 진행 표시

`Stage`(`backend/app/generation/progress.py`)의 순서와 화면 문구다.

| 값 | 화면 문구 | 언제 |
|---|---|---|
| `starting` | Reading the brief | 예전과 같음 |
| `skills` | Loading writing skills | 1단계에서 스킬을 불러올 때 |
| `searching` | Searching the web | 1단계 검색 |
| `drafting` (예전의 `writing`을 대신함) | Writing a draft | 1단계의 생각과 글쓰기 |
| `editing` | Editing for reading aloud | 2단계와 고치기 |
| `finishing` | Writing questions, translation, and words | 3단계 |
| `finalizing` | Checking the structure | 3단계의 StructuredOutput |
| `illustrating` | Drawing a picture for each word | 예전과 같음 |

- 생성기는 호출을 시작할 때마다 하나의 `StreamTracker`에 지금 단계를 알린다(`StreamTracker.begin`). 1단계 안에서는 메시지로 `skills`, `searching`, `drafting`을 추정한다. 2·3단계와 고치기에서는 모든 메시지가 그 단계에 머물고, 스킬 불러오기와 도구 호출은 activity 문구만 바꾼다. 앞 단계들의 StructuredOutput은 단계를 바꾸지 않고, 3단계의 StructuredOutput만 `finalizing`으로 간다. 고치기 중에는 activity를 "Fixing sentence and paragraph lengths"로 둔다.
- 토큰 수는 모든 호출에 걸쳐 누적된다. `TokenMeter`는 메시지 id로 세므로 tracker 하나를 계속 쓰면 된다.
- 취소는 progress 콜백(`Job.apply`)이 `Cancelled`를 던져서 일어난다. 단계가 바뀔 때마다 콜백이 불리므로 단계 사이에서도 멈춘다.
- 프런트엔드 `frontend/src/lib/progress.ts`의 `Stage` 타입, `FLOORS`, `NEXT`, `stageLabel`을 같은 값과 순서로 맞춘다. 막대가 뒤로 가지 않는 규칙(`percentFor`)은 유지한다.
- `stage_times` 테이블의 예전 `writing` 행은 남겨 둔다. 새 단계는 기록이 쌓이기 전까지 `DEFAULT_STAGE_SECONDS`의 값을 쓴다.

### 기록

- 각 호출 앞에 "session pass: <단계>" 로그를 남기고, 이어서 `Claude.run`의 "%s run: %.1fs, %d turns, $%.3f" 로그가 나온다.
- 길이 검사 결과를 한 줄로 남긴다: 2단계 뒤 어긋난 항목 수, 고치기 뒤 항목 수, 어느 결과를 썼는지, 남은 항목.

### `session-writing` 스킬 수정

이 스킬은 1단계와 3단계가 읽는다.

- 첫 문단의 독자 설명에 "문단 하나씩 돌아가며 끝까지 소리 내어 읽는다"를 더한다.
- "Specific over general" 항목을 "Concrete over vague"로 바꾼다. 행위자, 장소, 작동 방식을 밝히고, 수치는 주장에 필요할 때만 소리 내어 말하듯 반올림해서 쓴다. 확인하지 않은 수치를 지어내지 않는다는 규칙은 남긴다.
- "Sentence length" 항목은 프롬프트의 읽기 기준이 이긴다고 적고, 22단어 같은 별도 숫자를 두지 않는다.
- "Final pass before the structured output"은 편집 단계가 맡게 된 항목을 빼고 정리한다. 수치, 이름, 날짜가 검색한 페이지에서 왔는지 확인하는 항목은 남긴다.

### stop-slop 가져오기

`/home/humanoid/repositories/study-companion/app/plugin/skills/stop-slop` 폴더(SKILL.md, LICENSE, SOURCE.md, references/)를 `backend/plugin/skills/stop-slop`으로 수정 없이 복사한다. 출처는 github.com/hardikpandya/stop-slop, MIT, Copyright (c) 2025 Hardik Pandya이고 SOURCE.md에 적혀 있다. Docker 이미지는 `backend/plugin`을 통째로 복사하므로(`backend/Dockerfile`) 따로 할 일이 없다. 스킬 이름은 `english-session:stop-slop`이다.

## 설계자의 판단

사용자가 정하지 않고 설계자가 정한 것이다. 사용자가 검토할 수 있도록 모았다.

| 항목 | 결정 | 이유 |
|---|---|---|
| 읽기 기준 값 | 문장 20단어, 문단 4~5개, 문단 50~65단어, 문단당 수치 2개 | 예전 기사의 긴 문장(27~33단어)과 문단 편차(53~77단어)를 줄이는 선. 실제 결과를 보고 조정한다 |
| 2단계 안의 순서 | 읽기 편집을 먼저, 두 스킬을 그다음에. 부딪히면 읽기 규칙이 이긴다 | 사용자가 처음 정한 순서(가독성 편집 다음 humanizer)를 한 호출 안에서 지킨다 |
| 고치기 방식 | 2단계를 통째로 다시 돌리지 않고, 어긋난 항목만 고치는 가벼운 호출 | 다시 두 스킬을 돌리면 문장이 또 바뀐다. 고칠 곳만 고치는 쪽이 싸고 안전하다 |
| 고치기 호출의 도구 | 도구와 스킬이 없는 별도 호출 | 고칠 곳만 고치는 일에는 스킬이 필요 없고, 기준 값은 코드 상수에서 프롬프트로 온다 |
| 고치기 호출이 실패할 때 | 2단계 결과로 계속한다 | 길이 검사 때문에 생성이 실패하면 안 된다 ("실패로 보는 것") |
| 고친 결과를 쓰는 조건 | 항목 수가 많지 않고, 문단 개수가 범위에서 멀어지지 않고, 단어 수가 85% 이상 | 최종 리뷰에서 항목 수만 비교하면 문단을 합치거나 일부만 돌려준 결과가 뽑힐 수 있음이 드러났다 |
| 모델과 effort | 모든 호출이 `CLAUDE_MODEL`, `CLAUDE_EFFORT` | 새 설정 없이 시작한다. 전체 시간이 너무 길면 편집 단계의 effort를 낮추는 것을 따로 검토한다 |
| 호출마다의 시간 제한 | `TIMEOUT_S`(600초)를 호출마다 적용 | 1단계가 예전 한 번의 호출보다 일이 적으므로 넉넉하다 |
| 3단계의 이미지 확인 | 후보에 없는 `image_url`은 버린다 | 3단계는 웹 도구가 없어서 새 주소를 확인할 수 없다 |
| 진행 단계 이름과 문구 | 위 표 | 예전 문구 "Writing the article, expressions, and words"는 표현이 corpus에서 온 뒤로 이미 틀렸다 |
| `DEFAULT_STAGE_SECONDS`의 `editing` | 100초 | 4단계 때의 편집(40초)과 다듬기(60초)를 더한 값. 기록이 쌓이면 중앙값이 대신한다 |

## 검증

- 단위 테스트: 세 호출이 정해진 순서와 도구, 스킬로 불리는지. `check_items`가 3단계에만 붙는지. 2단계와 고치기 프롬프트에 독자 상황과 상수 값이 들어가는지. 2단계 프롬프트가 읽기 규칙 다음에 두 스킬을 부르고 충돌 규칙 정리를 담는지. 최종 `Draft`의 body가 2단계(또는 고치기) 출력과 같은지. 문장 나누기(약어, 소수점, 닫는 따옴표)와 길이 검사. 고치기가 어긋남이 있을 때만 한 번, 도구 없이 불리는지, 어긋남이 남아도 예외 없이 진행하는지, `repair_holds`를 지키는 쪽이 쓰이는지. 후보에 없는 이미지가 버려지는지. 진행 단계가 차례대로 나오고 토큰이 누적되는지. stop-slop 폴더에 LICENSE와 SOURCE.md가 있는지. 프런트엔드 `progress.ts`의 단계.
- 실제 생성: merge 전에 브랜치 코드로 실제 주제 하나를 생성해서 기사 본문, 단계별 시간과 비용 로그, 길이 검사 기록을 사용자에게 보여준다. 운영 백엔드를 다시 띄워야 한다면 먼저 돌고 있는 생성이 없는지 확인한다.
