from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, Request
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(
    tenant_id: str,
    expires_delta: Optional[timedelta] = None,
    *,
    role: str = "owner",
    account_id: Optional[int] = None,
) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(days=7))
    payload = {
        "sub": str(account_id) if account_id else tenant_id,
        "tenant_id": tenant_id,
        "type": "merchant",
        "role": role or "owner",
        "exp": expire,
    }
    if account_id is not None:
        payload["account_id"] = int(account_id)
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


def create_demo_launch_code(expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (
        expires_delta or timedelta(days=settings.DEMO_LAUNCH_DAYS)
    )
    return jwt.encode(
        {"sub": "demo-launch", "type": "demo_launch", "exp": expire},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_demo_launch_code(token: str) -> Optional[dict]:
    payload = verify_token(token)
    if not payload or payload.get("type") != "demo_launch":
        return None
    return payload


def create_demo_session_token(
    *,
    tenant_id: str,
    dining_session_id: str,
    table_no: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.DEMO_SESSION_MINUTES)
    )
    return jwt.encode(
        {
            "sub": f"demo-session:{dining_session_id}",
            "tenant_id": tenant_id,
            "dining_session_id": str(dining_session_id),
            "table_no": table_no,
            "type": "demo_merchant",
            "scope": "demo_order_fulfillment",
            "exp": expire,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_demo_session_token(token: str) -> Optional[dict]:
    payload = verify_token(token)
    if not payload or payload.get("type") != "demo_merchant":
        return None
    if payload.get("scope") != "demo_order_fulfillment":
        return None
    if not payload.get("tenant_id") or not payload.get("dining_session_id"):
        return None
    return payload


def create_channel_partner_access_token(
    partner_id: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(days=7))
    payload = {
        "sub": f"channel_partner:{partner_id}",
        "type": "channel_partner",
        "partner_id": str(partner_id),
        "role": "channel_partner",
        "exp": expire,
    }
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
