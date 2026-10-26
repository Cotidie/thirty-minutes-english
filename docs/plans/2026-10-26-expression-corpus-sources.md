# 표현 corpus 출처 조사 (2026-10-26)

`expressions` corpus를 채울 공개 출처 조사 기록. 기준: 대화에 쓰는 패턴과 표현을 사람이 직접 정리했고, 로그인 없이 공개돼 있어 긁을 수 있는 곳. 단어·어휘 목록만 있는 곳은 뺐다. 확인은 BrowserOS neo(로그인된 브라우저)와 firecrawl로 실제 게시물을 열어서 했다.

## 한국 출처

| 출처 | 형태 | 주기·규모 | 수집 |
|---|---|---|---|
| **브릿센트 「하루 1분 영어」** [유튜브 커뮤니티](https://www.youtube.com/@BRITCENT/posts), [네이버 블로그](https://m.blog.naver.com/PostList.naver?blogId=britcent) | 텍스트. 한국어 문장 → 영어 표현, 발음기호, 뉘앙스 설명, 예문 4개와 해석. 영국 영어 | 매일 (2026-10-25 게시물 확인) | 쉬움. 틀이 고정 |
| **네이버 「오늘의 영어 회화」** [learn.dict.naver.com/conversation](https://learn.dict.naver.com/conversation#/endic/20261026) | 대화문 하나, 핵심 문장, 표현별 예문과 해석 | 매일. 주소가 `#/endic/YYYYMMDD` | 보통. JS 렌더링이라 브라우저 필요 |
| **소리튠영어(주아쌤)** [@soritune_english](https://www.instagram.com/soritune_english/) | "소리블록" 게시물은 캡션에 패턴이 텍스트로 있음. 예: `It depends on + 명사 → ~에 따라 달라` | 거의 매일. 광고 섞임 | 보통. 유튜브 커뮤니티는 광고와 빈칸 퀴즈 위주라 제외 |
| **티멘트** [유튜브 커뮤니티](https://www.youtube.com/@temmentenglishofficial/posts), [@temmentenglish](https://www.instagram.com/temmentenglish/) | 이미지 카드 6~8장. 글은 제목 한 줄. 인스타그램 캐러셀은 유튜브와 같은 카드, 그 밖에 릴스 450개 | 주 3~4회 (유튜브 1년에 200개) | 완료 (2026-10-26). 아래 수집 기록 |
| **Leo Kim** [@leokim_english](https://www.instagram.com/leokim_english/), **Else** [@else.korea](https://www.instagram.com/else.korea/) | 캡션은 제목뿐, 본문은 이미지. 예: "온라인 회의 필수 표현 40개" | Leo Kim 주 1~2회, Else 매일 | 어려움. OCR 필요 |

브릿센트 게시물 틀 (파서 기준):

```
[하루 1분 영어] "<한국어 문장>" 영어로?
(카톡방·앱 홍보 블록, ‗‗ 로 감쌈)
✨<영어 표현>
/<발음기호>/
<뉘앙스·쓰임 설명 단락>
🎯 예문으로 완벽하게 익혀볼게요!
<영어 예문>
<한국어 해석>     ← 이 두 줄이 4번
‗‗
(수업 홍보)
```

## 영어권 출처

| 출처 | 형태 | 주기·규모 | 수집 |
|---|---|---|---|
| **British Council "What to Say!"** [LearnEnglish Speaking](https://learnenglish.britishcouncil.org/free-resources/speaking) | 기능별 레슨(이해 확인, 대화 이어가기, 반박하기). 레슨마다 useful phrases 목록, 대본, 연습 문제 | A1~B2 | 쉬움. 대본은 접힌 영역이지만 HTML에 있음 |
| **BBC The English We Speak** [목록](https://www.bbc.co.uk/learningenglish/features/the-english-we-speak) | 표현 하나마다 소개, 대화 대본, 예문 3개 | 주 1회. 2026-09 회차까지 확인 | 보통. firecrawl은 본문을 못 가져옴, 브라우저 필요 |
| **PhraseMix** [examples](https://www.phrasemix.com/examples?page=1) | 상황별 문장과 해설 | 여러 쪽 | 쉬움. `?page=N` 순회 |

후순위:

- **VOA English in a Minute** ([목록](https://learningenglish.voanews.com/z/3619)): 2025-03 회차가 마지막. 지난 회차만 남음.
- **PHRASE List** (Martinez & Schmitt 2012, Applied Linguistics 33(3)): 뜻이 단어 합으로 드러나지 않는 빈출 표현 505개. 논문 부록, 예문 없음.

## 제외

| 출처 | 이유 |
|---|---|
| 하루 영어 한개 (maily.so/1wordaday) | 뉴스 어휘 위주 |
| TalkEnglish Speaking Basics | 초급 패턴(`I'm + (verb)` 등)이라 수준이 너무 낮음 |
| Wiktionary English phrasebook | 여행 회화 기초 문장 위주라 수준이 너무 낮음 |
| 명랑소녀다이어리 「오늘의 영어표현」 (blog.naver.com/sry1988) | 단어가 섞이고, 저자가 예문 대부분을 AI로 만들었다고 밝힘 |
| 일일영어회화 유튜브 커뮤니티 | 그림 묘사 글만 있고 1년 전 중단 |
| 매일영어습관 유튜브 커뮤니티 | 이미지만, 글 없음 |
| 구슬쌤 유튜브 커뮤니티 | 책 홍보 글만 있음 |
| Cake 앱, 뉴스레터들 | 앱 안이나 구독 메일로만 전달, 공개 아카이브 없음 |

## 수집 메모

- 형태별 도구: 텍스트 HTML은 HTTP 요청, JS 렌더링(네이버 회화, BBC)은 브라우저, 이미지 카드(티멘트, Leo Kim, Else)는 OCR.
- 인스타그램은 firecrawl이 지원하지 않는다. BrowserOS neo에서는 로그인 상태로 프로필과 캡션을 읽을 수 있었다. 단, 인스타그램 약관은 자동 수집을 금지한다.
- 남은 출처의 약관은 확인하지 않았다.

## 티멘트 수집 기록 (2026-10-26)

corpus 38개 → 1,028개 (티멘트 990개 추가).

| 단계 | 방법 | 결과 |
|---|---|---|
| 유튜브 목록 | 커뮤니티 페이지 HTML의 `ytInitialData`와 `youtubei/v1/browse` continuation. 로그인 불필요 | 게시물 200개 (카드 172, 퀴즈 21, 투표 7), 카드 1,237장 |
| 인스타그램 목록 | 로그인한 BrowserOS neo에서 프로필을 스크롤하며 페이지가 받는 GraphQL 응답을 가로챔. `api/v1/feed`는 HTML만 돌려줌 | 671개 중 643개 (캐러셀 193, 릴스 450) |
| 중복 제거 | 카드 이미지 dHash(256비트) 비교. 거리 8 미만이면 같은 카드 | 캐러셀 171개는 유튜브와 같음, 2개는 일부만, 20개만 인스타 전용 |
| 카드 읽기 | Claude Sonnet 5.5에 게시물별 카드 이미지를 보내 JSON 스키마로 받음. 영어 뜻과 usage note는 Claude가 씀 | 게시물 179개와 퀴즈 21개 → 항목 1,175개 |
| 적재 | `key()`로 같은 표현을 합침(예문은 합쳐 최대 3개). 이미 있던 표현은 그대로 둠 | 997개 중 7개는 기존, 990개 추가 |

넣지 않은 것: 릴스(영상), 단어 목록 게시물과 표현 게시물 속 단어 42개, 추천·공부법·인사 게시물. 넣은 경계 사례: 노래 가사와 영화 대사 6개 게시물, 텍스트 퀴즈 21개.

- 990개 중 403개는 예문이 없다. 카드에 표현과 한국어 뜻만 있는 목록형 게시물이라서다.
- `source`는 게시물 주소 (`https://www.youtube.com/post/<id>`, `https://www.instagram.com/p/<code>/`).
- 추출 JSON과 스크립트, 적재 전 백업은 `backend/data/` 아래 (`corpus-temment-2026-10-26/`, `sessions.db.bak-corpus-2026-10-26`). git에는 없다.
