import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChannelStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ChannelMapping(Base):
    __tablename__ = "channel_mapping"

    kakao_user_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    slack_channel_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus), nullable=False, default=ChannelStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
