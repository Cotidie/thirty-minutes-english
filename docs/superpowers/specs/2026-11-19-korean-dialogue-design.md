# 한국어로 해 보기: 대화문

- 상태: 설계 (2026-11-19).
- 범위: Expressions 탭 카드의 "한국어로 해 보기"에 두 사람 대화문(A, B 두 줄)을 더한다. 지금의 한 문장 예문은 그대로 두고, 카드마다 토글로 둘 중 하나를 본다. 대화문은 corpus에 저장하고, repo에 커밋하는 Python 모듈이 Claude로 채운다. DB 스키마가 v17이 된다.

## 목적

지금 카드에는 한국어 문장 하나가 있고, 두 사람이 각자 그 문장을 영어로 말한 뒤 누르면 영어 모범 답안이 나온다 (`expressions.korean_example`, 932개 모두 채워짐). 두 사람이 같이 하는 연습이니, A와 B가 한 줄씩 주고받는 대화문으로도 연습하게 한다. 둘 다 표현을 억지로 넣으면 대화가 어색해지므로, 표현은 두 줄 중 적어도 한 줄에만 들어가면 된다.

## 사용자가 정한 것 (2026-11-19 대화)

1. 대화문은 A와 B 두 줄이다. 둘 중 한 줄은 표현을 안 써도 된다.
2. 기존 한 문장 예문은 남긴다. 둘 중 무엇을 볼지 고를 수 있다.
3. 고르는 곳은 ⚙ 설정이 아니라 카드의 "한국어로 해 보기" 옆 토글이다.
4. 카드를 누르면 두 줄이 한꺼번에 영어 모범 답안으로 바뀐다. 줄마다 따로 뒤집지 않는다.
5. 대화문 생성은 repo에 커밋하는 Python 모듈로 한다. `docker compose exec backend ...`로 돌리고, 대화문이 없는 표현만 채운다.

## 설계자가 정한 것 (사용자가 고칠 수 있음)

1. 토글은 카드마다 따로 있다. 한 사람이 바꾸면 세션의 모두에게 같이 바뀐다 (presence 공유, `useSharedView`). 저장하지 않으며 새로고침하면 기본값으로 돌아간다. 이유: 카드 뒤집기와 같은 성격의 상태이고, CLAUDE.md 규칙상 presence가 "what they have turned over"를 맡는다.
2. 기본값은 대화다. 대화문이 없는 표현은 한 문장만 보이고 토글이 없다. 한 문장 예문이 없고 대화문만 있으면 대화만 보이고 토글이 없다. 둘 다 없으면 지금처럼 이 영역 전체가 없다.
3. 토글 문구는 주변 문구("한국어로 해 보기", "영어로 어떻게 말할까요?")에 맞춰 한국어로 "한 문장"과 "대화"다.
4. 뒤집기 상태는 모드마다 따로 둔다. 한 문장은 지금 키 `example:{id}`를 그대로 쓰고, 대화는 새 키 `dialogue:{id}`를 쓴다. 모드를 바꿔도 다른 모드의 뒤집기 상태는 그대로다. 이유: 두 키를 한 번에 되돌리는 처리 없이 각자 기본값(한국어 면)에서 시작한다.
5. 영어 답안에서는 표현을 가장 많이 담은 줄만 기존 `Marked`로 칠하고, 다른 줄은 그냥 글자로 둔다 (`strongestMatches`, `frontend/src/lib/phraseMatch.ts`). 어느 줄에 표현이 있는지는 저장하지 않는다. `Marked`는 표현 전체가 없으면 표현의 두 단어 조각("about it", "on the")으로도 칠하므로, 표현을 안 쓴 줄이 잘못 칠해지지 않게 두 줄을 견준다. `~`가 든 표현은 전체가 맞는 일이 없어 "전체가 맞는 줄만"으로는 고를 수 없다. 둘이 똑같이 담으면 둘 다 칠한다.
6. 생성 모듈은 앱 서버 이벤트를 내지 않는다. 다른 프로세스에서 돌아 서버의 `Changes`에 닿지 않고, 한 문장 예문을 채울 때도 그랬다. 열려 있던 세션은 새로고침하면 대화문을 본다.

## 목표가 아닌 것

- ⚙ 설정의 전역 스위치. 사용자가 카드 토글로 바꿨다.
- 토글 상태 저장(계정별, 세션별 모두).
- 세 줄 이상의 대화, 줄마다 뒤집기, A/B 역할을 사람에게 배정하기.
- 앱 안에서 대화문 만들기, 다시 만들기, 고치기. 화면에는 읽기만 있다.
- 새로 가져온 표현의 한 문장 예문 채우기. 예전 스크립트는 없어졌지만 이번 범위 밖이다.
- 영어 답안에 표현이 실제로 들어갔는지 코드로 검사하기. 프롬프트로 요구하고, 미리보기로 사람이 확인한다.
- Database 페이지(관리자 corpus 목록)에 대화문 보여 주기.

## 접근 방법

| 방법 | 장단점 | 결정 |
|---|---|---|
| repo에 커밋하는 Python 모듈, `python -m`으로 실행 | git에 남아 다시 잃지 않는다. 표현을 새로 가져온 뒤 다시 돌리면 빈 것만 채운다. 가짜 Runner로 테스트된다 | 채택 |
| git 밖 일회용 스크립트 (예전 한 문장 예문 방식) | 가장 빠르지만, 예전 스크립트처럼 사라질 수 있고 새 표현은 비어 남는다 | 기각 |
| 앱이 카드를 처음 볼 때 job으로 생성 | 관리할 것은 없지만, 한 번 돌리면 끝날 일에 job, 크레딧, 이벤트 연결이 붙고 처음 볼 때 기다린다 | 기각 |

저장은 열 하나를 더하는 방법만 검토했다. 기존 `korean_example` JSON에 대화를 끼워 넣으면 이미 채워진 932개의 모양이 바뀌고, 앞 두 결정(따로 고르기, 따로 비어 있기)도 표현하기 어렵다.

## 데이터

### 스키마 v17

`backend/app/db/schema.py`:

```sql
-- Added in v17: a two-line dialogue, A then B, as a JSON array [{"korean", "english"}, {"korean", "english"}]; NULL until the corpus has one.
ALTER TABLE expressions ADD COLUMN korean_dialogue TEXT;
```

- `VERSION = 17`. 새 상수(예: `KOREAN_DIALOGUES`)를 `SCHEMA` 끝에 붙여 새 파일에도 열이 생기게 하고, `upgrade`에 `if version < 17:` 단계를 더한다. v6 `KOREAN_EXAMPLES`와 같은 모양이다.
- 백업은 `Database.__init__`이 업그레이드 전에 이미 남긴다 (`sessions.db.bak-v16-<날짜>`).
- 기존 행은 모두 NULL로 시작한다.

### 모델

`backend/app/models.py`:

```python
class KoreanLine(BaseModel):
    """One speaker's line: Korean to say in English, then `english` as the model answer."""

    korean: str
    english: str


class Expression(BaseModel):
    ...
    """None until the corpus has one. A's line, then B's; at least one says the expression."""
    korean_dialogue: list[KoreanLine] | None = None
```

`KoreanExample`과 필드가 같지만 의미(한 사람의 한 줄)가 달라 따로 둔다. 하나로 합칠지는 구현자 판단에 맡긴다.

`frontend/src/types.ts`의 `Expression`에 `korean_dialogue?: KoreanLine[] | null`, `KoreanLine { korean; english }`를 더한다.

### 읽기

`backend/app/db/expressions.py`:

- `COLUMNS`에 `e.korean_dialogue`를 더한다.
- `expression_from`이 `korean_dialogue=row["korean_dialogue"] and json.loads(row["korean_dialogue"])`로 읽는다.
- 세션 내용, `ExpressionRepo.get`, `list_all`이 모두 이 경로를 지나므로 따로 고칠 곳은 없다. `COLUMNS`를 쓰는 다른 쿼리가 있는지는 구현 때 확인한다.

### 쓰기

`ExpressionRepo`에 두 메서드를 더한다.

- `without_dialogue(limit: int | None) -> list[Expression]`: `korean_dialogue IS NULL`인 표현, id 순.
- `set_dialogue(expression_id: int, lines: list[KoreanLine]) -> None`: JSON으로 쓴다 (`ensure_ascii=False`). 이벤트는 내지 않는다 (위 결정 6).

`upsert`(표현 가져오기)는 `korean_dialogue`를 건드리지 않는다. 같은 표현을 다시 가져와도 대화문은 남는다. `korean_example`도 지금 그렇다.

## 생성 모듈

위치와 실행:

```
docker compose exec backend uv run --no-dev python -m app.generation.korean_dialogues [--apply] [--limit N] [--batch N] [--model M] [--effort E]
```

`app.accounts.reset_password`와 같은 꼴이다. DB 경로는 `os.environ.get("DB_PATH", ROOT / "data" / "sessions.db")`.

동작:

1. 대화문이 없는 표현을 `--limit`만큼(기본: 전부) 고른다.
2. `--batch`개(기본 20)씩 묶어 `Claude.run(prompt, schema, label="korean dialogues")` 한 번에 보낸다. `Claude`는 `app.llm`의 것을 그대로 쓰고, 도구는 없다. 기본 모델 `opus`, effort `medium`, `timeout_s`는 묶음 하나가 끝날 만큼 넉넉히(예: 300). 모두 플래그로 바꿀 수 있다.
3. 결과에서 묶음에 보낸 id마다 정확히 두 줄이 있는지 본다. 빠졌거나 줄 수가 틀린 id는 건너뛰고 경고를 찍는다. 다음 실행에서 다시 채워진다.
4. `--apply`가 없으면 아무것도 쓰지 않고 표현마다 phrase와 두 줄(한국어, 영어)을 출력한다. 품질을 보려면 `--limit 10`처럼 조금만 돌린다.
5. `--apply`가 있으면 묶음이 끝날 때마다 그 묶음을 쓴다. 중간에 실패해도 끝난 묶음은 남고, 다시 돌리면 빈 것만 채운다.
6. `GenerationError`가 나면 그 묶음을 건너뛰고 다음으로 간다. 끝에 채운 수, 건너뛴 수를 출력한다. 하나라도 건너뛰면 종료 코드는 1이다.

구조: 묶음 하나를 대화문으로 바꾸는 부분(`Runner`를 받는 함수나 클래스)과, DB에서 골라 묶고 쓰는 부분(`main`)을 나눈다. 테스트는 앞부분에 가짜 `Runner`를 넣는다.

### 프롬프트가 요구할 것

표현마다 `id`, `phrase`, `meaning`, `usage_note`, `examples`(영어 예문), `korean_example`(있으면)을 준다.

- A와 B가 한 줄씩 말하는 자연스러운 일상 대화. B는 A에 대한 대답이나 반응이다.
- 적어도 한 줄의 영어 답안은 표현을 쓴다. 다른 줄은 대화가 자연스러우면 표현을 안 써도 된다. 둘 다 억지로 넣지 않는다.
- 표현을 쓰는 줄이 A일지 B일지는 대화에 맞게 정한다. 한쪽으로 쏠리지 않게 한다.
- 상황은 영어 예문과 한 문장 예문(`korean_example`)과 다르다.
- 한국어는 사람들이 실제로 하는 구어. 영어 답안은 그 한국어를 자연스럽게 옮긴 것이며, 표현이 든 줄은 표현의 뜻과 `usage_note`의 쓰임에 맞다.
- 한 줄은 짧다. 한두 문장.

출력 스키마:

```json
{
  "type": "object",
  "properties": {
    "dialogues": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "integer"},
          "lines": {
            "type": "array", "minItems": 2, "maxItems": 2,
            "items": {
              "type": "object",
              "properties": {"korean": {"type": "string"}, "english": {"type": "string"}},
              "required": ["korean", "english"]
            }
          }
        },
        "required": ["id", "lines"]
      }
    }
  },
  "required": ["dialogues"]
}
```

## 화면

`frontend/src/components/ExpressionsTab.tsx`의 `KoreanExample`이 두 모드를 품는 컴포넌트가 된다 (이름은 구현자 판단).

```
한국어로 해 보기                    [ 한 문장 | 대화 ]
┌───────────────────────────────────────────────┐
│ A  아까 회의에서 인사한 분 이름 기억나?               │
│ B  죄송한데, 성함을 못 들었어요.                     │
│ 영어로 어떻게 말할까요?                            │
└───────────────────────────────────────────────┘
          누르면
┌───────────────────────────────────────────────┐
│ A  Do you remember the name of the guy from    │
│    the meeting?                               │
│ B  Sorry, I didn't catch your name.            │
│    (표현에 형광펜)                               │
│ 모범 답안 · 다르게 말해도 표현을 넣었으면 충분해요       │
└───────────────────────────────────────────────┘
```

- 토글: 라벨 줄 오른쪽의 두 칸 짜리 선택. 키보드와 화면 낭독기로 쓸 수 있어야 한다(예: 버튼 두 개에 `aria-pressed`, 또는 radio group). 공유 키는 `mode:{id}`, 값 `'dialogue' | 'solo'`, 기본 `'dialogue'`. presence 서버는 `KEY = re.compile(r"[a-z]+(:[a-z0-9]+)*")`(`backend/app/live/presence.py`)에 안 맞는 키를 오류 없이 버리고, 바꾼 사람 화면만 바뀐다. 그래서 키에 하이픈을 쓰지 않는다. `dialogue:{id}`도 이 패턴에 맞는다.
- 대화 카드: 지금 카드와 같은 버튼 하나. 안에 A, B 줄이 차례로 있고 각 줄 앞에 화자 표시 "A", "B". 누르면 두 줄 모두 영어, 다시 누르면 한국어. 아래 안내 문구는 지금 카드와 같다.
- 한 문장 카드: 지금과 같다.
- 스타일은 `ExpressionsTab.css`의 `.korean-example*`를 따른다. 화자 표시는 본문보다 흐리게.
- 탭 위 안내(`tab-brief`): "Read the examples aloud, then each of you says the Korean sentence in English before you tap it for the model answer." 대화도 덮도록 고친다. 문장은 구현자 판단. 예: "Read the examples aloud, then say the Korean in English, each of you a sentence or one side of the dialogue, before you tap it for the model answer."

## 테스트

백엔드:

- `test_schema.py`: v16 파일(열을 지운 파일)을 열면 v17이 되고 모든 표현의 `korean_dialogue`가 None. 새 파일에도 열이 있다.
- `test_expressions.py`: 대화문이 세션 내용, `get`, `list_all`로 나온다. `without_dialogue`는 빈 것만 id 순으로, `limit`을 지킨다. `set_dialogue` 뒤에는 빠진다. `upsert`로 다시 가져와도 대화문이 남는다.
- 생성 모듈: 가짜 Runner로, 미리보기는 DB를 바꾸지 않는다. `--apply`는 묶음별로 쓴다. 줄 수가 틀리거나 빠진 id는 건너뛰고 남는다. 한 묶음의 `GenerationError`가 다른 묶음을 막지 않는다. 묶음 크기만큼 나눠 부른다.

프론트엔드 (`ExpressionsTab.test.tsx`):

- 둘 다 있으면 토글이 보이고 기본은 대화. 두 줄과 A, B가 보인다.
- 대화 카드를 누르면 두 줄 모두 영어, 표현이 있는 줄에 `mark`. 다시 누르면 한국어.
- 토글로 한 문장으로 바꾸면 지금 한 문장 카드.
- 하나만 있으면 토글이 없고 그것만 보인다. 둘 다 없으면 영역이 없다 (기존 테스트 유지).
- presence: 다른 사람이 모드를 바꾸거나 대화 카드를 뒤집으면 나도 바뀐다 (기존 "flips the Korean card with them" 테스트 꼴).

프론트엔드 presence 테스트는 가짜 소켓을 써서 서버가 키를 버려도 통과한다. 그래서 백엔드 presence 테스트에 `mode:{id}`와 `dialogue:{id}`가 `_read_view`를 지나 다른 사람에게 전달되는지 확인하는 테스트를 더한다.

## 문서와 운영

- `docs/superpowers/specs/2026-10-25-sqlite-schema-redesign-design.md`: 155줄 "한국어 예문" 항목에서 없어진 스크립트 경로를 지우고 대화문과 토글, 생성 모듈을 적는다. 144줄 버전 문단에 v17을 더한다. 81줄 스키마 블록에 `korean_dialogue`를 더한다.
- `.claude/skills/expression-cleanup/SKILL.md`: 표현을 새로 가져온 뒤 대화문 생성 모듈을 돌리라는 한 줄.
- 배포: 서버(이 호스트)에서 새 이미지로 backend를 다시 띄우면 v17 업그레이드와 백업이 일어난다. 그다음 `--limit 10` 미리보기로 품질을 보고, 괜찮으면 `--apply`로 전부 채운다. 932개, 묶음 20개면 Claude 실행 47번이고 구독 사용량이 든다.
- 버전: main 머지 후 `scripts/bump-version patch`.

## 구현자에게 맡기는 것

- 컴포넌트, 함수, 상수 이름. `KoreanLine`과 `KoreanExample`을 합칠지.
- 토글의 정확한 마크업과 스타일, `tab-brief` 문장.
- 프롬프트 문장. 단, 위 "프롬프트가 요구할 것"은 모두 담는다.
- 묶음 크기, 타임아웃, 기본 모델과 effort의 정확한 값.
