from datetime import datetime
from typing import Any, TypeAlias

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.super_admin import _verify_super_token
from app.core.database import get_db
from app.core.response import RespVo, error_response, success_response
from app.services.billing_service import BillingService, serialize_invoice


ApiResponse: TypeAlias = RespVo[Any]

router = APIRouter(
    prefix="/api/super/billing",
    tags=["平台SaaS账单"],
    dependencies=[Depends(_verify_super_token)],
)


class SuperBillingInvoiceCreateRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=32)
    charge_type: str
    description: str = ""
    amount_cents: int = Field(..., gt=0)
    currency: str = "CNY"
    expired_at: datetime | None = None
    metadata: dict[str, Any] | None = None


@router.post("/invoices", response_model=RespVo)
async def create_billing_invoice(
    body: SuperBillingInvoiceCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    service = BillingService(db)
    try:
        invoice = await service.create_invoice(
            tenant_id=body.tenant_id,
            charge_type=body.charge_type,
            description=body.description,
            amount_cents=body.amount_cents,
            currency=body.currency,
            expired_at=body.expired_at,
            metadata=body.metadata,
        )
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return success_response(data=serialize_invoice(invoice), msg="账单已创建")


@router.get("/invoices", response_model=RespVo)
async def list_billing_invoices(tenant_id: str | None = None, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    rows = await BillingService(db).list_invoices_for_super(tenant_id=tenant_id)
    return success_response(data=[serialize_invoice(row) for row in rows], msg="ok")


@router.get("/payment-config-status", response_model=RespVo)
async def get_billing_payment_config_status() -> ApiResponse:
    return success_response(data=BillingService.payment_config_status(), msg="ok")
