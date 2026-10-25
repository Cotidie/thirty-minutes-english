# 표현 corpus 출처 조사 (2026-10-26)

`expressions` corpus를 채울 공개 출처 조사 기록. 기준: 대화에 쓰는 패턴과 표현을 사람이 직접 정리했고, 로그인 없이 공개돼 있어 긁을 수 있는 곳. 단어·어휘 목록만 있는 곳은 뺐다. 확인은 BrowserOS neo(로그인된 브라우저)와 firecrawl로 실제 게시물을 열어서 했다.

## 한국 출처

| 출처 | 형태 | 주기·규모 | 수집 |
|---|---|---|---|
| **브릿센트 「하루 1분 영어」** [유튜브 커뮤니티](https://www.youtube.com/@BRITCENT/posts), [네이버 블로그](https://m.blog.naver.com/PostList.naver?blogId=britcent) | 텍스트. 한국어 문장 → 영어 표현, 발음기호, 뉘앙스 설명, 예문 4개와 해석. 영국 영어 | 매일 (2026-10-25 게시물 확인) | 쉬움. 틀이 고정 |
| **네이버 「오늘의 영어 회화」** [learn.dict.naver.com/conversation](https://learn.dict.naver.com/conversation#/endic/20261026) | 대화문 하나, 핵심 문장, 표현별 예문과 해석 | 매일. 주소가 `#/endic/YYYYMMDD` | 보통. JS 렌더링이라 브라우저 필요 |
| **소리튠영어(주아쌤)** [@soritune_english](https://www.instagram.com/soritune_english/) | "소리블록" 게시물은 캡션에 패턴이 텍스트로 있음. 예: `It depends on + 명사 → ~에 따라 달라` | 거의 매일. 광고 섞임 | 보통. 유튜브 커뮤니티는 광고와 빈칸 퀴즈 위주라 제외 |
| **티멘트** [유튜브 커뮤니티](https://www.youtube.com/@temmentenglishofficial/posts) | 이미지 카드 6~8장. 글은 제목 한 줄 | 자주 | 어려움. OCR 필요 |
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
| **TalkEnglish** [Speaking Basics](https://www.talkenglish.com/speaking/listbasics.aspx) | 레슨 하나가 패턴 하나. 예: `I'm trying + (verb)`, `I was about to + (verb)`. 예문과 음성 | 레슨 90개, 음성 900개 이상 | 쉬움. 정적 HTML |
| **British Council "What to Say!"** [LearnEnglish Speaking](https://learnenglish.britishcouncil.org/free-resources/speaking) | 기능별 레슨(이해 확인, 대화 이어가기, 반박하기). 레슨마다 useful phrases 목록, 대본, 연습 문제 | A1~B2 | 쉬움. 대본은 접힌 영역이지만 HTML에 있음 |
| **BBC The English We Speak** [목록](https://www.bbc.co.uk/learningenglish/features/the-english-we-speak) | 표현 하나마다 소개, 대화 대본, 예문 3개 | 주 1회. 2026-09 회차까지 확인 | 보통. firecrawl은 본문을 못 가져옴, 브라우저 필요 |
| **Wiktionary** [English phrasebook](https://en.wiktionary.org/wiki/Category:English_phrasebook) + 관용구 범주 | 표현, 뜻, 예문 | phrasebook 465개 | 가장 쉬움. [kaikki.org](https://kaikki.org/dictionary/rawdata.html) JSON 덤프를 받으면 됨. CC BY-SA |
| **PhraseMix** [examples](https://www.phrasemix.com/examples?page=1) | 상황별 문장과 해설 | 여러 쪽 | 쉬움. `?page=N` 순회 |

후순위:

- **VOA English in a Minute** ([목록](https://learningenglish.voanews.com/z/3619)): 2025-03 회차가 마지막. 지난 회차만 남음.
- **PHRASE List** (Martinez & Schmitt 2012, Applied Linguistics 33(3)): 뜻이 단어 합으로 드러나지 않는 빈출 표현 505개. 논문 부록, 예문 없음.

## 제외

| 출처 | 이유 |
|---|---|
| 하루 영어 한개 (maily.so/1wordaday) | 뉴스 어휘 위주 |
| 명랑소녀다이어리 「오늘의 영어표현」 (blog.naver.com/sry1988) | 단어가 섞이고, 저자가 예문 대부분을 AI로 만들었다고 밝힘 |
| 일일영어회화 유튜브 커뮤니티 | 그림 묘사 글만 있고 1년 전 중단 |
| 매일영어습관 유튜브 커뮤니티 | 이미지만, 글 없음 |
| 구슬쌤 유튜브 커뮤니티 | 책 홍보 글만 있음 |
| Cake 앱, 뉴스레터들 | 앱 안이나 구독 메일로만 전달, 공개 아카이브 없음 |

## 수집 메모

- 형태별 도구: 텍스트 HTML은 HTTP 요청, JS 렌더링(네이버 회화, BBC)은 브라우저, 이미지 카드(티멘트, Leo Kim, Else)는 OCR.
- 인스타그램은 firecrawl이 지원하지 않는다. BrowserOS neo에서는 로그인 상태로 프로필과 캡션을 읽을 수 있었다. 단, 인스타그램 약관은 자동 수집을 금지한다.
- 라이선스가 명확한 곳은 Wiktionary(CC BY-SA)뿐. 나머지 약관은 확인하지 않았다.
