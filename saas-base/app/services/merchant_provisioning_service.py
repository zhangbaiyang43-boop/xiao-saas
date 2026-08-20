from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.services.subscription_service import SubscriptionService
from app.services.tenant_service import TenantService
from app.utils.id_generator import generate_tenant_id

# Merchant Provisioning Foundation (Phase 01). This is the single Domain
# Authority for "create a new merchant" -- the only place that is allowed to
# orchestrate Tenant + TenantConfig + trial Subscription as one unit. Routers
# (app/api/v1/login.py::register, app/api/v1/super_admin.py::create_merchant)
# must call this service and must not call TenantService/SubscriptionService
# directly to create a tenant -- that was the old, divergent shape (Super
# Admin created no trial; self-registration created one inline in the
# router), which is exactly what this service replaces.
#
# TenantService.create_tenant() and SubscriptionService.create_trial_for_tenant()
# remain the real primitives this service composes (both already support
# commit=False for exactly this purpose) -- this file does not reimplement
# their DB writes, only owns the transaction boundary around them.


class ProvisioningSource:
    """Who initiated this provisioning. Not just an audit label: trial policy
    (see TrialPolicy) currently defaults the same way regardless of source,
    but call sites must still say which they are, explicitly, rather than
    leaving it to be inferred from which router happened to call in -- that
    inference is exactly how the pre-Phase-01 Super Admin / self-register
    split silently diverged in the first place."""

    SELF_REGISTER = "SELF_REGISTER"
    SUPER_ADMIN = "SUPER_ADMIN"


class TrialPolicy:
    """Explicit trial-grant decision for one provisioning call, so a future
    caller that genuinely needs to skip the trial (e.g. a not-yet-existing
    "manual free tenant" contract) has to say so out loud rather than the
    absence of a trial being an accidental side effect of which code path
    it went through.

    Frozen product decision for Phase 01 (docs audit found no existing
    "special/internal/test/free tenant" contract in code or tests): every
    genuinely new tenant, regardless of source, gets the same 30-day PRO
    trial. GRANT_DEFAULT_TRIAL is therefore the default for both
    ProvisioningSource values.
    """

    GRANT_DEFAULT_TRIAL = "GRANT_DEFAULT_TRIAL"
    NO_TRIAL = "NO_TRIAL"


class ProvisioningError(Exception):
    """Base class for MerchantProvisioningService failures that a router is
    expected to catch and translate into a stable RespVo error -- never a
    raw 500."""


class PhoneAlreadyRegisteredError(ProvisioningError):
    """Raised whether the duplicate was caught by the fast pre-check or by
    the DB's ux_tenant_phone unique index (the TOCTOU backstop) -- callers
    get the same exception either way and don't need to know which path
    caught it."""

    def __init__(self, phone: str):
        self.phone = phone
        super().__init__(f"phone already registered: {phone}")


def _is_phone_uniqueness_violation(exc: IntegrityError) -> bool:
    # ux_tenant_phone is the only unique constraint this insert can hit that
    # mentions "phone" -- tenant.tenant_id's own uniqueness violation (an
    # astronomically unlikely id collision) would mention "tenant_id"
    # instead, and must NOT be swallowed as a phone conflict.
    message = str(getattr(exc, "orig", None) or exc).lower()
    return "phone" in message


@dataclass
class ProvisionResult:
    tenant: Tenant
    subscription: Optional[Subscription]


class MerchantProvisioningService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def provision_merchant(
        self,
        *,
        name: str,
        phone: str,
        source: str,
        address: str | None = None,
        logo_url: str | None = None,
        trial_policy: str = TrialPolicy.GRANT_DEFAULT_TRIAL,
    ) -> ProvisionResult:
        """Create Tenant + TenantConfig + (per trial_policy) a trial
        Subscription as one all-or-nothing transaction that THIS method
        owns: internal calls to TenantService/SubscriptionService are always
        made with commit=False (flush only), and this method issues the one
        real db.commit() at the end. Any failure anywhere in the sequence
        rolls back everything -- no orphan tenant, no orphan config, no
        tenant-without-trial left behind by a partial failure.

        Fast-path duplicate check first (cheap, avoids burning a tenant_id /
        DB round trip on the common case), then the DB's ux_tenant_phone
        unique index is the real, race-safe authority -- a concurrent
        duplicate that slips past the fast-path check still fails atomically
        at flush/commit time and is translated to the same
        PhoneAlreadyRegisteredError, never a raw 500.
        """
        tenant_service = TenantService(self.db)

        existing = await tenant_service.get_tenant_by_phone(phone)
        if existing is not None:
            raise PhoneAlreadyRegisteredError(phone)

        if source not in (ProvisioningSource.SELF_REGISTER, ProvisioningSource.SUPER_ADMIN):
            raise ValueError(f"unknown provisioning source: {source!r}")

        tenant_id = generate_tenant_id()
        try:
            tenant = await tenant_service.create_tenant(
                tenant_id=tenant_id,
                name=name,
                password_hash="",
                phone=phone,
                address=address,
                logo_url=logo_url,
                commit=False,
            )

            subscription: Optional[Subscription] = None
            if trial_policy == TrialPolicy.GRANT_DEFAULT_TRIAL:
                subscription = await SubscriptionService(self.db).create_trial_for_tenant(
                    tenant.tenant_id, commit=False
                )
            elif trial_policy != TrialPolicy.NO_TRIAL:
                raise ValueError(f"unknown trial_policy: {trial_policy!r}")

            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            if _is_phone_uniqueness_violation(exc):
                raise PhoneAlreadyRegisteredError(phone) from exc
            raise
        except Exception:
            await self.db.rollback()
            raise

        await self.db.refresh(tenant)
        logger.info(
            f"[MERCHANT_PROVISION] source={source} tenant_id={tenant_id} "
            f"trial_policy={trial_policy} trial_granted={subscription is not None}"
        )
        return ProvisionResult(tenant=tenant, subscription=subscription)
