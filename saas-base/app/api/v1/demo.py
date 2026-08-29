from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import RespVo, error_response, success_response
from app.services.demo_session_service import (
    DemoActionDeniedError,
    DemoInvalidLaunchError,
    DemoOrderNotFoundError,
    DemoPoolFullError,
    DemoRateLimitedError,
    DemoSessionService,
    DemoUnavailableError,
)


router = APIRouter(prefix="/api/v1/demo", tags=["体验演示"])


class DemoStartIn(BaseModel):
    launchCode: str


class DemoStatusIn(BaseModel):
    status: str


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_response(code=status_code, msg=message).to_response(),
    )


@router.post("/sessions/start", response_model=RespVo)
async def start_demo_session(
    body: DemoStartIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = DemoSessionService(db)
    try:
        data = await service.start_session(
            launch_code=body.launchCode,
            client_ip=request.client.host if request.client else "unknown",
        )
        return success_response(data=data, msg="success")
    except DemoInvalidLaunchError:
        return _error_response(403, "体验入口无效或已过期")
    except (DemoRateLimitedError, DemoPoolFullError):
        return _error_response(429, "体验人数较多，请稍后再试")
    except DemoUnavailableError:
        return _error_response(503, "体验服务暂不可用")


@router.get("/session", response_model=RespVo)
async def get_demo_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = DemoSessionService(db)
    try:
        data = await service.get_session_snapshot(
            tenant_id=request.state.tenant_id,
            dining_session_id=request.state.demo_session_id,
        )
        return success_response(data=data, msg="success")
    except DemoOrderNotFoundError:
        return _error_response(404, "体验会话不存在")


@router.patch("/orders/{order_id}/status", response_model=RespVo)
async def update_demo_order_status(
    order_id: int,
    body: DemoStatusIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = DemoSessionService(db)
    try:
        data = await service.update_order_status(
            tenant_id=request.state.tenant_id,
            dining_session_id=request.state.demo_session_id,
            order_id=order_id,
            status=body.status,
        )
        return success_response(data=data, msg="success")
    except DemoOrderNotFoundError:
        return _error_response(404, "订单不存在")
    except DemoActionDeniedError:
        return _error_response(409, "当前订单状态不能执行此操作")


@router.post("/orders/{order_id}/serve", response_model=RespVo)
async def serve_demo_order(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = DemoSessionService(db)
    try:
        data = await service.serve_order(
            tenant_id=request.state.tenant_id,
            dining_session_id=request.state.demo_session_id,
            order_id=order_id,
        )
        return success_response(data=data, msg="success")
    except DemoOrderNotFoundError:
        return _error_response(404, "订单不存在")
    except DemoActionDeniedError:
        return _error_response(409, "当前订单状态不能执行此操作")
