import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dead_letter import DeadLetter, DLQStatus


class DLQService:
    def push(
        self,
        db: Session,
        task_name: str,
        task_kwargs: dict,
        error_message: str,
        retry_count: int,
    ) -> DeadLetter:
        """실패한 태스크를 DLQ에 저장."""
        entry = DeadLetter(
            task_name=task_name,
            task_kwargs=json.dumps(task_kwargs, ensure_ascii=False),
            error_message=error_message,
            retry_count=retry_count,
            status=DLQStatus.PENDING,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        logger.error(
            f"[DLQ] Task pushed | task={task_name} retries={retry_count} error={error_message[:120]}"
        )
        return entry

    def list_pending(self, db: Session, limit: int = 50, offset: int = 0) -> list[DeadLetter]:
        return (
            db.query(DeadLetter)
            .filter(DeadLetter.status == DLQStatus.PENDING)
            .order_by(DeadLetter.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get(self, db: Session, dlq_id: str) -> DeadLetter | None:
        return db.query(DeadLetter).filter(DeadLetter.id == dlq_id).first()

    def mark_replayed(self, db: Session, dlq_id: str) -> None:
        db.query(DeadLetter).filter(DeadLetter.id == dlq_id).update(
            {
                "status": DLQStatus.REPLAYED,
                "replayed_at": datetime.now(timezone.utc),
            }
        )
        db.commit()

    def mark_discarded(self, db: Session, dlq_id: str) -> None:
        db.query(DeadLetter).filter(DeadLetter.id == dlq_id).update(
            {"status": DLQStatus.DISCARDED}
        )
        db.commit()
