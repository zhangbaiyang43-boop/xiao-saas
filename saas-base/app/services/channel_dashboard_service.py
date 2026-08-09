from typing import Any

from app.services.base_service import BaseService
from app.services.channel_commission_service import ChannelCommissionService, serialize_ledger
from app.services.channel_partner_service import ChannelPartnerService, serialize_partner


class ChannelDashboardService(BaseService):
    async def get_dashboard(self, partner_id: int) -> dict[str, Any]:
        commission_service = ChannelCommissionService(self.db)
        summary = await commission_service.get_partner_earnings_summary(partner_id)
        latest = await commission_service.list_ledgers(partner_id=partner_id, skip=0, limit=5)
        partner = await ChannelPartnerService(self.db).get_partner(partner_id)
        return {
            "partner": serialize_partner(partner) if partner else None,
            **summary,
            "latest_commissions": [serialize_ledger(item) for item in latest],
        }
