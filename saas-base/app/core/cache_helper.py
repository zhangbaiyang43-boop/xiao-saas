import json
from typing import Any, Optional, Callable
from functools import wraps
from fastapi.encoders import jsonable_encoder
from app.core.redis_client import redis_client
from app.core.tenant_context import TenantContext
from app.config import settings
from app.core.logger import logger

CACHE_PREFIX = settings.CACHE_PREFIX
DEFAULT_TTL = settings.CACHE_DEFAULT_TTL

async def get_cache(key: str) -> Optional[Any]:
    if not settings.REDIS_ENABLED:
        return None
    full_key = f"{CACHE_PREFIX}{key}"
    try:
        value = await redis_client.get(full_key)
    except Exception as exc:
        logger.warning(f"Redis cache read skipped: {exc}")
        return None
    if value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return None

async def set_cache(key: str, value: Any, ttl: int = DEFAULT_TTL):
    if not settings.REDIS_ENABLED:
        return
    full_key = f"{CACHE_PREFIX}{key}"
    try:
        serialized = json.dumps(jsonable_encoder(value), ensure_ascii=False)
        await redis_client.setex(full_key, ttl, serialized)
    except Exception as exc:
        logger.warning(f"Redis cache write skipped: {exc}")

async def delete_cache(key: str):
    if not settings.REDIS_ENABLED:
        return
    full_key = f"{CACHE_PREFIX}{key}"
    try:
        await redis_client.delete(full_key)
    except Exception as exc:
        logger.warning(f"Redis cache delete skipped: {exc}")

async def clear_cache_pattern(pattern: str):
    if not settings.REDIS_ENABLED:
        return
    full_pattern = f"{CACHE_PREFIX}{pattern}"
    try:
        keys = await redis_client.keys(full_pattern)
        if keys:
            await redis_client.delete(*keys)
    except Exception as exc:
        logger.warning(f"Redis cache clear skipped: {exc}")

def cache_result(key_prefix: str, ttl: int = DEFAULT_TTL):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tenant_id = TenantContext.get_current_tenant_id()
            key_suffix = "_".join(str(arg) for arg in args[1:])
            if kwargs:
                key_suffix += "_" + "_".join(f"{k}={v}" for k, v in kwargs.items())
            
            cache_key = f"{key_prefix}:{tenant_id}:{func.__name__}:{key_suffix}" if tenant_id else f"{key_prefix}:{func.__name__}:{key_suffix}"
            
            cached = await get_cache(cache_key)
            if cached is not None:
                return cached
            
            result = await func(*args, **kwargs)
            
            await set_cache(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator
