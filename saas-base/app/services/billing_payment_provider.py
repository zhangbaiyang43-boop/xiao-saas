import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import settings


REAL_PAYMENT_BLOCKED_REASON = "REAL PAYMENT BLOCKED BY PLATFORM PAYMENT CONFIG"
MANUAL_PAYMENT_BLOCKED_REASON = "MANUAL PAYMENT NOT AVAILABLE"

# F1G-CF-C1: the real WXPAY provider protocol (signature verification,
# decryption, prepay order construction) is not implemented yet -- this is
# a CODE-level capability flag, not an env var, specifically so no
# combination of production secrets can ever make real_payment_enabled
# true before an actual implementation phase (F1G-CF-C2+) flips this
# constant as part of shipping that code. Env values can never reach this.
PROVIDER_IMPLEMENTATION_READY = False

_SUPPORTED_PAYMENT_MODES = {"JSAPI", "MINIPROGRAM"}
_REAL_CALLBACK_PATH = "/api/v1/billing/wxpay-notify"


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


class ManualBillingPaymentProvider(BillingPaymentProvider):
    """F1G-CM: V1 SaaS subscription payment -- official QR code + platform
    SuperAdmin manually confirms the funds actually arrived. Unlike WXPAY
    (blocked because no protocol implementation exists) and FAKE (blocked by
    ALLOW_MOCK_MONEY_ENDPOINTS when disabled, but otherwise a fully working
    test provider), MANUAL is a real, intentionally-used V1 payment path,
    gated by its own independent settings.SAAS_MANUAL_PAYMENT_ENABLED.

    create_payment() only ever returns display data (payee name, QR image
    URL, confirmation-window minutes) that a client shows to a human -- it
    is not a signed protocol payload and carries no secret.

    verify_notify() always returns None: MANUAL never receives a provider
    callback. Confirmation is a trusted platform-operator action (see
    BillingService.confirm_manual_payment), which builds a
    BillingPaymentNotification directly from the server's own persisted
    Payment/Invoice rows and feeds it into the SAME
    process_verified_payment_fact() core a real WXPAY callback or query
    would use -- MANUAL is not a special bypass of that core, just a
    different, trusted way of producing the same verified-fact shape."""

    provider = "MANUAL"

    @property
    def enabled(self) -> bool:
        return bool(manual_payment_config_audit()["manual_payment_available"])

    async def create_payment(self, data: BillingPaymentRequest) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError(MANUAL_PAYMENT_BLOCKED_REASON)
        return {
            "provider": self.provider,
            "provider_mchid": None,
            "provider_appid": None,
            "pay_params": {
                "payee_name": settings.SAAS_MANUAL_PAYMENT_PAYEE_NAME,
                "qr_url": settings.SAAS_MANUAL_PAYMENT_QR_URL,
                "confirmation_minutes": settings.SAAS_MANUAL_PAYMENT_CONFIRM_MINUTES,
            },
        }

    def verify_notify(self, headers: dict[str, str], body: bytes) -> BillingPaymentNotification | None:
        return None


class PlatformWxPayBillingProvider(BillingPaymentProvider):
    provider = "WXPAY"

    @property
    def enabled(self) -> bool:
        # Single source of truth: mirrors platform_payment_config_audit()'s
        # real_payment_enabled exactly, so there is never a second,
        # independently-hardcoded "false" that could drift out of sync with
        # the audit. Always False today because PROVIDER_IMPLEMENTATION_READY
        # is False (F1G-CF-C1) -- create_payment()/verify_notify() below are
        # still stubs, not merely blocked by missing config.
        return bool(platform_payment_config_audit()["real_payment_enabled"])

    async def create_payment(self, data: BillingPaymentRequest) -> dict[str, Any]:
        raise RuntimeError(REAL_PAYMENT_BLOCKED_REASON)

    def verify_notify(self, headers: dict[str, str], body: bytes) -> BillingPaymentNotification | None:
        return None


def get_billing_payment_provider(provider: str | None = None) -> BillingPaymentProvider:
    normalized = (provider or "").upper()
    if normalized == "WXPAY":
        return PlatformWxPayBillingProvider()
    if normalized == "MANUAL":
        return ManualBillingPaymentProvider()
    return FakeBillingPaymentProvider()


def manual_payment_config_audit() -> dict[str, Any]:
    """Structured, fail-closed manual-payment readiness audit (F1G-CM).
    Independent of platform_payment_config_audit() (real WXPAY) -- neither
    flag's state affects the other. Every field is a local presence/shape
    check only; payee_name and qr_url are display data, never secrets, but
    are still never given a value in this repo."""
    enabled = bool(settings.SAAS_MANUAL_PAYMENT_ENABLED)
    payee_present = bool((settings.SAAS_MANUAL_PAYMENT_PAYEE_NAME or "").strip())
    qr_present = bool((settings.SAAS_MANUAL_PAYMENT_QR_URL or "").strip())
    manual_payment_available = enabled and payee_present and qr_present
    return {
        "manual_payment_enabled": enabled,
        "payee_present": payee_present,
        "qr_present": qr_present,
        "manual_payment_available": manual_payment_available,
    }


def platform_notify_url() -> str:
    """Canonical real-provider callback URL (F1G-CF-C1 Phase 6): reuses
    PUBLIC_BASE_URL (the project's existing production-base-URL authority,
    already used for H5_ORDER_BASE_URL etc.) rather than a second,
    separately-configured notify-URL field that could drift out of sync
    with it. The route path itself stays fixed -- this is a helper for
    constructing the value a future WXPAY create_payment() would send,
    not something the route itself needs to call."""
    base = (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    return f"{base}{_REAL_CALLBACK_PATH}"


def platform_payment_config_audit() -> dict[str, Any]:
    """Structured, fail-closed real-payment readiness audit (F1G-CF-C1).
    Every boolean here is a local presence/shape check only -- no network
    call, no WeChat Merchant Platform probe, no certificate-validity API
    call -- and no field ever carries a secret's actual value, only whether
    it is set. See PROVIDER_IMPLEMENTATION_READY's own comment for why
    real_payment_enabled cannot become true from config/env alone."""
    payment_mode = (settings.SAAS_PAYMENT_MODE or "").strip().upper()
    payment_mode_valid = payment_mode in _SUPPORTED_PAYMENT_MODES

    mchid_present = bool((settings.WX_SP_MCHID or "").strip())
    # Deliberately no fallback to WECHAT_APP_ID: that field belongs to the
    # restaurant customer-payment context, a different merchant-of-record
    # entirely (F1G-CF-B Phase 9 / F1G-CF-C1 Phase 2).
    appid_present = bool((settings.WX_SP_APPID or "").strip())
    api_v3_key_present = bool((settings.WX_SP_API_KEY_V3 or "").strip())
    cert_serial_present = bool((settings.WX_SP_CERT_SERIAL or "").strip())
    private_key_present = bool((settings.WX_SP_PRIVATE_KEY or "").strip())
    # Public-key verification mode only, for now -- APIv3 key alone is
    # NEVER sufficient to consider callback verification ready. Leaves
    # architectural room for a platform-certificate mode later (mirroring
    # wxpay_service.py's existing dual-mode support for the restaurant
    # flow), without wiring that mode up in this phase.
    verification_material_present = bool(
        (settings.WX_SP_PUBLIC_KEY_ID or "").strip() and (settings.WX_SP_PUBLIC_KEY or "").strip()
    )
    callback_url_valid = (settings.PUBLIC_BASE_URL or "").strip().startswith("https://")

    config_complete = (
        payment_mode_valid
        and mchid_present
        and appid_present
        and api_v3_key_present
        and cert_serial_present
        and private_key_present
        and verification_material_present
        and callback_url_valid
    )

    release_switch_enabled = bool(settings.SAAS_REAL_PAYMENT_ENABLED)
    real_payment_enabled = release_switch_enabled and config_complete and PROVIDER_IMPLEMENTATION_READY

    return {
        "release_switch_enabled": release_switch_enabled,
        "payment_mode": payment_mode,
        "payment_mode_valid": payment_mode_valid,
        "mchid_present": mchid_present,
        "appid_present": appid_present,
        "api_v3_key_present": api_v3_key_present,
        "cert_serial_present": cert_serial_present,
        "private_key_present": private_key_present,
        "verification_material_present": verification_material_present,
        "callback_url_valid": callback_url_valid,
        "provider_implementation_ready": PROVIDER_IMPLEMENTATION_READY,
        "config_complete": config_complete,
        "real_payment_enabled": real_payment_enabled,
        "blocked_reason": None if real_payment_enabled else REAL_PAYMENT_BLOCKED_REASON,
    }
