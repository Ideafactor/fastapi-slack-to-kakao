from fastapi import APIRouter, Header, HTTPException, Request, status
from loguru import logger

from app.config import settings
from app.core.redis import is_duplicate_event
from app.schemas.kakao import KakaoWebhookPayload
from app.tasks.message_tasks import notify_channel_blocked, relay_kakao_file_to_slack, relay_kakao_to_slack

router = APIRouter(prefix="/kakao", tags=["kakao"])


def _verify_kakao_auth(authorization: str | None) -> None:
    """카카오 어드민 키 검증."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    expected = f"KakaoAK {settings.KAKAO_ADMIN_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Kakao admin key")


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def kakao_webhook(
    payload: KakaoWebhookPayload,
    request: Request,
    authorization: str | None = Header(None),
    x_kakao_resource_id: str | None = Header(None),
) -> dict:
    """카카오 웹훅 수신 엔드포인트.

    - 3초 이내 응답을 위해 즉시 202 반환
    - 실제 처리는 Celery 태스크로 위임
    """
    _verify_kakao_auth(authorization)

    user_key = payload.identifier
    if not user_key:
        logger.warning("Kakao webhook received without user identifier")
        return {"status": "ignored"}

    event = payload.event or ""
    logger.info(f"Kakao webhook | event={event} user={user_key} resource_id={x_kakao_resource_id}")

    # 중복 이벤트 필터링 (X-Kakao-Resource-ID 기반, TTL 5분)
    if x_kakao_resource_id and is_duplicate_event(x_kakao_resource_id):
        logger.debug(f"Duplicate kakao event ignored: {x_kakao_resource_id}")
        return {"status": "duplicate"}

    # 차단/언링크 이벤트 처리
    if event in ("blocked", "unlink"):
        from app.database import SessionLocal
        from app.services.channel_service import ChannelService

        db = SessionLocal()
        try:
            channel_id = ChannelService().get_channel_id(db, user_key)
        finally:
            db.close()

        if channel_id:
            notify_channel_blocked.delay(user_key=user_key, channel_id=channel_id)
        return {"status": "accepted"}

    # 미디어 파일 이벤트 처리
    if payload.message and payload.message.media_url:
        relay_kakao_file_to_slack.delay(
            user_key=user_key,
            media_url=payload.message.media_url,
            media_name=payload.message.media_name or "attachment",
            nickname=payload.nickname,
            kakao_message_id=x_kakao_resource_id,
        )
        return {"status": "accepted"}

    # 텍스트 메시지 릴레이
    text = payload.text
    if not text:
        return {"status": "ignored"}

    relay_kakao_to_slack.delay(
        user_key=user_key,
        text=text,
        nickname=payload.nickname,
        icon_url=None,
        kakao_message_id=x_kakao_resource_id,
    )

    return {"status": "accepted"}
