from app.models.billing import BillingInvoice


CHANNEL_COMMISSION_POLICY_VERSION = "CHANNEL_COMMISSION_V1_20260809"

ELIGIBLE_CHARGE_TYPES = {"SAAS_SUBSCRIPTION", "ADDON"}
NON_ELIGIBLE_CHARGE_TYPES = {
    "SETUP_SERVICE",
    "MINIPROGRAM_CERTIFICATION",
    "HARDWARE",
    "SMS_TOPUP",
    "OTHER",
}


def is_commission_eligible_charge_type(charge_type: str | None) -> bool:
    return (charge_type or "").upper() in ELIGIBLE_CHARGE_TYPES


def invoice_commission_snapshot(charge_type: str | None) -> tuple[bool, str]:
    return is_commission_eligible_charge_type(charge_type), CHANNEL_COMMISSION_POLICY_VERSION


def invoice_is_commission_eligible(invoice: BillingInvoice) -> bool:
    return bool(getattr(invoice, "commission_eligible", False))
