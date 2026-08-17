from typing import Any, TypeAlias

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import RespVo, error_response, success_response
from app.services.billing_service import BillingService, serialize_invoice, serialize_payment


ApiResponse: TypeAlias = RespVo[Any]

router = APIRouter(prefix="/api/v1/billing", tags=["SaaS Billing"])


class BillingPaymentCreateRequest(BaseModel):
    provider: str = "FAKE"


def _merchant_tenant_id(request: Request) -> str | None:
    if getattr(request.state, "token_type", None) != "merchant":
        return None
    return getattr(request.state, "tenant_id", None)


@router.get("/invoices", response_model=RespVo)
async def list_my_billing_invoices(request: Request, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    service = BillingService(db)
    service.set_tenant_id(tenant_id)
    invoices = await service.list_invoices_for_tenant()
    return success_response(data=[serialize_invoice(item) for item in invoices], msg="ok")


@router.get("/invoices/{invoice_id}", response_model=RespVo)
async def get_my_billing_invoice(invoice_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    service = BillingService(db)
    service.set_tenant_id(tenant_id)
    invoice = await service.get_invoice_for_tenant(int(invoice_id))
    if not invoice:
        return error_response(code=404, msg="账单不存在")
    return success_response(data=serialize_invoice(invoice), msg="ok")


@router.get("/payment-readiness", response_model=RespVo)
async def get_merchant_payment_readiness(request: Request) -> ApiResponse:
    # Merchant-facing readiness check (Phase F1E-A) -- lets the "我的套餐"
    # page disable its purchase/renewal CTA BEFORE ever calling
    # renewal-orders, so a merchant can never end up with a Pending
    # BillingInvoice they have no way to pay. Pure read, no `db` dependency
    # at all: BillingService.payment_config_status() is a static method, so
    # this handler cannot write anything even by accident.
    #
    # Maps the internal platform_payment_config_audit() dict down to a
    # single boolean -- merchants never see provider names, WX_SP_* config
    # presence, or the internal blocked_reason text; that's platform-ops-only
    # detail already exposed separately at
    # GET /api/super/billing/payment-config-status (SuperAdmin token only).
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    config_status = BillingService.payment_config_status()
    online_payment_available = bool(config_status.get("real_payment_enabled", False))
    return success_response(data={"online_payment_available": online_payment_available}, msg="ok")


@router.post("/invoices/{invoice_id}/payments", response_model=RespVo)
async def create_my_billing_payment(
    invoice_id: str,
    body: BillingPaymentCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    service = BillingService(db)
    service.set_tenant_id(tenant_id)
    try:
        payment, provider_result = await service.create_payment_attempt(int(invoice_id), body.provider)
    except RuntimeError as exc:
        return error_response(code=422, msg=str(exc), data=BillingService.payment_config_status())
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return success_response(
        data={
            "payment": serialize_payment(payment),
            "provider": provider_result,
        },
        msg="支付单已创建",
    )


@router.get("/payments/{payment_id}", response_model=RespVo)
async def get_my_billing_payment(payment_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    service = BillingService(db)
    service.set_tenant_id(tenant_id)
    payment = await service.get_payment_for_tenant(int(payment_id))
    if not payment:
        return error_response(code=404, msg="支付记录不存在")
    return success_response(data=serialize_payment(payment), msg="ok")


@router.post("/wxpay-notify")
async def billing_wxpay_notify(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    headers = {k.lower(): v for k, v in dict(request.headers).items()}
    raw_body = await request.body()
    provider = request.query_params.get("provider") or "FAKE"
    return await BillingService(db).process_provider_notification(
        provider_name=provider,
        headers=headers,
        body=raw_body,
    )
