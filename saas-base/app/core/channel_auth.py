from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.channel_revenue import ChannelPartner
from app.services.channel_partner_service import (
    PARTNER_STATUS_ACTIVE,
    PARTNER_STATUS_DISABLED,
    ChannelPartnerService,
)


@dataclass(frozen=True)
class ChannelPrincipal:
    partner_id: int
    partner: ChannelPartner


async def get_current_channel_partner(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ChannelPrincipal:
    token_type = getattr(request.state, "token_type", None)
    partner_id = getattr(request.state, "partner_id", None)
    if token_type != "channel_partner" or not partner_id:
        raise HTTPException(status_code=403, detail="channel auth required")
    try:
        partner_id_int = int(partner_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail="channel auth required") from None

    partner = await ChannelPartnerService(db).get_partner(partner_id_int)
    if not partner or partner.status == PARTNER_STATUS_DISABLED:
        raise HTTPException(status_code=403, detail="channel auth required")
    return ChannelPrincipal(partner_id=partner_id_int, partner=partner)


async def require_active_channel_partner(
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
) -> ChannelPrincipal:
    if principal.partner.status != PARTNER_STATUS_ACTIVE:
        raise HTTPException(status_code=403, detail="active channel partner required")
    return principal
