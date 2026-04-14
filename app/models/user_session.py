from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSession(Base):
    __tablename__ = "user_session"

    kakao_user_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
