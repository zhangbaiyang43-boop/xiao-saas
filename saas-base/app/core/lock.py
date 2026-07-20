import asyncio
import uuid
from contextlib import asynccontextmanager

from app.config import settings
from app.core.logger import logger
from app.core.redis_client import redis_client

LOCK_PREFIX = "lock:"
DEFAULT_TIMEOUT = settings.LOCK_DEFAULT_TIMEOUT
RETRY_DELAY = settings.LOCK_RETRY_DELAY / 1000


@asynccontextmanager
async def redis_lock(key: str, timeout: int = DEFAULT_TIMEOUT):
    lock_key = f"{LOCK_PREFIX}{key}"
    lock_value = str(uuid.uuid4())
    acquired = False

    if not settings.REDIS_ENABLED:
        raise RuntimeError("Redis is unavailable, cannot acquire distributed lock")

    try:
        try:
            result = await redis_client.set(lock_key, lock_value, nx=True, ex=timeout)
        except Exception as exc:
            logger.error(f"Redis lock unavailable: {exc}")
            raise RuntimeError("Redis is unavailable, cannot acquire distributed lock") from exc
        if result:
            acquired = True
            yield acquired
        else:
            yield acquired
    finally:
        if acquired:
            try:
                current_value = await redis_client.get(lock_key)
                if current_value == lock_value:
                    await redis_client.delete(lock_key)
            except Exception as exc:
                logger.error(f"Redis lock release failed: {exc}")


async def try_acquire_lock(key: str, timeout: int = DEFAULT_TIMEOUT, max_retries: int = 3) -> bool:
    if not settings.REDIS_ENABLED:
        return False

    lock_key = f"{LOCK_PREFIX}{key}"
    lock_value = str(uuid.uuid4())

    for _ in range(max_retries):
        result = await redis_client.set(lock_key, lock_value, nx=True, ex=timeout)
        if result:
            return True
        await asyncio.sleep(RETRY_DELAY)

    return False


async def release_lock(key: str, lock_value: str) -> bool:
    if not settings.REDIS_ENABLED:
        return False

    lock_key = f"{LOCK_PREFIX}{key}"
    current_value = await redis_client.get(lock_key)
    if current_value == lock_value:
        await redis_client.delete(lock_key)
        return True
    return False
