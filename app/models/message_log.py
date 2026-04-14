import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MessageDirection(str, enum.Enum):
    KAKAO_TO_SLACK = "KAKAO_TO_SLACK"
    SLACK_TO_KAKAO = "SLACK_TO_KAKAO"


class PayloadType(str, enum.Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    FILE = "FILE"
    VIDEO = "VIDEO"


class MessageLog(Base):
    __tablename__ = "message_log"

    message_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    kakao_user_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kakao_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection), nullable=False)
    payload_type: Mapped[PayloadType] = mapped_column(
        Enum(PayloadType), nullable=False, default=PayloadType.TEXT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
