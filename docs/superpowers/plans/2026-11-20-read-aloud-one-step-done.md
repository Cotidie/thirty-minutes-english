# Read aloud: Done 한 번으로 끝내기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 이 세션에서 직접 실행하고 끝에 새 서브에이전트 리뷰를 한 번 한다. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Done을 누르면 라운드가 저장되고 바로 닫힌다. 저장에 실패하면 오류와 Close가 남는다.

**Architecture:** `useReadAloudRound`(`frontend/src/components/ReadAloud.tsx`)의 `done`이 저장 결과를 기다려, 성공하면 새 private `finish`(라운드를 비우고, 공유를 끝내고, 마이크를 풀고, 통화는 두는 것)를 부르고, 실패하면 `setError('Could not save this round.')`. `reset`(Close)은 `hangUp` + `endRound` + `finish`.

**Tech Stack:** React 19, TypeScript, vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-20-read-aloud-one-step-done-design.md`

## Global Constraints

- 브랜치 `fix/read-aloud-one-step-done`. `--ff-only`로 합치고 `scripts/bump-version patch`. 사용자가 배포와 push까지 말했다 (대화문 채우기가 끝난 뒤).
- 고치기 전에 GitNexus `impact`, 커밋 전에 `detect-changes`. 커밋 메시지에 `Co-Authored-By` 없음.
- 오류 문구는 정확히 "Could not save this round."
- 테스트: `cd frontend && npx vitest run`(기준 544), `npx tsc -b --noEmit`, `npm run lint`(기존 경고 23개).

## Review Focus

1. 저장 실패 → 패널이 남고 오류, Close, 이번 표시가 보인다. (`keeps the round open with Close when it could not be saved`)
2. 코치가 말하는 중에 Done → 통화가 끊기지 않는다. (`lets a coach that is speaking finish when Done closes the round`)
3. Azure가 멈추며 넘긴 마지막 조각 → 저장에 들어가고, 다른 사람에게는 마지막에 null. (`says the round is over once Done has filed it, the last segment included`)
4. 저장 중에 페이지를 떠남 → 상태를 바꾸지 않는다 (기존 `mounted` 확인). 기존 테스트 `says the round is over when the page is left…`가 지킨다.
5. 깨끗한 라운드 → 저장되고 바로 닫혀 Read aloud로 돌아온다. (`files a clean round too … returns to idle on Done`)

---

### Task 1: Done이 라운드를 닫는다

**Files:** Modify `frontend/src/components/ReadAloud.tsx`; Test `frontend/src/components/ReadAloud.test.tsx`, `frontend/src/components/ArticleTab.test.tsx`.

- [ ] **Step 1: impact** — `useReadAloudRound`(또는 파일 안의 훅 이름), `ReadAloudPanel`.

- [ ] **Step 2: 테스트를 새 흐름으로 고치고 더한다** (`ReadAloud.test.tsx`)
  - `opens the microphone for Azure only, shows what was heard, and files the round on Done`: `Round over` 확인을 지우고, 저장 확인 뒤 `await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())`.
  - `keeps the round done for the others when a last segment lands while Azure stops`: 마지막이 아니라 보낸 것 중에 `{ paragraph: 7, phase: 'done', findings: [verified…] }`가 있고, 저장 뒤 마지막은 `null`.
  - `says the round is over on Close, even if Azure hands over more as it stops` → `says the round is over once Done has filed it, the last segment included`: Done, `finish()`, `addReading`이 `corrections`에 `verified`를 담아 불림, 마지막 공유 `null`.
  - `files a clean round too, so the old marks do not come back, and returns to idle on Close` → `… returns to idle on Done`: Close 클릭을 지우고 `onEnd` 호출과 `Read aloud` 버튼을 `waitFor`로.
  - `keeps the marks after Close, still clickable, with Read again on offer` → `finishes on Done with the marks still clickable and Read again on offer`: Close 클릭을 지우고, `Close` 버튼이 없음을 확인.
  - `after Close the paragraph shows the marks it is given again, not its own round's` → `after Done …`: Done 뒤 `waitFor`로 주어진 표시가 돌아옴.
  - `still dials the coach after Done, and drops the call on Close` → `lets a coach that is speaking finish when Done closes the round`: 표시를 눌러 `connect` 확인 → Done → `onEnd` 호출 → `connection.dispose` 안 불림.
  - 새 `keeps the round open with Close when it could not be saved`: `addReading`이 한 번 reject → 오류 문구, `Close`, `verified: b for v` 표시가 보임 → Close → `onEnd`.
  - `ArticleTab.test.tsx`의 `tells them about my round, from the start until I close it` → `… until I finish it`: Done 뒤 마지막 공유가 `null`(Close 클릭 없음).

- [ ] **Step 3: 실패 확인** — `npx vitest run src/components/ReadAloud.test.tsx src/components/ArticleTab.test.tsx`. Expected: 고친 테스트들이 Close가 남아 있거나 상태가 남아 FAIL.

- [ ] **Step 4: 구현** — Architecture대로. `done`은 `endRound` 뒤 `api.addReading(...).then(onFiled)`의 성공 여부를 받고, `!mounted.current || roundRef.current !== round`면 아무것도 하지 않는다.

- [ ] **Step 5: 통과 확인** — `npx vitest run`, `npx tsc -b --noEmit`, `npm run lint`.

- [ ] **Step 6: 커밋** — `git commit -m "fix: Done ends a read-aloud round in one step"`.

### Task 2: 마무리

- [ ] 새 서브에이전트 리뷰 한 번, spec 상태 "구현됨", `--ff-only` 합치기, `scripts/bump-version patch`.
- [ ] 대화문 채우기가 끝났으면 배포(진행 중 job 확인 뒤 `docker compose up -d --build`)와 `git push --follow-tags origin main`.
