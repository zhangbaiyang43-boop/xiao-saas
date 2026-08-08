"""Neutral staff_device Cookie helpers (HTTP cookie only; no identity providers)."""

from __future__ import annotations

from fastapi import Request, Response

from app.config import settings


def cookie_name() -> str:
    return settings.STAFF_DEVICE_COOKIE_NAME or "staff_device"


def cookie_path() -> str:
    return settings.STAFF_DEVICE_COOKIE_PATH or "/api"


def cookie_secure() -> bool:
    env = (settings.APP_ENV or "").strip().lower()
    return env in ("production", "prod")


def set_device_cookie(response: Response, credential: str) -> None:
    if not settings.STAFF_DEVICE_COOKIE_ENABLED or not credential:
        return
    max_age = max(1, int(settings.STAFF_TRUST_DEVICE_DAYS or 30)) * 86400
    response.set_cookie(
        key=cookie_name(),
        value=credential,
        max_age=max_age,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path=cookie_path(),
    )


def clear_device_cookie(response: Response) -> None:
    # Clear configured path; also clear legacy Path=/ from earlier builds.
    for path in {cookie_path(), "/"}:
        response.delete_cookie(key=cookie_name(), path=path)


def read_device_credential(request: Request, body_cred: str | None) -> str | None:
    """Cookie mode and JS credential mode are mutually exclusive."""
    if settings.STAFF_DEVICE_COOKIE_ENABLED:
        cookie = request.cookies.get(cookie_name())
        return cookie.strip() if cookie else None
    if body_cred:
        return body_cred.strip()
    return None


def public_auth_payload(result: dict) -> dict:
    """Strip long-lived device secret (and internal keys) from JSON when Cookie mode is on."""
    data = {k: v for k, v in result.items() if k not in ("ok", "account")}
    if settings.STAFF_DEVICE_COOKIE_ENABLED:
        data.pop("device_credential", None)
    return data


def deliver_device_credential(response: Response, result: dict) -> dict:
    cred = result.get("device_credential")
    if settings.STAFF_DEVICE_COOKIE_ENABLED:
        if cred:
            set_device_cookie(response, cred)
        # Never put secret in JSON when cookie mode is configured — no silent fallback.
        return public_auth_payload(result)
    return public_auth_payload(result)
