from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.lock import redis_lock
from app.core.pagination import build_page, normalize_pagination
from app.core.rate_limiter import tenant_limit
from app.core.response import RespVo, error_response, success_response
from app.services.anti_fraud_service import AntiFraudService
from app.services.verify_service import VerifyService

router = APIRouter(prefix="/api/v1", tags=["verify"])


class VerifyRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=1024, description="verify code")


class VerifyOperationRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255, description="operation reason")


async def run_verify(code: str, db: AsyncSession):
    service = VerifyService(db)
    result = await service.verify_coupon_with_result(code)
    if not result["success"]:
        return error_response(
            code=400,
            msg=result["message"],
            data={"reason": result["reason"], "coupon": result["coupon"]},
        )
    return success_response(data={"coupon": result["coupon"]}, msg="核销成功")


@router.post("/verify", response_model=RespVo)
@tenant_limit()
async def verify_coupon(request: Request, data: VerifyRequest, db: AsyncSession = Depends(get_db)):
    lock_key = f"verify:{data.code.strip().upper()}"
    tenant_id = getattr(request.state, "tenant_id", "unknown")
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    device_id = request.headers.get("x-device-id") or ip

    if not await AntiFraudService.allow_frequency(
        "merchant_verify",
        f"{tenant_id}:{device_id}",
        {"tenant_id": tenant_id, "device_id": device_id, "ip": ip},
    ):
        return error_response(code=429, msg="核销请求过于频繁，请稍后再试")

    try:
        async with redis_lock(lock_key, timeout=10) as acquired:
            if not acquired:
                return error_response(code=400, msg="操作过于频繁，请稍后再试")
            return await run_verify(data.code, db)
    except RuntimeError:
        return await run_verify(data.code, db)


@router.get("/verify/records", response_model=RespVo)
@tenant_limit()
async def list_verify_records(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    skip, limit = normalize_pagination(skip, limit)
    service = VerifyService(db)
    records = await service.list_verify_records(skip, limit)
    total = await service.count_verify_records()
    return success_response(data=build_page(records, total, skip, limit), msg="ok")


@router.post("/verify/{coupon_id}/revoke", response_model=RespVo)
@tenant_limit()
async def revoke_verify_record(
    request: Request,
    coupon_id: int,
    data: VerifyOperationRequest,
    db: AsyncSession = Depends(get_db),
):
    service = VerifyService(db)
    result = await service.revoke_verification(coupon_id, data.reason)
    if not result["success"]:
        return error_response(code=400, msg=result["message"], data=result)
    return success_response(data=result, msg=result["message"])


@router.post("/verify/{coupon_id}/abnormal", response_model=RespVo)
@tenant_limit()
async def mark_verify_record_abnormal(
    request: Request,
    coupon_id: int,
    data: VerifyOperationRequest,
    db: AsyncSession = Depends(get_db),
):
    service = VerifyService(db)
    result = await service.mark_abnormal(coupon_id, data.reason)
    if not result["success"]:
        return error_response(code=400, msg=result["message"], data=result)
    return success_response(data=result, msg=result["message"])
