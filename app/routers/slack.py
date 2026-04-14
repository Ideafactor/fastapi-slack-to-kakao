from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.redis import is_duplicate_event
from app.core.security import verify_slack_signature
from app.schemas.slack import SlackEventCallback
from app.tasks.message_tasks import relay_slack_file_to_kakao, relay_slack_to_kakao

router = APIRouter(prefix="/slack", tags=["slack"])


@router.post("/events", dependencies=[Depends(verify_slack_signature)])
async def slack_events(request: Request) -> JSONResponse:
    """슬랙 Events API 수신 엔드포인트.

    - HMAC-SHA256 서명 검증 (Depends)
    - url_verification challenge 처리
    - 중복 이벤트 필터링 (Redis)
    - 봇 메시지 필터링 (무한 루프 방지)
    - 텍스트/파일 이벤트 → Celery 태스크 위임
    """
    body = await request.json()
    event_type = body.get("type")

    # 슬랙 엔드포인트 소유권 인증 (최초 1회)
    if event_type == "url_verification":
        challenge = body.get("challenge", "")
        logger.info("Slack url_verification challenge received")
        return JSONResponse(content={"challenge": challenge})

    payload = SlackEventCallback(**body)

    if event_type != "event_callback" or not payload.event:
        return JSONResponse(content={"status": "ignored"})

    # 중복 이벤트 필터링 (event_id 기반, TTL 5분)
    if payload.event_id and is_duplicate_event(payload.event_id):
        logger.debug(f"Duplicate slack event ignored: {payload.event_id}")
        return JSONResponse(content={"status": "duplicate"})

    event = payload.event

    # 봇 메시지 필터링 (무한 루프 방지)
    if event.bot_id or event.display_as_bot:
        return JSONResponse(content={"status": "ignored"})

    # message subtype 있으면 편집/삭제 등 — 무시
    if event.subtype:
        return JSONResponse(content={"status": "ignored"})

    if event.type != "message" or not event.channel:
        return JSONResponse(content={"status": "ignored"})

    logger.info(
        f"Slack message event | channel={event.channel} user={event.user} ts={event.ts}"
    )

    # 파일 첨부 이벤트 처리
    if event.files:
        for file_info in event.files:
            file_url = file_info.get("url_private_download") or file_info.get("url_private")
            filename = file_info.get("name", "attachment")
            mimetype = file_info.get("mimetype", "application/octet-stream")
            if file_url:
                relay_slack_file_to_kakao.delay(
                    channel_id=event.channel,
                    file_url=file_url,
                    filename=filename,
                    mimetype=mimetype,
                    slack_ts=event.ts,
                )
        # 파일과 함께 텍스트가 있으면 텍스트도 별도 발송
        if not event.text:
            return JSONResponse(content={"status": "accepted"}, status_code=status.HTTP_200_OK)

    # 텍스트 메시지 릴레이
    if not event.text:
        return JSONResponse(content={"status": "ignored"})

    relay_slack_to_kakao.delay(
        channel_id=event.channel,
        text=event.text,
        slack_ts=event.ts,
        slack_event_id=payload.event_id,
    )

    return JSONResponse(content={"status": "accepted"}, status_code=status.HTTP_200_OK)
