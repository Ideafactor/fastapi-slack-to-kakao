import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request, status

from app.config import settings


async def verify_slack_signature(
    request: Request,
    x_slack_signature: str | None = Header(None),
    x_slack_request_timestamp: str | None = Header(None),
) -> None:
    """슬랙 웹훅 서명 검증 (HMAC-SHA256).

    슬랙 공식 가이드:
    1. 타임스탬프 5분 초과 시 재전송 공격 차단
    2. 'v0:{timestamp}:{body}' 문자열에 signing secret으로 HMAC-SHA256 서명
    3. 헤더의 X-Slack-Signature와 비교
    """
    if not x_slack_signature or not x_slack_request_timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Slack signature headers",
        )

    # 5분 초과 요청 차단 (재전송 공격 방지)
    try:
        timestamp = int(x_slack_request_timestamp)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timestamp")

    if abs(time.time() - timestamp) > 300:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Request timestamp too old",
        )

    body = await request.body()
    sig_basestring = f"v0:{x_slack_request_timestamp}:{body.decode('utf-8')}"
    computed = (
        "v0="
        + hmac.new(
            key=settings.SLACK_SIGNING_SECRET.encode("utf-8"),
            msg=sig_basestring.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(computed, x_slack_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature",
        )
