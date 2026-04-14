from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.config import settings
from app.core.logging import setup_logging
from app.core.middleware import TraceMiddleware
from app.database import Base, engine
from app.routers import kakao, slack, admin

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FastAPI Slack middleware...")
    if settings.APP_ENV == "development":
        # 개발 환경: 테이블 자동 생성 (Alembic 없이 빠른 시작)
        Base.metadata.create_all(bind=engine)
    # 운영 환경: 배포 전 `alembic upgrade head` 별도 실행 필요
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="카카오톡-슬랙 통합 미들웨어",
    description="카카오톡 비즈니스 채널과 슬랙을 양방향으로 연동하는 미들웨어",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(TraceMiddleware)

app.include_router(kakao.router)
app.include_router(slack.router)
app.include_router(admin.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
