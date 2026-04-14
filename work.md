# 카카오톡-슬랙 연동 미들웨어 작업 기록

---

## DB 구축 가이드

### 별도 DB 구축 불필요 — 환경별 자동화

#### 개발 환경
```bash
cp .env.example .env   # 키값 입력
docker-compose up      # PostgreSQL 컨테이너 + 테이블 자동 생성
```
`APP_ENV=development`일 때 앱 시작 시 `Base.metadata.create_all()`이 자동 실행됨.

#### 운영 환경 (첫 배포)
```bash
APP_ENV=production alembic upgrade head
# → alembic/versions/0001_init.py 실행 → 4개 테이블 + 인덱스 생성
```

#### 스키마 변경 시
```bash
alembic revision --autogenerate -m "add_column_xxx"
alembic upgrade head

# 롤백
alembic downgrade -1
```

#### docker-compose 기동 순서 보장
```
postgres (healthcheck 통과) → migrate (alembic upgrade head 완료) → api + worker 시작
```

### DB 테이블 구조 요약

| 테이블 | PK | 역할 |
|--------|-----|------|
| `channel_mapping` | `kakao_user_key` | 카카오 userKey ↔ 슬랙 channel_id 1:1 매핑 |
| `user_session` | `kakao_user_key` | 고객 마지막 활성 시각, 차단 여부 |
| `message_log` | `message_id` (UUID) | 양방향 메시지 전체 이력 (direction, payload_type) |
| `dead_letter` | `id` (UUID) | 재시도 초과 실패 태스크 보관 (PENDING→REPLAYED/DISCARDED) |

`kakao_user_key`가 channel_mapping, user_session, message_log 3개 테이블의 연결 키.

---

## 1단계 (MVP) — 2026-04-14

### 목표
카카오톡 → 슬랙 텍스트 메시지 전달 및 핵심 인프라 초기화

### 구현 내용

#### 프로젝트 기본 구조
- `requirements.txt`: fastapi, uvicorn, celery, redis, sqlalchemy, alembic, httpx, loguru
- `.env.example`: 환경변수 템플릿 (DB, Redis, Kakao, Slack 키)
- `Dockerfile` + `docker-compose.yml`: API 서버, Celery 워커, PostgreSQL, Redis 컨테이너 구성

#### DB 모델 (SQLAlchemy + Alembic)
| 파일 | 테이블 | 역할 |
|------|--------|------|
| `app/models/channel_mapping.py` | `channel_mapping` | 카카오 `userKey` ↔ 슬랙 `channel_id` 1:1 매핑, status(ACTIVE/ARCHIVED) |
| `app/models/message_log.py` | `message_log` | 양방향 메시지 감사 이력, direction/payload_type ENUM |
| `app/models/user_session.py` | `user_session` | 고객 세션 상태, `is_blocked` 차단 여부 |

#### Pydantic 스키마
- `app/schemas/kakao.py`: `KakaoWebhookPayload` — userKey/app_user_id 통합 식별, 이벤트 타입, 메시지 파싱
- `app/schemas/slack.py`: `SlackEventCallback` — url_verification, message 이벤트

#### 서비스 레이어
- `app/services/slack_service.py`: `SlackService` — `conversations.create`, `chat.postMessage`, `conversations.archive`
- `app/services/channel_service.py`: `ChannelService` — DB 조회/저장, 역참조(채널→userKey), 차단 처리
- `app/services/kakao_service.py`: `KakaoService` — 카카오 상담톡 메시지 발송

#### Celery 태스크
- `app/tasks/celery_app.py`: Celery 앱 초기화, Redis 브로커, `task_acks_late=True`
- `app/tasks/message_tasks.py`:
  - `relay_kakao_to_slack`: 채널 조회 → 없으면 생성 → 메시지 전송 → Message_Log 기록
  - `notify_channel_blocked`: 차단 알림 메시지 → 채널 아카이브
  - 지수 백오프 재시도 (2s → 4s → 8s …, 최대 5회)
  - Rate Limit 시 트리아지 채널 fallback

#### API 엔드포인트
- `POST /kakao/webhook`: KakaoAK 헤더 검증 → 즉시 202 반환 → Celery 위임
- `POST /slack/events`: url_verification challenge 처리
- `GET /health`: 헬스체크

---

---

## Alembic 마이그레이션 — 2026-04-14

### 목표
운영 환경용 DB 스키마 버전 관리 체계 구축

### 구현 내용

#### 마이그레이션 파일 (`alembic/versions/0001_init.py`)
- 4개 테이블 전체 DDL 포함 (channel_mapping, user_session, message_log, dead_letter)
- ENUM 타입 생성 포함 (channelstatus, messagedirection, payloadtype, dlqstatus)
- 조회 성능을 위한 인덱스 추가
  - `channel_mapping`: status
  - `user_session`: is_blocked
  - `message_log`: kakao_user_key, slack_channel_id, created_at
  - `dead_letter`: status, task_name, created_at
- `downgrade()`: 전체 테이블 및 ENUM 타입 삭제

#### Alembic env.py 개선 (`alembic/env.py`)
- `DATABASE_URL` 환경변수 우선 읽기 (alembic.ini 하드코딩 대신)
- `compare_type=True`, `compare_server_default=True` 활성화 → 컬럼 변경 자동 감지

#### app/main.py 환경 분기
- `APP_ENV=development`: `create_all()` 자동 실행 (빠른 개발)
- `APP_ENV=production`: Alembic 전용 (`alembic upgrade head` 별도 실행)

#### docker-compose.yml 개선
- `migrate` 서비스 추가: `alembic upgrade head` 실행 후 종료
- `postgres` healthcheck 추가: `pg_isready` 응답 확인 후 migrate 실행
- `api`, `worker`: migrate 완료 후에만 시작 (`service_completed_successfully`)

### 실행 방법
```bash
# 개발 (자동)
docker-compose up

# 운영 배포
APP_ENV=production alembic upgrade head

# 스키마 변경 시 새 마이그레이션 생성
alembic revision --autogenerate -m "add_column_xxx"
alembic upgrade head

# 롤백
alembic downgrade -1
```

---

## 4단계 — 2026-04-14

### 목표
DLQ, 재시도 고도화, 구조화 로깅/분산 추적, 관리자 API 구현

### 구현 내용

#### Dead Letter Queue (`app/models/dead_letter.py`, `app/services/dlq_service.py`)
- `DeadLetter` DB 테이블: `task_name`, `task_kwargs`(JSON), `error_message`, `retry_count`, `status`(PENDING/REPLAYED/DISCARDED)
- `DLQService`: `push`, `list_pending`, `get`, `mark_replayed`, `mark_discarded`
- `BaseTaskWithRetry.on_failure` 훅: 최대 재시도 초과 시 자동으로 DLQ에 저장

#### 재시도 고도화 (`app/services/slack_service.py`, `app/tasks/message_tasks.py`)
- `SlackRateLimitError`: 슬랙 429 응답 전용 예외 클래스, `retry_after` 속성 포함
- `_check_slack_response`: 모든 슬랙 API 호출에 공통 적용 (429 → `SlackRateLimitError`, 그 외 → `RuntimeError`)
- `_retry_or_raise` 공통 헬퍼:
  - `SlackRateLimitError` → `Retry-After` 헤더값 기반 정확한 대기 후 재시도
  - 4xx 비재시도 오류 (`not_authed`, `channel_not_found` 등) → 즉시 중단
  - 그 외 → 지수 백오프 (`2^n`초)
- 전체 태스크에 `_retry_or_raise` 일괄 적용

#### 구조화 로깅 (`app/core/logging.py`)
- Loguru JSON 포맷 stdout 출력 (`enqueue=True`로 비동기 로깅)
- `setup_logging()` 앱 시작 시 호출

#### 분산 추적 미들웨어 (`app/core/middleware.py`)
- `TraceMiddleware`: 모든 요청에 `trace_id` 부여
  - 카카오: `X-Kakao-Resource-ID` 헤더 우선 사용
  - 없으면 UUID 생성
- 요청/응답 진입·종료 로그 + 소요 시간 기록
- 응답 헤더 `X-Trace-Id`로 trace_id 반환
- `trace_id_var` ContextVar로 전체 수명주기 전파

#### 관리자 API (`app/routers/admin.py`)
| 엔드포인트 | 설명 |
|-----------|------|
| `GET /admin/dlq` | PENDING 항목 목록 조회 (limit/offset 페이지네이션) |
| `POST /admin/dlq/{id}/replay` | 단건 재처리 → Celery 큐 재투입 |
| `POST /admin/dlq/replay-all` | 전체 PENDING 재처리 |
| `DELETE /admin/dlq/{id}` | 항목 폐기(DISCARDED) |

---

## 3단계 — 2026-04-14

### 목표
양방향 미디어 파일 전송 파이프라인 구축 (이미지 리사이징, 슬랙 3단계 업로드, S3 fallback)

### 구현 내용

#### 의존성 추가 (`requirements.txt`)
- `Pillow==10.4.0`: 이미지 리사이징/압축
- `boto3==1.35.0`: S3 업로드 fallback

#### 설정 추가 (`app/config.py`, `.env.example`)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`, `S3_PUBLIC_BASE_URL`
- `KAKAO_IMAGE_MAX_BYTES`: 카카오 이미지 제한 (기본 500KB)

#### 파일 처리 서비스 (`app/services/file_service.py`)
- `download(url, headers)`: 범용 파일 다운로드
- `download_slack_file(url)`: 슬랙 Bearer 인증 다운로드
- `compress_image_for_kakao(data, mimetype)`: Pillow 기반 압축 파이프라인
  1. quality 85→15로 점진적 감소
  2. quality로 불가 시 해상도 scale 0.8→0.2 순차 축소
  3. 압축 불가 시 `ValueError` → 호출자에서 S3 fallback 처리

#### S3 서비스 (`app/services/s3_service.py`)
- `upload(data, filename, mimetype)`: S3 업로드 후 공개 URL 반환
- `is_configured()`: S3 설정 여부 확인
- 동영상, PDF 등 비이미지 파일 및 압축 불가 대용량 이미지 처리

#### 슬랙 파일 업로드 (`app/services/slack_service.py`)
- `upload_file(channel_id, data, filename, mimetype, title)`: 3단계 업로드
  1. `files.getUploadURLExternal` → `upload_url`, `file_id` 획득
  2. `upload_url`에 바이너리 POST
  3. `files.completeUploadExternal`로 채널에 결합

#### 카카오 서비스 추가 (`app/services/kakao_service.py`)
- `send_image(user_key, image_data, mimetype)`: multipart/form-data 이미지 발송

#### Celery 태스크 추가 (`app/tasks/message_tasks.py`)
- `relay_kakao_file_to_slack`: 카카오 미디어 URL → 다운로드 → 슬랙 파일 업로드
- `relay_slack_file_to_kakao`: 슬랙 파일 → 압축 → 카카오 발송 / S3 fallback
  - 이미지: Pillow 압축 → 카카오 이미지 API
  - 압축 실패 또는 비이미지: S3 업로드 후 다운로드 링크 텍스트 발송

#### 라우터 업데이트
- `app/routers/kakao.py`: `message.media_url` 존재 시 `relay_kakao_file_to_slack` 태스크 위임
- `app/routers/slack.py`: `event.files` 존재 시 `relay_slack_file_to_kakao` 태스크 위임 (파일+텍스트 동시 처리)

---

## 2단계 — 2026-04-14

### 목표
슬랙 → 카카오 텍스트 응답 + 보안 강화 (슬랙 서명 검증, 중복 이벤트 필터링)

### 구현 내용

#### 슬랙 서명 검증 (`app/core/security.py`)
- `verify_slack_signature` FastAPI 의존성 함수
- 슬랙 공식 HMAC-SHA256 서명 검증 로직
  - `X-Slack-Request-Timestamp` 5분 초과 요청 차단 (재전송 공격 방지)
  - `v0:{timestamp}:{body}` 문자열에 `SLACK_SIGNING_SECRET`으로 서명 후 `hmac.compare_digest` 비교
- `POST /slack/events`에 `Depends(verify_slack_signature)` 적용

#### 중복 이벤트 필터링 (`app/core/redis.py`)
- `is_duplicate_event(event_id, ttl=300)`: Redis SET NX + TTL 5분
- 카카오: `X-Kakao-Resource-ID` 헤더 기반 중복 감지
- 슬랙: `event_id` 기반 중복 감지
- 양쪽 라우터에 적용 → 동일 이벤트 재전송 시 즉시 `duplicate` 응답

#### 슬랙 → 카카오 메시지 릴레이 (`app/tasks/message_tasks.py`)
- `relay_slack_to_kakao` Celery 태스크 추가
  - 슬랙 `channel_id` → DB 역참조 → 카카오 `userKey` 확보
  - `is_blocked` 사용자 확인 후 발송 차단
  - `KakaoService.send_message` 호출
  - `Message_Log` 기록 (direction=SLACK_TO_KAKAO)
  - 지수 백오프 재시도 (최대 5회)

#### 슬랙 라우터 개선 (`app/routers/slack.py`)
- `verify_slack_signature` 의존성 연결
- `event_id` 기반 중복 이벤트 필터링 추가
- `relay_slack_to_kakao.delay(...)` 태스크 위임 연결

#### 카카오 라우터 개선 (`app/routers/kakao.py`)
- `X-Kakao-Resource-ID` 기반 중복 이벤트 필터링 추가

#### 설정 추가 (`app/config.py`, `.env.example`)
- `KAKAO_API_URL`: 카카오 상담톡 API 엔드포인트 설정 추가
