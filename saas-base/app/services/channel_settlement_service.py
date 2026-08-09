from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.channel_revenue import (
    ChannelCommissionLedger,
    ChannelCommissionSettlement,
    ChannelCommissionSettlementItem,
)
from app.services.base_service import BaseService
from app.services.channel_commission_service import (
    CHANNEL_COMMISSION_STATUS_AVAILABLE,
    CHANNEL_COMMISSION_STATUS_SETTLED,
    ChannelCommissionService,
)
from app.utils.id_generator import generate_snowflake_id


def serialize_settlement(item: ChannelCommissionSettlement) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "partner_id": str(item.partner_id),
        "settlement_no": item.settlement_no,
        "amount_cents": item.amount_cents,
        "status": item.status,
        "approved_at": item.approved_at.isoformat() if item.approved_at else None,
        "settled_at": item.settled_at.isoformat() if item.settled_at else None,
        "operator": item.operator,
        "transaction_reference": item.transaction_reference,
    }


class ChannelSettlementService(BaseService):
    async def create_manual_settlement(
        self,
        *,
        partner_id: int,
        operator: str,
        ledger_ids: list[int],
        transaction_reference: str | None = None,
    ) -> ChannelCommissionSettlement:
        if not ledger_ids:
            raise ValueError("ledger_ids required")
        await ChannelCommissionService(self.db).promote_available()
        result = await self.db.execute(
            select(ChannelCommissionLedger)
            .where(
                ChannelCommissionLedger.id.in_(ledger_ids),
                ChannelCommissionLedger.partner_id == partner_id,
            )
            .with_for_update()
        )
        ledgers = list(result.scalars().all())
        if len(ledgers) != len(set(ledger_ids)):
            raise ValueError("ledger not found")
        for ledger in ledgers:
            existing_item = await self.db.execute(
                select(ChannelCommissionSettlementItem).where(ChannelCommissionSettlementItem.ledger_id == ledger.id)
            )
            if existing_item.scalar_one_or_none():
                raise ValueError("ledger already settled")
            if ledger.status != CHANNEL_COMMISSION_STATUS_AVAILABLE:
                raise ValueError("only AVAILABLE ledger entries can be settled")

        now = datetime.utcnow()
        total = sum(item.commission_amount_cents for item in ledgers)
        settlement_id = generate_snowflake_id()
        settlement = ChannelCommissionSettlement(
            id=settlement_id,
            partner_id=partner_id,
            settlement_no=f"CSET{settlement_id}",
            amount_cents=total,
            status=CHANNEL_COMMISSION_STATUS_SETTLED,
            approved_at=now,
            settled_at=now,
            operator=operator or "",
            transaction_reference=transaction_reference,
        )
        self.db.add(settlement)
        for ledger in ledgers:
            ledger.status = CHANNEL_COMMISSION_STATUS_SETTLED
            self.db.add(
                ChannelCommissionSettlementItem(
                    settlement_id=settlement.id,
                    ledger_id=ledger.id,
                    partner_id=partner_id,
                    amount_cents=ledger.commission_amount_cents,
                )
            )
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError("ledger already settled") from exc
        await self.db.refresh(settlement)
        return settlement

    async def list_settlements(self, partner_id: int | None = None) -> list[ChannelCommissionSettlement]:
        query = select(ChannelCommissionSettlement)
        if partner_id:
            query = query.where(ChannelCommissionSettlement.partner_id == partner_id)
        result = await self.db.execute(query.order_by(ChannelCommissionSettlement.created_at.desc()))
        return list(result.scalars().all())

    async def list_settlements_for_partner(
        self,
        partner_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[ChannelCommissionSettlement], int]:
        total = await self.db.scalar(
            select(func.count()).select_from(ChannelCommissionSettlement).where(ChannelCommissionSettlement.partner_id == partner_id)
        )
        result = await self.db.execute(
            select(ChannelCommissionSettlement)
            .where(ChannelCommissionSettlement.partner_id == partner_id)
            .order_by(ChannelCommissionSettlement.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_settlement_for_partner(self, partner_id: int, settlement_id: int) -> ChannelCommissionSettlement | None:
        result = await self.db.execute(
            select(ChannelCommissionSettlement).where(
                ChannelCommissionSettlement.id == settlement_id,
                ChannelCommissionSettlement.partner_id == partner_id,
            )
        )
        return result.scalar_one_or_none()
