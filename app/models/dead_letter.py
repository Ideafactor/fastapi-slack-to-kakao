import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DLQStatus(str, enum.Enum):
    PENDING = "PENDING"      # 재처리 대기
    REPLAYED = "REPLAYED"    # 재처리 완료
    DISCARDED = "DISCARDED"  # 폐기


class DeadLetter(Base):
    """최대 재시도 횟수 초과 후 실패한 Celery 태스크 보관소."""

    __tablename__ = "dead_letter"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_kwargs: Mapped[str] = mapped_column(Text, nullable=False)   # JSON 직렬화
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[DLQStatus] = mapped_column(
        Enum(DLQStatus), nullable=False, default=DLQStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
