import uuid

from celery import Task
from loguru import logger

from app.config import settings
from app.database import SessionLocal
from app.models.message_log import MessageDirection, MessageLog, PayloadType
from app.services.channel_service import ChannelService
from app.services.dlq_service import DLQService
from app.services.file_service import FileService
from app.services.kakao_service import KakaoService
from app.services.s3_service import S3Service
from app.services.slack_service import SlackRateLimitError, SlackService
from app.tasks.celery_app import celery_app

MAX_RETRIES = 5

# 재시도 불필요한 슬랙 오류 코드 (4xx 계열)
NON_RETRYABLE_ERRORS = frozenset(
    ["not_authed", "invalid_auth", "channel_not_found", "no_permission", "token_revoked"]
)


def _retry_or_raise(task, exc: Exception) -> None:
    """Rate Limit은 Retry-After 기반 대기, 4xx 비재시도 오류는 즉시 중단, 그 외 지수 백오프."""
    if isinstance(exc, SlackRateLimitError):
        countdown = exc.retry_after
        logger.warning(
            f"[{task.name}] Rate limited, retrying after {countdown}s "
            f"(attempt {task.request.retries + 1})"
        )
        raise task.retry(exc=exc, countdown=countdown, max_retries=MAX_RETRIES)

    error_msg = str(exc)
    if any(code in error_msg for code in NON_RETRYABLE_ERRORS):
        logger.error(f"[{task.name}] Non-retryable error, giving up: {exc}")
        return

    countdown = 2 ** task.request.retries
    logger.warning(
        f"[{task.name}] Failed (attempt {task.request.retries + 1}), "
        f"retrying in {countdown}s: {exc}"
    )
    raise task.retry(exc=exc, countdown=countdown, max_retries=MAX_RETRIES)


class BaseTaskWithRetry(Task):
    """모든 메시지 태스크의 기반 클래스.

    최대 재시도 초과 시 on_failure 훅에서 DLQ에 자동 저장.
    """

    abstract = True
    max_retries = MAX_RETRIES
    default_retry_delay = 2

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """최대 재시도 횟수 초과 후 최종 실패 시 DLQ에 저장."""
        db = SessionLocal()
        try:
            DLQService().push(
                db=db,
                task_name=self.name,
                task_kwargs=kwargs,
                error_message=str(exc),
                retry_count=self.max_retries,
            )
        finally:
            db.close()
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.message_tasks.relay_kakao_to_slack",
    queue="default",
)
def relay_kakao_to_slack(
    self,
    user_key: str,
    text: str,
    nickname: str = "",
    icon_url: str | None = None,
    kakao_message_id: str | None = None,
) -> None:
    """카카오 메시지를 슬랙 채널로 릴레이.

    1. DB에서 채널 조회
    2. 없으면 슬랙 채널 생성 후 DB 저장
    3. 메시지 전송
    4. Message_Log 기록
    """
    db = SessionLocal()
    channel_service = ChannelService()
    slack_service = SlackService()

    try:
        # 세션 최신화
        channel_service.upsert_user_session(db, user_key)

        # 채널 조회
        channel_id = channel_service.get_channel_id(db, user_key)

        if not channel_id:
            # 신규 고객 — 슬랙 채널 생성
            logger.info(f"New customer, creating Slack channel for {user_key}")
            try:
                result = slack_service.create_channel(user_key)
                channel_id = result["channel_id"]
                channel_service.save_channel_mapping(
                    db, user_key, channel_id, result["channel_name"]
                )
            except RuntimeError as e:
                error_msg = str(e)
                # Rate Limit 초과 시 트리아지 채널로 우선 라우팅
                if "ratelimited" in error_msg.lower() and settings.SLACK_TRIAGE_CHANNEL_ID:
                    logger.warning(f"Rate limited, routing to triage channel for {user_key}")
                    channel_id = settings.SLACK_TRIAGE_CHANNEL_ID
                    # 재시도 스케줄링 (지수 백오프)
                    raise self.retry(
                        exc=e,
                        countdown=2 ** self.request.retries,
                        max_retries=MAX_RETRIES,
                    )
                raise

        # 슬랙 메시지 전송
        username = nickname or user_key[:16]
        slack_ts = slack_service.post_message(
            channel_id=channel_id,
            text=text,
            username=username,
            icon_url=icon_url,
        )

        # Message_Log 기록
        log = MessageLog(
            message_id=str(uuid.uuid4()),
            kakao_user_key=user_key,
            kakao_message_id=kakao_message_id,
            slack_channel_id=channel_id,
            slack_ts=slack_ts,
            direction=MessageDirection.KAKAO_TO_SLACK,
            payload_type=PayloadType.TEXT,
        )
        db.add(log)
        db.commit()

        logger.info(f"relay_kakao_to_slack done | user={user_key} channel={channel_id} ts={slack_ts}")

    except Exception as exc:
        db.rollback()
        _retry_or_raise(self, exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.message_tasks.relay_slack_to_kakao",
    queue="default",
)
def relay_slack_to_kakao(
    self,
    channel_id: str,
    text: str,
    slack_ts: str | None = None,
    slack_event_id: str | None = None,
) -> None:
    """슬랙 메시지를 카카오 상담톡으로 릴레이.

    1. 슬랙 channel_id → DB 역참조로 카카오 userKey 확보
    2. KakaoService로 메시지 발송
    3. Message_Log 기록
    """
    db = SessionLocal()
    channel_service = ChannelService()
    kakao_service = KakaoService(
        api_url=settings.KAKAO_API_URL,
        admin_key=settings.KAKAO_ADMIN_KEY,
    )

    try:
        user_key = channel_service.get_user_key_by_channel(db, channel_id)
        if not user_key:
            logger.warning(f"No kakao user_key found for slack channel {channel_id}, skipping")
            return

        # 차단된 사용자 확인
        from app.models.user_session import UserSession
        session = db.query(UserSession).filter(UserSession.kakao_user_key == user_key).first()
        if session and session.is_blocked:
            logger.warning(f"User {user_key} is blocked, skipping relay")
            return

        kakao_service.send_message(user_key=user_key, text=text)

        log = MessageLog(
            message_id=str(uuid.uuid4()),
            kakao_user_key=user_key,
            slack_channel_id=channel_id,
            slack_ts=slack_ts,
            direction=MessageDirection.SLACK_TO_KAKAO,
            payload_type=PayloadType.TEXT,
        )
        db.add(log)
        db.commit()

        logger.info(f"relay_slack_to_kakao done | user={user_key} channel={channel_id}")

    except Exception as exc:
        db.rollback()
        error_msg = str(exc)
        if any(code in error_msg for code in ["not_authed", "invalid_auth"]):
            logger.error(f"Non-retryable kakao error, giving up: {exc}")
            return
        _retry_or_raise(self, exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.message_tasks.relay_kakao_file_to_slack",
    queue="default",
)
def relay_kakao_file_to_slack(
    self,
    user_key: str,
    media_url: str,
    media_name: str,
    nickname: str = "",
    kakao_message_id: str | None = None,
) -> None:
    """카카오 미디어 파일을 슬랙으로 릴레이.

    1. 카카오 파일 URL에서 바이너리 다운로드
    2. 슬랙 3단계 파일 업로드 (getUploadURLExternal → POST → completeUpload)
    3. Message_Log 기록
    """
    db = SessionLocal()
    channel_service = ChannelService()
    slack_service = SlackService()
    file_service = FileService()

    try:
        channel_service.upsert_user_session(db, user_key)
        channel_id = channel_service.get_channel_id(db, user_key)

        if not channel_id:
            result = slack_service.create_channel(user_key)
            channel_id = result["channel_id"]
            channel_service.save_channel_mapping(db, user_key, channel_id, result["channel_name"])

        # 파일 다운로드
        data, mimetype = file_service.download(media_url)
        filename = media_name or f"kakao_file_{uuid.uuid4().hex[:8]}"
        title = f"[{nickname or user_key[:8]}] {filename}"

        # 슬랙 파일 업로드
        slack_service.upload_file(
            channel_id=channel_id,
            data=data,
            filename=filename,
            mimetype=mimetype,
            title=title,
        )

        log = MessageLog(
            message_id=str(uuid.uuid4()),
            kakao_user_key=user_key,
            kakao_message_id=kakao_message_id,
            slack_channel_id=channel_id,
            direction=MessageDirection.KAKAO_TO_SLACK,
            payload_type=PayloadType.IMAGE if file_service.is_image(mimetype) else PayloadType.FILE,
        )
        db.add(log)
        db.commit()
        logger.info(f"relay_kakao_file_to_slack done | user={user_key} file={filename}")

    except Exception as exc:
        db.rollback()
        _retry_or_raise(self, exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.message_tasks.relay_slack_file_to_kakao",
    queue="default",
)
def relay_slack_file_to_kakao(
    self,
    channel_id: str,
    file_url: str,
    filename: str,
    mimetype: str,
    slack_ts: str | None = None,
) -> None:
    """슬랙 파일을 카카오로 릴레이.

    이미지: Pillow로 500KB 이하 압축 → 카카오 이미지 API 전송
    비이미지/압축 불가: S3 업로드 후 다운로드 링크를 텍스트로 발송 (fallback)
    """
    db = SessionLocal()
    channel_service = ChannelService()
    file_service = FileService()
    s3_service = S3Service()
    kakao_service = KakaoService(
        api_url=settings.KAKAO_API_URL,
        admin_key=settings.KAKAO_ADMIN_KEY,
    )

    try:
        user_key = channel_service.get_user_key_by_channel(db, channel_id)
        if not user_key:
            logger.warning(f"No kakao user_key for slack channel {channel_id}, skipping")
            return

        from app.models.user_session import UserSession
        session = db.query(UserSession).filter(UserSession.kakao_user_key == user_key).first()
        if session and session.is_blocked:
            logger.warning(f"User {user_key} is blocked, skipping file relay")
            return

        # 슬랙 private URL 다운로드 (Bearer 인증)
        data, detected_mimetype = file_service.download_slack_file(file_url)
        effective_mimetype = detected_mimetype or mimetype

        payload_type = PayloadType.FILE
        sent_as_text = False

        if file_service.is_image(effective_mimetype):
            payload_type = PayloadType.IMAGE
            try:
                compressed, effective_mimetype = file_service.compress_image_for_kakao(
                    data, effective_mimetype
                )
                kakao_service.send_image(user_key=user_key, image_data=compressed, mimetype=effective_mimetype)
            except ValueError:
                # 압축 실패 → S3 fallback
                logger.warning(f"Image too large to compress, falling back to S3 for {user_key}")
                _send_via_s3(s3_service, kakao_service, user_key, data, filename, effective_mimetype)
                sent_as_text = True
        else:
            # 비이미지 파일 (동영상, PDF 등) → S3 fallback
            if s3_service.is_configured():
                _send_via_s3(s3_service, kakao_service, user_key, data, filename, effective_mimetype)
                sent_as_text = True
            else:
                logger.warning(f"S3 not configured, cannot send file {filename} to kakao {user_key}")
                kakao_service.send_message(
                    user_key=user_key,
                    text=f"[첨부파일] {filename} (파일 전송 불가 — S3 미설정)",
                )
                sent_as_text = True

        log = MessageLog(
            message_id=str(uuid.uuid4()),
            kakao_user_key=user_key,
            slack_channel_id=channel_id,
            slack_ts=slack_ts,
            direction=MessageDirection.SLACK_TO_KAKAO,
            payload_type=PayloadType.TEXT if sent_as_text else payload_type,
        )
        db.add(log)
        db.commit()
        logger.info(f"relay_slack_file_to_kakao done | user={user_key} file={filename}")

    except Exception as exc:
        db.rollback()
        _retry_or_raise(self, exc)
    finally:
        db.close()


def _send_via_s3(
    s3_service: S3Service,
    kakao_service: KakaoService,
    user_key: str,
    data: bytes,
    filename: str,
    mimetype: str,
) -> None:
    """S3에 파일 업로드 후 다운로드 링크를 카카오 텍스트 메시지로 발송."""
    url = s3_service.upload(data=data, filename=filename, mimetype=mimetype)
    kakao_service.send_message(
        user_key=user_key,
        text=f"[첨부파일] {filename}\n다운로드: {url}",
    )


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.message_tasks.notify_channel_blocked",
    queue="default",
)
def notify_channel_blocked(self, user_key: str, channel_id: str) -> None:
    """고객 차단 시 슬랙 채널에 알림 메시지 전송 후 아카이브."""
    slack_service = SlackService()
    db = SessionLocal()
    channel_service = ChannelService()
    try:
        slack_service.post_message(
            channel_id=channel_id,
            text=f":no_entry: 고객(userKey: `{user_key}`)이 카카오톡 채널을 차단했습니다. 더 이상 메시지를 발송할 수 없습니다.",
        )
        slack_service.archive_channel(channel_id)
        channel_service.mark_blocked(db, user_key)
        logger.info(f"Channel archived after block: {channel_id}")
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=2 ** self.request.retries, max_retries=MAX_RETRIES)
    finally:
        db.close()
