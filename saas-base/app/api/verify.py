"""
已废弃 — 此路由文件不再注册到应用。
核销请使用 /api/v1/verify（见 app/api/v1/verify.py）。
保留此文件仅为防止 app/api/__init__.py 的历史 import 报 ImportError。
"""
from fastapi import APIRouter
from app.core.response import error_response

router = APIRouter(prefix="/api", tags=["deprecated"])


@router.post("/verify")
async def verify_coupon_deprecated():
    """此接口已停用，请使用 /api/v1/verify。"""
    return error_response(code=410, msg="此接口已停用，请使用 /api/v1/verify")
