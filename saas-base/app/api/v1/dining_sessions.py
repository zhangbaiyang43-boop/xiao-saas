from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.response import error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.tenant import Tenant
from app.services.dining_session_service import DiningSessionService


router = APIRouter(prefix="/api/v1/dining-sessions", tags=["桌台会话"])


class DiningSessionResolveIn(BaseModel):
    tenant_id: str
    table_no: str
    client_id: Optional[str] = None
    participant_token: Optional[str] = None


class DiningParticipantBindIn(BaseModel):
    tenant_id: str
    participant_token: str


class DiningCheckoutRequestIn(BaseModel):
    tenant_id: str
    dining_session_id: str
    participant_token: Optional[str] = None
    requested: bool = True


@router.get("/active")
async def list_active_dining_sessions(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Staff assisted-add STEP1: currently OPEN dining tables for this tenant."""
    if getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    tenant_id = getattr(request.state, "tenant_id", None) or TenantContext.get_tenant_id()
    if not tenant_id:
        return error_response(code=400, msg="缺少门店")
    TenantContext.set_tenant_id(tenant_id)

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    payment_mode = (getattr(tenant, "payment_mode", None) or "prepay") if tenant else "prepay"

    sessions = await DiningSessionService(db).list_active_sessions_for_staff(tenant_id)
    assisted_allowed = payment_mode in ("postpay", "table_account")
    return success_response(
        data={
            "payment_mode": payment_mode,
            "assisted_add_allowed": assisted_allowed,
            "sessions": sessions,
            "prepay_blocked_msg": None
            if assisted_allowed
            else "当前收款模式请由顾客扫码加单",
        },
        msg="ok",
    )


@router.post("/resolve")
async def resolve_dining_session(
    body: DiningSessionResolveIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = (body.tenant_id or "").strip()
    table_no = (body.table_no or "").strip()
    if not tenant_id or not table_no:
        return error_response(code=400, msg="缺少门店或桌号")

    TenantContext.set_tenant_id(tenant_id)
    customer_id = getattr(request.state, "customer_id", None)
    openid = getattr(request.state, "openid", None)
    try:
        data = await DiningSessionService(db).resolve_session(
            tenant_id=tenant_id,
            table_no=table_no,
            client_id=body.client_id,
            participant_token=body.participant_token,
            customer_id=int(customer_id) if customer_id else None,
            openid=openid,
        )
        await db.commit()
        return success_response(data=data, msg="ok")
    except ValueError as exc:
        await db.rollback()
        return error_response(code=400, msg=str(exc))


@router.get("/current/orders")
async def list_current_dining_orders(
    request: Request,
    tenant_id: str,
    dining_session_id: str,
    participant_token: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = (tenant_id or "").strip()
    if not tenant_id or not dining_session_id:
        return error_response(code=400, msg="缺少门店或会话")
    customer_id = getattr(request.state, "customer_id", None)
    if not participant_token and not customer_id:
        # 409 而不是 401：这是"没带本桌匿名身份"，跟"会员登录过期"是两码事——
        # 401/403 在这个项目里全局约定代表"需要重新登录"，客户端的通用拦截器会把它们
        # 当成会员登录失效处理，误导顾客去做微信授权。参见 orders.py 里 participant
        # 校验失败同样改用 409 的注释。
        return error_response(code=409, msg="缺少本桌身份，请重新扫码")

    service = DiningSessionService(db)
    result = await service.list_session_orders(
        tenant_id=tenant_id,
        dining_session_id=int(dining_session_id),
        participant_token=participant_token,
        customer_id=int(customer_id) if customer_id else None,
    )
    session_status = await service.get_session_status(tenant_id=tenant_id, dining_session_id=int(dining_session_id))
    checkout_requested_at = await service.get_checkout_requested_at(tenant_id=tenant_id, dining_session_id=int(dining_session_id))
    closed_at = await service.get_closed_at(tenant_id=tenant_id, dining_session_id=int(dining_session_id))
    return success_response(
        data={
            "orders": result["orders"],
            "table_total": result["table_total"],
            "item_count": result["item_count"],
            "participant_count": result.get("participant_count", 0),
            "identity_mismatch": result.get("identity_mismatch", False),
            "session_status": session_status,
            "closed": session_status in ("CLOSED", "EXPIRED"),
            "checkout_requested_at": checkout_requested_at.isoformat() if checkout_requested_at else None,
            # 真正的结账时间，供顾客端"查看结账详情"展示——区别于订单的下单时间
            "closed_at": closed_at.isoformat() if closed_at else None,
        },
        msg="ok",
    )


@router.post("/checkout-request")
async def request_table_checkout(
    body: DiningCheckoutRequestIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """顾客端"吃好了，去结账"的入口：只记录一次请求时间，真正的结账动作仍由商家在后台完成，
    但商家后台从此能看到"这一桌顾客已经在等结账"，不用再靠巡台去发现。"""
    tenant_id = (body.tenant_id or "").strip()
    if not tenant_id or not body.dining_session_id:
        return error_response(code=400, msg="缺少门店或会话")
    customer_id = getattr(request.state, "customer_id", None)
    if not body.participant_token and not customer_id:
        return error_response(code=409, msg="缺少本桌身份，请重新扫码")

    TenantContext.set_tenant_id(tenant_id)
    result = await DiningSessionService(db).set_checkout_request(
        tenant_id=tenant_id,
        dining_session_id=int(body.dining_session_id),
        requested=body.requested,
        participant_token=body.participant_token,
        customer_id=int(customer_id) if customer_id else None,
    )
    if result is None:
        return error_response(code=404, msg="本桌会话不存在或已结束")
    await db.commit()
    return success_response(data=result, msg="ok")


@router.post("/participants/bind")
async def bind_dining_participant(
    body: DiningParticipantBindIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    customer_id = getattr(request.state, "customer_id", None)
    openid = getattr(request.state, "openid", None)
    if not customer_id:
        return error_response(code=401, msg="请先登录")
    tenant_id = (body.tenant_id or "").strip()
    participant_token = (body.participant_token or "").strip()
    if not tenant_id or not participant_token:
        return error_response(code=400, msg="缺少本桌身份")

    participant = await DiningSessionService(db).bind_participant_to_customer(
        tenant_id=tenant_id,
        participant_token=participant_token,
        customer_id=int(customer_id),
        openid=openid,
    )
    if not participant:
        return error_response(code=404, msg="本桌身份不存在")
    await db.commit()
    return success_response(data={"participant_id": str(participant.id)}, msg="ok")

