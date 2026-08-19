from datetime import datetime
from typing import Any, TypeAlias

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.super_admin import _verify_super_token
from app.core.database import get_db
from app.core.response import RespVo, error_response, success_response
from app.services.billing_service import (
    BillingService,
    MANUAL_REVIEW_WAITING_CONFIRMATION,
    ManualPaymentStateError,
    serialize_invoice,
    serialize_payment,
)


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


@router.get("/manual-payment-config-status", response_model=RespVo)
async def get_manual_payment_config_status() -> ApiResponse:
    return success_response(data=BillingService.manual_payment_config_status(), msg="ok")


class ManualPaymentReviewRequest(BaseModel):
    # F1G-CM Phase 12/26: the ONLY optional field. No amount_cents, plan_code,
    # billing_period, tenant_id, ends_at, or provider-transaction data --
    # confirm/reject can never accept a purchase-snapshot field, only an
    # operator's own free-text note about the review itself.
    note: str | None = Field(default=None, max_length=255)


@router.get("/manual-payments", response_model=RespVo)
async def list_manual_billing_payments(
    review_status: str = MANUAL_REVIEW_WAITING_CONFIRMATION,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    rows = await BillingService(db).list_manual_payments_for_super(review_status=review_status)
    return success_response(data=rows, msg="ok")


@router.post("/manual-payments/{payment_id}/confirm", response_model=RespVo)
async def confirm_manual_billing_payment(
    payment_id: str,
    body: ManualPaymentReviewRequest,
    actor: str = Depends(_verify_super_token),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    # F1G-CM Phase 12-13: the only authority accepted from the request is
    # payment_id (path) + an optional note -- amount/plan/tenant/date are
    # always re-derived server-side from the payment's own persisted row by
    # BillingService.confirm_manual_payment(), which builds the
    # MANUAL_VERIFIED_PAYMENT_FACT and hands it to the SAME
    # process_verified_payment_fact() core a real WXPAY callback would use.
    service = BillingService(db)
    try:
        result = await service.confirm_manual_payment(
            int(payment_id), verified_by=actor or "super_admin", note=body.note
        )
    except ManualPaymentStateError as exc:
        return error_response(code=400, msg=str(exc))
    except ValueError as exc:
        return error_response(code=404, msg=str(exc))
    return success_response(data=result, msg="已确认到账")


@router.post("/manual-payments/{payment_id}/reject", response_model=RespVo)
async def reject_manual_billing_payment(
    payment_id: str,
    body: ManualPaymentReviewRequest,
    actor: str = Depends(_verify_super_token),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    service = BillingService(db)
    try:
        payment = await service.reject_manual_payment(
            int(payment_id), verified_by=actor or "super_admin", note=body.note
        )
    except ManualPaymentStateError as exc:
        return error_response(code=400, msg=str(exc))
    except ValueError as exc:
        return error_response(code=404, msg=str(exc))
    return success_response(data=serialize_payment(payment), msg="已驳回")
