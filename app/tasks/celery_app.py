from celery import Celery

from app.config import settings

celery_app = Celery(
    "fastapi_slack",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.message_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    # 재시도 실패한 태스크를 DLQ 큐로 이동
    task_routes={
        "app.tasks.message_tasks.*": {"queue": "default"},
    },
    task_default_queue="default",
    # 최대 재시도 횟수 초과 시 dead_letter 큐로
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
