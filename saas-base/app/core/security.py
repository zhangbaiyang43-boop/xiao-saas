from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, Request
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(tenant_id: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(days=7))
    payload = {
        "sub": tenant_id,
        "tenant_id": tenant_id,
        "type": "merchant",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_customer_access_token(
    tenant_id: str,
    customer_id: int,
    openid: str = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(days=30))
    payload = {
        "sub": f"customer:{customer_id}",
        "tenant_id": tenant_id,
        "customer_id": customer_id,
        "type": "member",
        "role": "customer",
        "exp": expire,
    }
    if openid:
        payload["openid"] = openid
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> Optional[dict]:
    return verify_token(token)


async def get_current_user(request: Request) -> dict:
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="缺少或无效的登录凭证")
    return {
        "tenant_id": tenant_id,
        "user_id": getattr(request.state, "user_id", tenant_id),
        "customer_id": getattr(request.state, "customer_id", None),
        "type": token_type,
    }


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
