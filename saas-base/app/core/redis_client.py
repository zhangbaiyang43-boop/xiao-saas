import redis.asyncio as redis

from app.config import settings

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
)


async def get_redis():
    if not settings.REDIS_ENABLED:
        return None
    return redis_client
