from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import error_response, success_response
from app.core.tenant_context import TenantContext
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
        return error_response(code=401, msg="缺少本桌身份")

    service = DiningSessionService(db)
    orders = await service.list_session_orders(
        tenant_id=tenant_id,
        dining_session_id=int(dining_session_id),
        participant_token=participant_token,
        customer_id=int(customer_id) if customer_id else None,
    )
    session_status = await service.get_session_status(tenant_id=tenant_id, dining_session_id=int(dining_session_id))
    return success_response(
        data={
            "orders": orders,
            "session_status": session_status,
            "closed": session_status in ("CLOSED", "EXPIRED"),
        },
        msg="ok",
    )


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

