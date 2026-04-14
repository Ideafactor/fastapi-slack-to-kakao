from loguru import logger
from sqlalchemy.orm import Session

from app.models.channel_mapping import ChannelMapping, ChannelStatus
from app.models.user_session import UserSession


class ChannelService:
    def get_channel_id(self, db: Session, user_key: str) -> str | None:
        """DB에서 userKey에 매핑된 슬랙 채널 ID 조회."""
        mapping = (
            db.query(ChannelMapping)
            .filter(
                ChannelMapping.kakao_user_key == user_key,
                ChannelMapping.status == ChannelStatus.ACTIVE,
            )
            .first()
        )
        return mapping.slack_channel_id if mapping else None

    def save_channel_mapping(
        self, db: Session, user_key: str, channel_id: str, channel_name: str
    ) -> ChannelMapping:
        """채널 매핑을 DB에 저장."""
        mapping = ChannelMapping(
            kakao_user_key=user_key,
            slack_channel_id=channel_id,
            channel_name=channel_name,
            status=ChannelStatus.ACTIVE,
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)
        logger.info(f"Channel mapping saved: {user_key} -> {channel_id}")
        return mapping

    def upsert_user_session(self, db: Session, user_key: str) -> None:
        """고객 세션 최신화 (없으면 생성)."""
        session = db.query(UserSession).filter(UserSession.kakao_user_key == user_key).first()
        if session:
            from sqlalchemy import func
            db.query(UserSession).filter(UserSession.kakao_user_key == user_key).update(
                {"last_active_at": func.now()}
            )
        else:
            session = UserSession(kakao_user_key=user_key)
            db.add(session)
        db.commit()

    def mark_blocked(self, db: Session, user_key: str) -> None:
        """고객 차단 상태 처리."""
        db.query(UserSession).filter(UserSession.kakao_user_key == user_key).update(
            {"is_blocked": True}
        )
        db.query(ChannelMapping).filter(ChannelMapping.kakao_user_key == user_key).update(
            {"status": ChannelStatus.ARCHIVED}
        )
        db.commit()
        logger.info(f"User blocked and channel archived: {user_key}")

    def get_user_key_by_channel(self, db: Session, channel_id: str) -> str | None:
        """슬랙 채널 ID → 카카오 userKey 역참조."""
        mapping = (
            db.query(ChannelMapping)
            .filter(ChannelMapping.slack_channel_id == channel_id)
            .first()
        )
        return mapping.kakao_user_key if mapping else None
