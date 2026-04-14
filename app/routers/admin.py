import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dead_letter import DLQStatus
from app.services.dlq_service import DLQService
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/admin", tags=["admin"])


class DLQEntryResponse(BaseModel):
    id: str
    task_name: str
    task_kwargs: dict
    error_message: str | None
    retry_count: int
    status: DLQStatus
    created_at: str
    replayed_at: str | None

    model_config = {"from_attributes": True}


class ReplayResponse(BaseModel):
    replayed: int
    task_ids: list[str]


def _build_response(entry) -> DLQEntryResponse:
    return DLQEntryResponse(
        id=entry.id,
        task_name=entry.task_name,
        task_kwargs=json.loads(entry.task_kwargs),
        error_message=entry.error_message,
        retry_count=entry.retry_count,
        status=entry.status,
        created_at=entry.created_at.isoformat(),
        replayed_at=entry.replayed_at.isoformat() if entry.replayed_at else None,
    )


@router.get("/dlq", response_model=list[DLQEntryResponse])
def list_dlq(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[DLQEntryResponse]:
    """DLQ에 보관된 실패 태스크 목록 조회."""
    entries = DLQService().list_pending(db, limit=limit, offset=offset)
    return [_build_response(e) for e in entries]


@router.post("/dlq/{dlq_id}/replay", response_model=ReplayResponse)
def replay_one(dlq_id: str, db: Session = Depends(get_db)) -> ReplayResponse:
    """DLQ의 특정 항목을 큐에 다시 넣어 재처리."""
    svc = DLQService()
    entry = svc.get(db, dlq_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DLQ entry not found")
    if entry.status != DLQStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot replay entry with status {entry.status}",
        )

    kwargs = json.loads(entry.task_kwargs)
    task_result = celery_app.send_task(entry.task_name, kwargs=kwargs)
    svc.mark_replayed(db, dlq_id)
    logger.info(f"[DLQ] Replayed {dlq_id} → task_id={task_result.id}")
    return ReplayResponse(replayed=1, task_ids=[task_result.id])


@router.post("/dlq/replay-all", response_model=ReplayResponse)
def replay_all(db: Session = Depends(get_db)) -> ReplayResponse:
    """DLQ PENDING 항목 전체를 재처리."""
    svc = DLQService()
    entries = svc.list_pending(db, limit=200)
    task_ids = []
    for entry in entries:
        kwargs = json.loads(entry.task_kwargs)
        result = celery_app.send_task(entry.task_name, kwargs=kwargs)
        svc.mark_replayed(db, entry.id)
        task_ids.append(result.id)

    logger.info(f"[DLQ] Replayed all: {len(task_ids)} tasks")
    return ReplayResponse(replayed=len(task_ids), task_ids=task_ids)


@router.delete("/dlq/{dlq_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard(dlq_id: str, db: Session = Depends(get_db)) -> None:
    """DLQ 항목을 폐기(DISCARDED) 처리."""
    svc = DLQService()
    entry = svc.get(db, dlq_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DLQ entry not found")
    svc.mark_discarded(db, dlq_id)
    logger.info(f"[DLQ] Discarded {dlq_id}")
