from typing import Any, TypeAlias

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import RespVo, error_response, success_response
from app.services.billing_service import (
    BillingService,
    ManualPaymentDisabledError,
    ManualPaymentStateError,
    MockPaymentDisabledError,
    serialize_invoice,
    serialize_payment,
)


ApiResponse: TypeAlias = RespVo[Any]

router = APIRouter(prefix="/api/v1/billing", tags=["SaaS Billing"])


class BillingPaymentCreateRequest(BaseModel):
    # F1G-CF-A: a merchant-facing commercial API must never silently default
    # into the mock-money test provider. WXPAY is always blocked today
    # (REAL_PAYMENT_BLOCKED_REASON), so an omitted provider now lands on the
    # same safe, already-rejected path instead of quietly creating a FAKE
    # payment. The Admin frontend already sends provider: 'WXPAY' explicitly
    # (SubscriptionSettings.vue) -- this default only closes the gap for any
    # caller that omits the field.
    provider: str = "WXPAY"


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
    # F1G-CM: manual_payment_available is a SEPARATE authority from
    # online_payment_available -- one flag being true never implies or
    # excludes the other. Same minimal-boolean shape as online_payment_available:
    # no provider names, no config presence, no internal detail.
    manual_status = BillingService.manual_payment_config_status()
    manual_payment_available = bool(manual_status.get("manual_payment_available", False))
    return success_response(
        data={
            "online_payment_available": online_payment_available,
            "manual_payment_available": manual_payment_available,
        },
        msg="ok",
    )


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
    except MockPaymentDisabledError as exc:
        # Same code/shape as every other mock-money-disabled response in this
        # codebase (app/api/v1/member.py's /recharge, order_payment_service.py's
        # mock_pay_order) -- not the WXPAY-blocked 422, and no
        # payment_config_status() attached, since that dict describes real
        # platform WXPAY config presence, not mock-money policy.
        return error_response(code=403, msg=str(exc))
    except ManualPaymentDisabledError as exc:
        return error_response(code=403, msg=str(exc))
    except RuntimeError as exc:
        # F1G-CF-C1: no longer attaches BillingService.payment_config_status()
        # here. That dict is now a more granular structured audit (mchid/
        # appid/cert/key presence booleans, payment mode, etc.) than the old
        # 4-field wx_sp_config_present shape -- exactly the kind of "which
        # secret is missing" internal config detail this phase's own
        # payment-readiness design says merchants must never see (it remains
        # available to SuperAdmin via GET /api/super/billing/payment-config-status).
        return error_response(code=422, msg=str(exc))
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


@router.post("/payments/{payment_id}/manual-claim", response_model=RespVo)
async def claim_manual_billing_payment(
    payment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    # F1G-CM Phase 8: "我已付款" -- a PAYMENT CLAIM, never a PAYMENT FACT.
    # See BillingService.claim_manual_payment()'s own docstring: this can
    # never mark the invoice/payment paid or apply a subscription. Owner-only
    # enforcement comes from the SAME middleware default-deny every other
    # /api/v1/billing/* route already relies on (staff_route_allowed()) --
    # no extra role check needed here.
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    service = BillingService(db)
    service.set_tenant_id(tenant_id)
    try:
        payment = await service.claim_manual_payment(int(payment_id))
    except ManualPaymentStateError as exc:
        return error_response(code=400, msg=str(exc))
    except ValueError as exc:
        # Covers both "no such payment" and "belongs to a different tenant"
        # (claim_manual_payment's own lookup is tenant-scoped) -- 404 either
        # way, never distinguishing the two to an external caller.
        return error_response(code=404, msg=str(exc))
    return success_response(data=serialize_payment(payment), msg="已提交付款确认")


@router.post("/wxpay-notify")
async def billing_wxpay_notify(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    headers = {k.lower(): v for k, v in dict(request.headers).items()}
    raw_body = await request.body()
    # F1G-CF-A: this route's own name/purpose is a WeChat Pay callback --
    # missing/omitted provider must not implicitly mean the mock-money test
    # provider. See BillingService.process_provider_notification() for the
    # authoritative FAKE-disabled gate (this default is defense-in-depth,
    # not the real boundary).
    provider = request.query_params.get("provider") or "WXPAY"
    return await BillingService(db).process_provider_notification(
        provider_name=provider,
        headers=headers,
        body=raw_body,
    )
