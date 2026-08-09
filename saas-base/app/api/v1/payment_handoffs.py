from __future__ import annotations

import base64
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.orders import WxPayBody
from app.core.database import get_db
from app.core.permissions import ROLE_OWNER, parse_staff_role
from app.core.response import error_response, success_response
from app.services.order_payment_service import OrderPaymentService
from app.services.payment_handoff_service import HANDOFF_PAGE, PaymentHandoffService
from app.services.wechat_service import WechatService

router = APIRouter(prefix="/api/v1/payment-handoffs", tags=["支付交接"])


class HandoffClaimBody(BaseModel):
    token: Optional[str] = None


class HandoffPayBody(BaseModel):
    js_code: Optional[str] = None


def _staff_context(request: Request) -> tuple[str | None, int | None, str | None]:
    if getattr(request.state, "token_type", None) != "merchant":
        return None, None, None
    tenant_id = getattr(request.state, "tenant_id", None)
    account_id = getattr(request.state, "account_id", None)
    role = parse_staff_role(getattr(request.state, "role", None)) or ROLE_OWNER
    return tenant_id, int(account_id) if account_id is not None else None, role


@router.post("/orders/{order_id}")
async def create_payment_handoff(order_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, account_id, role = _staff_context(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    try:
        data = await PaymentHandoffService(db).create_for_order(
            tenant_id=str(tenant_id),
            order_id=int(order_id),
            actor_account_id=account_id,
            actor_role=role,
        )
        try:
            qr_bytes = await WechatService().get_wxacode_unlimit(
                scene=data["scene"],
                page=HANDOFF_PAGE,
            )
            data["qr_image"] = "data:image/png;base64," + base64.b64encode(qr_bytes).decode("ascii")
        except Exception as exc:
            data["qr_error"] = str(exc)
        await db.commit()
        return success_response(data=data, msg="ok")
    except ValueError as exc:
        await db.rollback()
        return error_response(code=400, msg=str(exc))


@router.get("/orders/{order_id}")
async def get_order_handoff(order_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, _, _ = _staff_context(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    try:
        data = await PaymentHandoffService(db).resolve_latest_for_order(
            tenant_id=str(tenant_id),
            order_id=int(order_id),
        )
        await db.commit()
        if data is None:
            return error_response(code=404, msg="支付二维码不存在")
        return success_response(data=data, msg="ok")
    except ValueError as exc:
        await db.rollback()
        return error_response(code=400, msg=str(exc))


@router.get("/{token}")
async def resolve_payment_handoff(token: str, db: AsyncSession = Depends(get_db)):
    try:
        data = await PaymentHandoffService(db).resolve(token)
        await db.commit()
        return success_response(data=data, msg="ok")
    except ValueError as exc:
        await db.rollback()
        return error_response(code=404, msg=str(exc))


@router.post("/{token}/claim")
async def claim_payment_handoff(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        return error_response(code=401, msg="请先登录")
    try:
        data = await PaymentHandoffService(db).claim(
            token=token,
            customer_id=int(customer_id),
            openid=getattr(request.state, "openid", None),
        )
        await db.commit()
        return success_response(data=data, msg="ok")
    except ValueError as exc:
        await db.rollback()
        return error_response(code=400, msg=str(exc))


@router.post("/{token}/pay")
async def pay_payment_handoff(
    token: str,
    body: HandoffPayBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        return error_response(code=401, msg="请先登录")
    try:
        data = await PaymentHandoffService(db).claim(
            token=token,
            customer_id=int(customer_id),
            openid=getattr(request.state, "openid", None),
        )
        return await OrderPaymentService(db).create_wxpay_order(
            str(data["order_id"]),
            WxPayBody(js_code=body.js_code, participant_token=None),
            request,
        )
    except ValueError as exc:
        await db.rollback()
        return error_response(code=400, msg=str(exc))
