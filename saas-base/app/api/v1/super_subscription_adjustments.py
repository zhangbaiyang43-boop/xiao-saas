import jwt
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.super_admin import _audit
from app.config import settings
from app.core.database import get_db
from app.core.response import RespVo, success_response
from app.schemas.subscription_adjustment import (
    SubscriptionAdjustmentCommitRequest,
    SubscriptionAdjustmentPreviewRequest,
)
from app.services.subscription_adjustment_service import (
    SubscriptionAdjustmentError,
    SubscriptionAdjustmentService,
)


router = APIRouter(prefix="/api/super", tags=["平台中控台-服务期调整"])


class SubscriptionAdjustmentAuthorizationError(Exception):
    def __init__(self, error_code: str, message: str, http_status: int):
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def _business_error(exc: SubscriptionAdjustmentError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=RespVo(
            code=exc.http_status,
            msg=exc.message,
            data={"error_code": exc.error_code},
        ).to_response(),
    )


async def subscription_adjustment_authorization_error_handler(
    _request: Request,
    exc: SubscriptionAdjustmentAuthorizationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=RespVo(
            code=exc.http_status,
            msg=exc.message,
            data={"error_code": exc.error_code},
        ).to_response(),
    )


def _verify_adjustment_super_token(
    x_super_token: str | None = Header(default=None, alias="X-Super-Token"),
) -> str:
    if not x_super_token:
        raise SubscriptionAdjustmentAuthorizationError("UNAUTHORIZED", "中控台鉴权失败", 401)
    try:
        payload = jwt.decode(
            x_super_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except Exception as exc:
        raise SubscriptionAdjustmentAuthorizationError("UNAUTHORIZED", "中控台鉴权失败", 401) from exc
    if payload.get("type") != "super_admin":
        raise SubscriptionAdjustmentAuthorizationError("FORBIDDEN", "无权执行中控台服务期调整", 403)
    return payload.get("sub", "")


@router.post(
    "/merchants/{tenant_id}/subscription-adjustments/preview",
    response_model=RespVo,
    dependencies=[Depends(_verify_adjustment_super_token)],
)
async def preview_subscription_adjustment(
    tenant_id: str,
    body: SubscriptionAdjustmentPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await SubscriptionAdjustmentService(db).preview(
            tenant_id,
            **body.model_dump(),
        )
    except SubscriptionAdjustmentError as exc:
        return _business_error(exc)
    return success_response(data=result, msg="预览成功")


@router.post(
    "/merchants/{tenant_id}/subscription-adjustments",
    response_model=RespVo,
)
async def commit_subscription_adjustment(
    tenant_id: str,
    request: Request,
    body: SubscriptionAdjustmentCommitRequest,
    _super_actor: str = Depends(_verify_adjustment_super_token),
    db: AsyncSession = Depends(get_db),
):
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    operator_ip = (forwarded or (request.client.host if request.client else "unknown"))[:45]
    payload = body.model_dump()
    payload["expected_subscription_id"] = int(body.expected_subscription_id)
    try:
        result = await SubscriptionAdjustmentService(db).commit(
            tenant_id,
            **payload,
            operator_type="SUPER_ADMIN",
            operator_id=None,
            operator_label="super_admin",
            operator_ip=operator_ip,
            request_id=getattr(request.state, "request_id", "unknown"),
        )
    except SubscriptionAdjustmentError as exc:
        return _business_error(exc)
    _audit(
        "subscription_adjustment_commit",
        request,
        tenant_id,
        detail=(
            f"adjustment_id={result['adjustment_id']} "
            f"subscription_id={result['subscription_id']} "
            f"operation={result['operation_type']} replay={result['idempotent_replay']}"
        ),
    )
    return success_response(data=result, msg="服务期调整已提交")


@router.get(
    "/merchants/{tenant_id}/subscription-adjustments",
    response_model=RespVo,
    dependencies=[Depends(_verify_adjustment_super_token)],
)
async def list_subscription_adjustments(
    tenant_id: str,
    limit: int = Query(default=20, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows = await SubscriptionAdjustmentService(db).list_history(tenant_id, limit=limit)
    except SubscriptionAdjustmentError as exc:
        return _business_error(exc)
    return success_response(data=rows, msg="ok")
