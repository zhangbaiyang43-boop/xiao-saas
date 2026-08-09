import asyncio
import re
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.channel_revenue import (
    ChannelLead,
    ChannelLeadMobileLock,
    ChannelPartner,
    ChannelPartnerTenantBinding,
)
from app.models.tenant import Tenant
from app.services.base_service import BaseService


PARTNER_STATUS_ACTIVE = "ACTIVE"
PARTNER_STATUS_SUSPENDED = "SUSPENDED"
PARTNER_STATUS_DISABLED = "DISABLED"
PARTNER_STATUSES = {PARTNER_STATUS_ACTIVE, PARTNER_STATUS_SUSPENDED, PARTNER_STATUS_DISABLED}

PARTNER_TYPES = {
    "WINE_SALES",
    "PAYMENT_AGENT",
    "POS_VENDOR",
    "ADVERTISING",
    "PRINTING",
    "FOOD_SUPPLIER",
    "EQUIPMENT",
    "KITCHEN_SUPPLIER",
    "DECORATION",
    "FINANCE_TAX",
    "OTHER",
}

LEAD_STATUS_PROTECTED = "PROTECTED"
LEAD_STATUS_CONTACTED = "CONTACTED"
LEAD_STATUS_DEMO = "DEMO"
LEAD_STATUS_WON = "WON"
LEAD_STATUS_LOST = "LOST"
LEAD_STATUS_EXPIRED = "EXPIRED"
ACTIVE_LEAD_STATUSES = {LEAD_STATUS_PROTECTED, LEAD_STATUS_CONTACTED, LEAD_STATUS_DEMO}

BINDING_STATUS_ACTIVE = "ACTIVE"
DEFAULT_PROTECTION_DAYS = 90
DEFAULT_COMMISSION_RATE_BPS = 2000
DEFAULT_COMMISSION_TERM_MONTHS = 36

_process_mobile_locks = defaultdict(asyncio.Lock)


def normalize_mobile(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def serialize_partner(partner: ChannelPartner) -> dict:
    return {
        "id": str(partner.id),
        "partner_code": partner.partner_code,
        "name": partner.name,
        "mobile": partner.mobile,
        "mobile_normalized": partner.mobile_normalized,
        "partner_type": partner.partner_type,
        "status": partner.status,
    }


def serialize_lead(lead: ChannelLead) -> dict:
    return {
        "id": str(lead.id),
        "partner_id": str(lead.partner_id),
        "merchant_name": lead.merchant_name,
        "merchant_mobile": lead.merchant_mobile,
        "contact_name": lead.contact_name,
        "status": lead.status,
        "tenant_id": lead.tenant_id,
        "protected_at": lead.protected_at.isoformat() if lead.protected_at else None,
        "protected_until": lead.protected_until.isoformat() if lead.protected_until else None,
        "converted_at": lead.converted_at.isoformat() if lead.converted_at else None,
    }


def serialize_binding(binding: ChannelPartnerTenantBinding) -> dict:
    return {
        "id": str(binding.id),
        "tenant_id": binding.tenant_id,
        "partner_id": str(binding.partner_id),
        "source_lead_id": str(binding.source_lead_id) if binding.source_lead_id else None,
        "status": binding.status,
        "commission_rate_bps": binding.commission_rate_bps,
        "commission_term_months": binding.commission_term_months,
        "commission_started_at": binding.commission_started_at.isoformat() if binding.commission_started_at else None,
        "commission_ends_at": binding.commission_ends_at.isoformat() if binding.commission_ends_at else None,
    }


class ChannelPartnerService(BaseService):
    async def create_partner(
        self,
        *,
        partner_code: str,
        name: str,
        mobile: str,
        partner_type: str,
        status: str = PARTNER_STATUS_ACTIVE,
    ) -> ChannelPartner:
        code = (partner_code or "").strip().upper()
        partner_type = (partner_type or "OTHER").upper()
        status = (status or PARTNER_STATUS_ACTIVE).upper()
        if not code:
            raise ValueError("partner_code required")
        if partner_type not in PARTNER_TYPES:
            raise ValueError("partner_type unsupported")
        if status not in PARTNER_STATUSES:
            raise ValueError("partner status unsupported")
        partner = ChannelPartner(
            partner_code=code,
            name=(name or "").strip(),
            mobile=normalize_mobile(mobile),
            mobile_normalized=normalize_mobile(mobile),
            partner_type=partner_type,
            status=status,
        )
        self.db.add(partner)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError("partner_code or mobile already exists") from exc
        await self.db.refresh(partner)
        return partner

    async def list_partners(self) -> list[ChannelPartner]:
        result = await self.db.execute(select(ChannelPartner).order_by(ChannelPartner.created_at.desc()))
        return list(result.scalars().all())

    async def get_partner(self, partner_id: int) -> ChannelPartner | None:
        result = await self.db.execute(select(ChannelPartner).where(ChannelPartner.id == partner_id))
        return result.scalar_one_or_none()

    async def get_partner_by_mobile_normalized(self, mobile_normalized: str) -> ChannelPartner | None:
        result = await self.db.execute(
            select(ChannelPartner).where(ChannelPartner.mobile_normalized == normalize_mobile(mobile_normalized))
        )
        return result.scalar_one_or_none()

    async def create_lead(
        self,
        *,
        partner_id: int,
        merchant_name: str,
        merchant_mobile: str,
        contact_name: str,
    ) -> ChannelLead:
        mobile_key = normalize_mobile(merchant_mobile)
        if not mobile_key:
            raise ValueError("merchant_mobile required")
        async with _process_mobile_locks[mobile_key]:
            partner = await self._get_active_partner(partner_id)
            if not partner:
                raise ValueError("partner must be ACTIVE")
            await self._ensure_mobile_lock_row(mobile_key)
            lock_result = await self.db.execute(
                select(ChannelLeadMobileLock)
                .where(ChannelLeadMobileLock.merchant_mobile_normalized == mobile_key)
                .with_for_update()
            )
            if not lock_result.scalar_one_or_none():
                raise ValueError("lead mobile lock unavailable")

            now = datetime.utcnow()
            await self._expire_mobile_leads(mobile_key, now)
            active_result = await self.db.execute(
                select(ChannelLead).where(
                    ChannelLead.merchant_mobile_normalized == mobile_key,
                    ChannelLead.status.in_(ACTIVE_LEAD_STATUSES),
                    ChannelLead.protected_until > now,
                )
            )
            active = active_result.scalar_one_or_none()
            if active and active.partner_id != partner.id:
                raise ValueError("merchant_mobile already protected")
            if active:
                raise ValueError("merchant_mobile already protected")

            lead = ChannelLead(
                partner_id=partner.id,
                merchant_name=(merchant_name or "").strip(),
                merchant_mobile=normalize_mobile(merchant_mobile),
                merchant_mobile_normalized=mobile_key,
                contact_name=(contact_name or "").strip(),
                status=LEAD_STATUS_PROTECTED,
                protected_at=now,
                protected_until=now + timedelta(days=DEFAULT_PROTECTION_DAYS),
            )
            self.db.add(lead)
            await self.db.commit()
            await self.db.refresh(lead)
            return lead

    async def list_leads(self) -> list[ChannelLead]:
        result = await self.db.execute(select(ChannelLead).order_by(ChannelLead.created_at.desc()))
        return list(result.scalars().all())

    async def list_leads_for_partner(self, partner_id: int, skip: int = 0, limit: int = 20) -> tuple[list[ChannelLead], int]:
        total = await self.db.scalar(select(func.count()).select_from(ChannelLead).where(ChannelLead.partner_id == partner_id))
        result = await self.db.execute(
            select(ChannelLead)
            .where(ChannelLead.partner_id == partner_id)
            .order_by(ChannelLead.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_lead_for_partner(self, partner_id: int, lead_id: int) -> ChannelLead | None:
        result = await self.db.execute(
            select(ChannelLead).where(ChannelLead.id == lead_id, ChannelLead.partner_id == partner_id)
        )
        return result.scalar_one_or_none()

    async def convert_lead_to_tenant_binding(self, lead_id: int, tenant_id: str) -> ChannelPartnerTenantBinding:
        lead_result = await self.db.execute(select(ChannelLead).where(ChannelLead.id == lead_id).with_for_update())
        lead = lead_result.scalar_one_or_none()
        if not lead:
            raise ValueError("lead not found")
        if lead.converted_at or lead.status == LEAD_STATUS_WON:
            raise ValueError("lead already converted")
        now = datetime.utcnow()
        await self._expire_mobile_leads(lead.merchant_mobile_normalized, now)
        await self.db.refresh(lead)
        if lead.status not in ACTIVE_LEAD_STATUSES or lead.protected_until <= now:
            raise ValueError("lead expired or not convertible")
        partner = await self._get_active_partner(lead.partner_id)
        if not partner:
            raise ValueError("partner must be ACTIVE")
        tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
        if not tenant_result.scalar_one_or_none():
            raise ValueError("tenant not found")
        existing_result = await self.db.execute(
            select(ChannelPartnerTenantBinding)
            .where(ChannelPartnerTenantBinding.tenant_id == tenant_id)
            .with_for_update()
        )
        if existing_result.scalar_one_or_none():
            raise ValueError("tenant already has channel binding")
        binding = ChannelPartnerTenantBinding(
            tenant_id=tenant_id,
            partner_id=lead.partner_id,
            source_lead_id=lead.id,
            status=BINDING_STATUS_ACTIVE,
            commission_rate_bps=DEFAULT_COMMISSION_RATE_BPS,
            commission_term_months=DEFAULT_COMMISSION_TERM_MONTHS,
        )
        lead.status = LEAD_STATUS_WON
        lead.tenant_id = tenant_id
        lead.converted_at = now
        self.db.add(binding)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError("tenant already has channel binding") from exc
        await self.db.refresh(binding)
        return binding

    async def list_bindings(self) -> list[ChannelPartnerTenantBinding]:
        result = await self.db.execute(select(ChannelPartnerTenantBinding).order_by(ChannelPartnerTenantBinding.created_at.desc()))
        return list(result.scalars().all())

    async def list_bindings_for_partner(
        self,
        partner_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[ChannelPartnerTenantBinding], int]:
        total = await self.db.scalar(
            select(func.count()).select_from(ChannelPartnerTenantBinding).where(ChannelPartnerTenantBinding.partner_id == partner_id)
        )
        result = await self.db.execute(
            select(ChannelPartnerTenantBinding)
            .where(ChannelPartnerTenantBinding.partner_id == partner_id)
            .order_by(ChannelPartnerTenantBinding.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_binding_for_partner(self, partner_id: int, binding_id: int) -> ChannelPartnerTenantBinding | None:
        result = await self.db.execute(
            select(ChannelPartnerTenantBinding).where(
                ChannelPartnerTenantBinding.id == binding_id,
                ChannelPartnerTenantBinding.partner_id == partner_id,
            )
        )
        return result.scalar_one_or_none()

    async def _ensure_mobile_lock_row(self, mobile_key: str) -> None:
        for _ in range(2):
            existing = await self.db.execute(
                select(ChannelLeadMobileLock).where(ChannelLeadMobileLock.merchant_mobile_normalized == mobile_key)
            )
            if existing.scalar_one_or_none():
                return
            try:
                async with self.db.begin_nested():
                    self.db.add(ChannelLeadMobileLock(merchant_mobile_normalized=mobile_key))
                    await self.db.flush()
                return
            except IntegrityError:
                await asyncio.sleep(0)
        return

    async def _expire_mobile_leads(self, mobile_key: str, now: datetime) -> None:
        result = await self.db.execute(
            select(ChannelLead)
            .where(
                ChannelLead.merchant_mobile_normalized == mobile_key,
                ChannelLead.status.in_(ACTIVE_LEAD_STATUSES),
                ChannelLead.protected_until <= now,
            )
            .with_for_update()
        )
        for lead in result.scalars().all():
            lead.status = LEAD_STATUS_EXPIRED

    async def _get_active_partner(self, partner_id: int) -> ChannelPartner | None:
        result = await self.db.execute(
            select(ChannelPartner).where(
                ChannelPartner.id == partner_id,
                ChannelPartner.status == PARTNER_STATUS_ACTIVE,
            )
        )
        return result.scalar_one_or_none()
