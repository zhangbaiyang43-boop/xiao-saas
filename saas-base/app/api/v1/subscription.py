from typing import Any, TypeAlias

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.core.response import RespVo, error_response, success_response
from app.models.subscription import Plan
from app.services.billing_service import BillingService
from app.services.subscription_service import (
    PLAN_CODE_FREE,
    PLAN_CODE_PRO,
    PLAN_CODE_STANDARD,
    CrossPlanChangeNotAllowedError,
    EffectiveSubscriptionView,
    PlanDataIntegrityError,
    PlanResolutionError,
    SubscriptionService,
)

# Phase F1D — Merchant Subscription API (docs/saas-subscription-audit.md).
# Read (current/plans) + create-renewal-order only. No payment logic here --
# renewal-orders returns a BillingInvoice, and the client drives the SAME
# existing POST /api/v1/billing/invoices/{invoice_id}/payments flow that
# every other charge_type already uses. No entitlement/feature-gating here
# either -- see subscription_service.py's own module docstring.

ApiResponse: TypeAlias = RespVo[Any]

router = APIRouter(prefix="/api/v1/subscription", tags=["Merchant Subscription"])

# Frozen commercial contract (Phase F1D): annual discount display is a fixed
# label per plan, never computed at runtime from price_month_cents/
# price_year_cents (which remain the sole price authority).
_ANNUAL_DISCOUNT_DISPLAY = {
    PLAN_CODE_FREE: None,
    PLAN_CODE_STANDARD: "14%",
    PLAN_CODE_PRO: "14%",
}


class RenewalOrderCreateRequest(BaseModel):
    # extra="forbid": a client-supplied amount/tenant_id/discount must be a
    # hard validation error (422), never a silently-ignored extra field a
    # future reader could mistake for "accepted".
    model_config = ConfigDict(extra="forbid")

    plan_code: str
    billing_period: str


def _merchant_tenant_id(request: Request) -> str | None:
    if getattr(request.state, "token_type", None) != "merchant":
        return None
    return getattr(request.state, "tenant_id", None)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _serialize_effective_view(view: EffectiveSubscriptionView) -> dict[str, Any]:
    return {
        "effective_plan_code": view.effective_plan.code,
        "effective_plan_name": view.effective_plan.name,
        "subscription_status": view.subscription_status,
        "is_trial": view.is_trial,
        "trial_ends_at": _iso(view.trial_ends_at),
        "paid_started_at": _iso(view.paid_started_at),
        "paid_ends_at": _iso(view.paid_ends_at),
        "days_remaining": view.days_remaining,
        "can_renew": view.can_renew,
    }


def _serialize_plan(plan: Plan) -> dict[str, Any]:
    return {
        "plan_code": plan.code,
        "display_name": plan.name,
        "price_month_cents": plan.price_month_cents,
        "price_year_cents": plan.price_year_cents,
        "annual_discount_display": _ANNUAL_DISCOUNT_DISPLAY.get(plan.code),
    }


@router.get("/current", response_model=RespVo)
async def get_current_subscription_view(request: Request, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    try:
        view = await SubscriptionService(db).get_effective_subscription_view(tenant_id)
    except PlanDataIntegrityError as exc:
        logger.error("[SUBSCRIPTION_CATALOG_INTEGRITY] tenant_id=%s error=%s", tenant_id, exc)
        return error_response(code=500, msg="套餐数据异常，请联系客服")
    return success_response(data=_serialize_effective_view(view), msg="ok")


@router.get("/plans", response_model=RespVo)
async def list_plan_catalog(request: Request, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    # Available to any authenticated merchant regardless of current plan --
    # a FREE/expired/cancelled tenant must still be able to see what they
    # can buy (Phase F1D §12).
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")
    plans = await SubscriptionService(db).get_active_plans()
    return success_response(data=[_serialize_plan(p) for p in plans], msg="ok")


@router.post("/renewal-orders", response_model=RespVo)
async def create_renewal_order(
    body: RenewalOrderCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    tenant_id = _merchant_tenant_id(request)
    if not tenant_id:
        return error_response(code=401, msg="请先登录")

    service = SubscriptionService(db)
    try:
        plan, amount_cents = await service.validate_renewal_purchase(
            tenant_id, body.plan_code, body.billing_period
        )
    except CrossPlanChangeNotAllowedError as exc:
        return error_response(code=409, msg=str(exc))
    except PlanResolutionError as exc:
        # Covers PlanNotFoundError / PlanInactiveError / InvalidBillingPeriodError
        # / SubscriptionPurchaseNotAllowedError (FREE not payable) -- all
        # client-input problems, all 400.
        return error_response(code=400, msg=str(exc))

    invoice = await BillingService(db).create_invoice(
        tenant_id=tenant_id,
        charge_type="SAAS_SUBSCRIPTION",
        description=f"{plan.name} {body.billing_period}",
        amount_cents=amount_cents,
        plan_code=plan.code,
        billing_period=body.billing_period,
    )
    return success_response(
        data={
            "invoice_id": str(invoice.id),
            "plan_code": invoice.plan_code,
            "billing_period": invoice.billing_period,
            "amount_cents": invoice.amount_cents,
            "status": invoice.status,
            "created_at": _iso(invoice.created_at),
        },
        msg="续费订单已创建",
    )
