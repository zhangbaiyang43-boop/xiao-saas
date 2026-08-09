import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import settings


REAL_PAYMENT_BLOCKED_REASON = "REAL PAYMENT BLOCKED BY PLATFORM PAYMENT CONFIG"


@dataclass(slots=True)
class BillingPaymentRequest:
    out_trade_no: str
    amount_cents: int
    currency: str
    description: str


@dataclass(slots=True)
class BillingPaymentNotification:
    out_trade_no: str
    transaction_id: str
    amount_cents: int
    currency: str
    trade_state: str
    provider_mchid: str | None = None
    provider_appid: str | None = None
    paid_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class BillingPaymentProvider:
    provider = "BASE"

    async def create_payment(self, data: BillingPaymentRequest) -> dict[str, Any]:
        raise NotImplementedError

    def verify_notify(self, headers: dict[str, str], body: bytes) -> BillingPaymentNotification | None:
        raise NotImplementedError


class FakeBillingPaymentProvider(BillingPaymentProvider):
    provider = "FAKE"
    provider_mchid = "fake-platform-mchid"
    provider_appid = "fake-platform-appid"

    async def create_payment(self, data: BillingPaymentRequest) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_mchid": self.provider_mchid,
            "provider_appid": self.provider_appid,
            "pay_params": {
                "fake": True,
                "out_trade_no": data.out_trade_no,
                "amount_cents": data.amount_cents,
                "currency": data.currency,
            },
        }

    def verify_notify(self, headers: dict[str, str], body: bytes) -> BillingPaymentNotification | None:
        if headers.get("x-billing-fake-signature") != "valid":
            return None
        try:
            payload = json.loads(body.decode() or "{}")
        except Exception:
            return None
        try:
            return BillingPaymentNotification(
                out_trade_no=str(payload.get("out_trade_no") or ""),
                transaction_id=str(payload.get("transaction_id") or ""),
                amount_cents=int(payload.get("amount_cents") or 0),
                currency=str(payload.get("currency") or "CNY"),
                trade_state=str(payload.get("trade_state") or ""),
                provider_mchid=str(payload.get("provider_mchid") or self.provider_mchid),
                provider_appid=str(payload.get("provider_appid") or self.provider_appid),
                paid_at=datetime.now(timezone.utc).replace(tzinfo=None),
                metadata={
                    "event_type": str(payload.get("event_type") or "TRANSACTION.SUCCESS"),
                    "provider": self.provider,
                },
            )
        except Exception:
            return None


class PlatformWxPayBillingProvider(BillingPaymentProvider):
    provider = "WXPAY"

    @property
    def enabled(self) -> bool:
        # WX_SP_* is only documented as service-provider infrastructure in this repo,
        # not as confirmed platform SaaS receivables config.
        return False

    async def create_payment(self, data: BillingPaymentRequest) -> dict[str, Any]:
        raise RuntimeError(REAL_PAYMENT_BLOCKED_REASON)

    def verify_notify(self, headers: dict[str, str], body: bytes) -> BillingPaymentNotification | None:
        return None


def get_billing_payment_provider(provider: str | None = None) -> BillingPaymentProvider:
    if (provider or "").upper() == "WXPAY":
        return PlatformWxPayBillingProvider()
    return FakeBillingPaymentProvider()


def platform_payment_config_audit() -> dict[str, Any]:
    return {
        "real_payment_enabled": False,
        "blocked_reason": REAL_PAYMENT_BLOCKED_REASON,
        "wx_sp_config_present": {
            "WX_SP_MCH": bool(getattr(settings, "WX_SP_MCH", "")),
            "WX_SP_API_KEY_V3": bool(getattr(settings, "WX_SP_API_KEY_V3", "")),
            "WX_SP_CERT_SERIAL": bool(getattr(settings, "WX_SP_CERT_SERIAL", "")),
            "WX_SP_PRIVATE_KEY": bool(getattr(settings, "WX_SP_PRIVATE_KEY", "")),
        },
        "audit_result": "WX_SP_* is not referenced by current money movement code and .env.example labels it as ISV/service-provider config, not confirmed SaaS platform receivables.",
    }
