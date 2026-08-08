"""Staff bind mini-program code generation — reuses WechatService access_token cache."""

from __future__ import annotations

import base64

from app.config import settings
from app.core.logger import logger
from app.services.staff_miniprogram_provider import staff_miniprogram_mock_allowed
from app.services.wechat_service import WechatService

# 1x1 PNG for local/dev when WeChat API unavailable and mock allowed.
_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def generate_staff_bind_wxacode(scene: str) -> bytes:
    page = (settings.STAFF_MP_BIND_PAGE or "subpkg-staff/pages/staff-bind").strip().lstrip("/")
    env_version = settings.STAFF_MP_WXACODE_ENV_VERSION or "release"
    wechat = WechatService()
    try:
        return await wechat.get_wxacode_unlimit(scene=scene, page=page, env_version=env_version)
    except Exception:
        logger.warning("staff_mp_wxacode_failed")
        if staff_miniprogram_mock_allowed():
            return _PLACEHOLDER_PNG
        raise
