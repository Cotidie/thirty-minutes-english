# 원격 서버 배포 설계

- 상태: 구현 (2026-10-30, 브랜치 `feat/remote-deploy`).
- 범위: 이미 있는 SSH 서버에 compose 스택을 올려 그 서버의 `127.0.0.1` 포트까지 띄운다. 로컬 데이터를 서버로 옮긴다.
- 범위 밖: 외부 연결. cloudflared와 nginx는 레포 밖에서 돌고, 소유자가 거기서 이 포트로 연결한다. 로그인·계정은 다음 단계.
- 버전: 머지 후 `scripts/bump-version minor` → 0.5.0 (소유자가 minor로 지정).

## 목적

| 지금 | 바뀐 뒤 |
|---|---|
| 노트북에서 `http://localhost:5173`만 | 서버 `127.0.0.1:5173`, 앞단 프록시가 공개 |
| 데이터는 노트북 `backend/data` | 서버 `backend/data`가 원본, 로컬은 개발용 |

## 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 스택 | `compose.yaml` 하나. 로컬과 서버가 같은 파일, 같은 명령 | 서버인지는 `.env`가 정한다. overlay 없음 |
| 호스트 포트 | frontend `127.0.0.1:${FRONTEND_PORT:-5173}:80` | 앱에 로그인이 없으니 서버 공인 IP로 직접 열지 않는다. 호스트 네트워크의 nginx·cloudflared는 이 주소로 닿는다 |
| 서버 요건 | Linux x86_64, Docker Engine ≥ 23(BuildKit), root 아닌 계정 | Dockerfile의 `--mount=type=cache`, `useradd --uid` |
| 배포 | `scripts/deploy <user@host> [dir]`: ssh → `git pull --ff-only` → `docker compose up -d --build` → nginx 거쳐 `/api/sessions` 스모크 | 레포 public이라 clone에 키 불필요. 레지스트리 없음 |
| 비밀값 | 서버 `.env`(권한 600): `CLAUDE_CODE_OAUTH_TOKEN`, `UID`. API 키·모델은 DB(⚙ 모달) | 기존 구조 유지. `UID`는 서버 계정 uid와 맞춰 `backend/data` 소유권 유지 |
| 데이터 이전 | 서버 이미지 빌드 → 로컬 `docker compose down` → `sessions.db` + `images/` rsync → 서버 `up` | 정지 후 복사라 DB 일관성 보장. 빌드를 먼저 끝내 중단 시간을 줄인다 |
| 백업 | `scripts/backup <user@host> [dir]`: SQLite 온라인 백업(`Connection.backup`) → `backups/<날짜>/sessions.db`, 그림은 `backups/images/`에 rsync | 원본이 원격으로 가므로 당기는 복사본이 필요. 실행 중 DB를 그냥 rsync하면 찢어질 수 있음 |

## 변하지 않는 것

- 앱 코드(`backend/app`, `frontend/src`): 변경 없음.
  - 세션 생성은 `POST /api/sessions` → 202 + job id, 진행은 `GET /api/jobs/{id}` 폴링. 앞단 프록시의 응답 시간 제한에 안 걸림.
  - Gemini Live(WebSocket)·Azure Speech는 브라우저 → 제공자 직결. 프록시를 안 지남.
- `compose.dev.yaml`, `frontend/nginx.conf`, Dockerfile 둘 다.
- 안 옮기는 것: `backend/data/speech/`(TTS 캐시, 재생성됨), `sessions.db.bak-*`, `corpus-temment-*/`(로컬 전용 스크립트). corpus 자체는 DB 안에 있어 같이 간다.

## 앞단 프록시 요건 (레포 밖)

- 마이크는 HTTPS에서만 열린다. 공개 주소는 HTTPS여야 한다.
- 대상은 `http://127.0.0.1:5173`. 호스트 네트워크에서 도는 프록시만 닿는다. 다른 bridge 네트워크의 컨테이너는 `host.docker.internal` 경유가 안 되므로 호스트 네트워크로 돌린다.

## 로그인 전 한계

- 공개 주소를 아는 사람은 누구나 세션 생성(Claude 구독 사용량 소모), 세션 삭제, ⚙ 설정 변경(키 교체 포함) 가능.
- 노트·별·설정·세션 목록이 전원 공유. 계정이 없으니 사람별 구분 없음.

## 파일

| 파일 | 변경 |
|---|---|
| `compose.yaml` | frontend 포트를 `127.0.0.1`에 묶음 |
| `.env.example` | 포트 설명, `UID` 항목 |
| `scripts/deploy` | 신규 |
| `scripts/backup` | 신규 |
| `.gitignore` | `backups/` |
| `README.md` | 서버 배포 절 |

## 전환 절차

1. 서버: `git clone https://github.com/Cotidie/thirty-minutes-english`, `.env`(600)에 토큰과 `UID=$(id -u)`, `mkdir -p backend/data`(없으면 Docker가 root 소유로 만듦), `docker compose build`.
2. 로컬: 열린 job 없음 확인, `docker compose down`.
3. 데이터: `rsync -az backend/data/sessions.db backend/data/images <user@host>:<dir>/backend/data/`.
4. 서버: `docker compose up -d`.
5. 외부 연결: 소유자가 레포 밖에서 프록시를 `127.0.0.1:5173`에 연결.

## 검증

| 확인 | 기대 |
|---|---|
| 서버 `curl -s 127.0.0.1:5173/api/sessions` | 200, 세션 수가 로컬과 같음 |
| 서버 `ss -ltn` | 5173은 `127.0.0.1`에만, 8765 없음 |
| 다른 머신 `curl http://<서버IP>:5173` | 연결 실패 |
| `scripts/deploy <user@host>` | 끝에 `smoke ok: v0.5.0` |
| 서버에서 세션 생성 1회 | 끝까지 진행, 그림 포함 |
| `scripts/backup <user@host>` 후 복사본의 세션 수 | 서버와 같음 |

## 나중

- 로그인/계정(사람별 노트·별).
- 백업 자동화(cron으로 `scripts/backup`).
