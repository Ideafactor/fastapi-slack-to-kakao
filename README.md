# 카카오톡-슬랙 통합 미들웨어

카카오톡 비즈니스 채널과 슬랙(Slack) 워크스페이스를 양방향으로 연동하는 FastAPI 기반 미들웨어 시스템입니다. 고객의 카카오톡 메시지를 실시간으로 슬랙 채널에 릴레이하고, 상담원이 슬랙에서 작성한 답변을 카카오톡으로 전송합니다.

## 아키텍처

```
카카오톡 고객  ──→  카카오 서버  ──→  FastAPI (웹훅 수신)
                                         │
                                    Redis (브로커)
                                         │
                                   Celery Worker
                                         │
                          ┌──────────────┴──────────────┐
                     슬랙 채널 자동 생성             카카오 API 응답
                          │                              │
                     Slack API                      카카오 고객
```

- **FastAPI**: 웹훅 수신 및 즉각 응답 (3초 이내)
- **Celery + Redis**: 비동기 태스크 처리 (메시지 릴레이, 파일 업로드 등)
- **PostgreSQL**: 카카오 userKey ↔ 슬랙 채널 ID 매핑 영속 저장
- **AWS S3**: 미디어 파일 임시 저장 및 URL 중계

## 주요 기능

- **실시간 양방향 메시지 연동**: 카카오톡 ↔ 슬랙 메시지 실시간 릴레이
- **슬랙 채널 자동 생성**: 신규 고객 최초 메시지 수신 시 1:1 전용 채널 자동 생성 및 매핑
- **미디어 파일 전송**: 이미지, 문서 등 첨부파일 양방향 전송 (S3 경유)
- **무한 루프 방지**: 봇 메시지 필터링으로 메시지 중복 발송 차단
- **Rate Limit 대응**: 트리아지 채널 + 지수 백오프 재시도 전략
- **DLQ(Dead Letter Queue)**: 처리 실패 메시지 별도 보관 및 재처리

## 프로젝트 구조

```
app/
├── main.py              # FastAPI 앱 진입점
├── config.py            # 환경 변수 설정 (pydantic-settings)
├── database.py          # SQLAlchemy 엔진 및 세션
├── core/
│   ├── logging.py       # Loguru 로깅 설정
│   └── middleware.py    # 트레이스 미들웨어
├── models/
│   ├── channel_mapping.py  # 카카오 userKey ↔ 슬랙 채널 매핑
│   ├── message_log.py      # 메시지 처리 이력
│   ├── user_session.py     # 사용자 세션 정보
│   └── dead_letter.py      # DLQ 레코드
├── routers/
│   ├── kakao.py         # 카카오톡 웹훅 엔드포인트
│   ├── slack.py         # 슬랙 Events API 엔드포인트
│   └── admin.py         # 관리 API
├── services/
│   ├── kakao_service.py    # 카카오 API 호출 로직
│   ├── slack_service.py    # 슬랙 API 호출 로직
│   ├── channel_service.py  # 채널 생성 및 매핑 관리
│   ├── file_service.py     # 미디어 파일 처리
│   ├── s3_service.py       # AWS S3 업로드/다운로드
│   └── dlq_service.py      # Dead Letter Queue 처리
├── schemas/             # Pydantic 요청/응답 스키마
└── tasks/               # Celery 태스크 정의
alembic/                 # DB 마이그레이션
docker-compose.yml
Dockerfile
requirements.txt
```

## 시작하기

### 사전 요구사항

- Docker & Docker Compose
- 카카오 비즈니스 채널 API 키
- Slack 앱 (Bot Token, Signing Secret)
- AWS S3 버킷 (미디어 파일 전송 시)

### 환경 변수 설정

`.env` 파일을 생성합니다.

```env
APP_ENV=development

DATABASE_URL=postgresql://postgres:password@localhost:5432/fastapi_slack
REDIS_URL=redis://localhost:6379/0

KAKAO_ADMIN_KEY=your_kakao_admin_key
KAKAO_API_URL=https://your-kakao-api-url

SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_SIGNING_SECRET=your_slack_signing_secret
SLACK_TRIAGE_CHANNEL_ID=C0XXXXXXXXX

# AWS S3 (미디어 파일 전송 시 필요)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=your-bucket-name
S3_PUBLIC_BASE_URL=https://your-bucket.s3.ap-northeast-2.amazonaws.com
```

### Docker Compose로 실행

```bash
docker-compose up -d
```

서비스 실행 순서: `postgres` → `migrate` (Alembic) → `api` + `worker`

### API 문서

서버 실행 후 접속:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- 헬스체크: `http://localhost:8000/health`

### 로컬 개발 환경

```bash
pip install -r requirements.txt

# DB 마이그레이션
alembic upgrade head

# FastAPI 서버
uvicorn app.main:app --reload

# Celery 워커 (별도 터미널)
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
```

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/kakao/webhook` | 카카오톡 웹훅 수신 |
| `POST` | `/slack/events` | 슬랙 Events API 수신 |
| `GET`  | `/admin/...` | 관리 API |
| `GET`  | `/health` | 헬스체크 |

## 기술 스택

| 분류 | 기술 |
|------|------|
| 웹 프레임워크 | FastAPI 0.115, Uvicorn |
| 데이터베이스 | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| 태스크 큐 | Celery 5.4, Redis 7 |
| HTTP 클라이언트 | httpx |
| 이미지 처리 | Pillow |
| 클라우드 스토리지 | AWS S3 (boto3) |
| 로깅 | Loguru |
| 배포 | Docker, AWS ECS Fargate |
