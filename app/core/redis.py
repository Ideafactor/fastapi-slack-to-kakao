import redis

from app.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def is_duplicate_event(event_id: str, ttl_seconds: int = 300) -> bool:
    """이벤트 ID가 이미 처리됐는지 확인. 처음이면 False 반환 후 Redis에 등록."""
    r = get_redis()
    key = f"event:seen:{event_id}"
    # SET NX (Not eXists) — 이미 있으면 None 반환
    result = r.set(key, "1", ex=ttl_seconds, nx=True)
    return result is None  # None이면 이미 존재 → 중복
