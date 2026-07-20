from sqlalchemy.future import select

from app.models.customer_identity import CustomerIdentity
from app.services.base_service import BaseService


CHANNEL_PHONE = "phone"
CHANNEL_MINIAPP = "miniapp"
CHANNEL_WECOM = "wecom"
CHANNEL_MANUAL = "manual"


class CustomerIdentityService(BaseService):
    async def get_by_identity(self, channel: str, channel_user_id: str) -> CustomerIdentity:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CustomerIdentity).filter(
                CustomerIdentity.tenant_id == tenant_id,
                CustomerIdentity.channel == channel,
                CustomerIdentity.channel_user_id == channel_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> CustomerIdentity:
        if not phone:
            return None
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CustomerIdentity).filter(
                CustomerIdentity.tenant_id == tenant_id,
                CustomerIdentity.channel == CHANNEL_PHONE,
                CustomerIdentity.channel_user_id == phone,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_customer(self, customer_id: int) -> list:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CustomerIdentity).filter(
                CustomerIdentity.tenant_id == tenant_id,
                CustomerIdentity.customer_id == customer_id,
            ).order_by(CustomerIdentity.bind_time.desc())
        )
        return result.scalars().all()

    async def bind_identity(
        self,
        customer_id: int,
        channel: str,
        channel_user_id: str,
        phone: str = None,
        unionid: str = None,
    ) -> CustomerIdentity:
        tenant_id = self.require_tenant_id()
        if not channel_user_id:
            return None

        existing = await self.get_by_identity(channel, channel_user_id)
        if existing:
            return existing

        identity = CustomerIdentity(
            tenant_id=tenant_id,
            customer_id=customer_id,
            channel=channel,
            channel_user_id=channel_user_id,
            phone=phone,
            unionid=unionid,
        )
        self.db.add(identity)
        await self.db.commit()
        await self.db.refresh(identity)
        return identity

    async def rebind_identity(
        self,
        *,
        channel: str,
        channel_user_id: str,
        customer_id: int,
        phone: str = None,
        unionid: str = None,
    ) -> CustomerIdentity:
        tenant_id = self.require_tenant_id()
        existing = await self.get_by_identity(channel, channel_user_id)
        if existing:
            existing.customer_id = customer_id
            if phone:
                existing.phone = phone
            if unionid:
                existing.unionid = unionid
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        return await self.bind_identity(
            customer_id=customer_id,
            channel=channel,
            channel_user_id=channel_user_id,
            phone=phone,
            unionid=unionid,
        )

    async def bind_customer_identities(
        self,
        customer_id: int,
        phone: str = None,
        openid: str = None,
        external_userid: str = None,
    ) -> list:
        identities = []
        if phone:
            identities.append(await self.bind_identity(customer_id, CHANNEL_PHONE, phone, phone=phone))
        if openid and not openid.startswith("phone:") and not openid.startswith("manual-"):
            identities.append(await self.bind_identity(customer_id, CHANNEL_MINIAPP, openid, phone=phone))
        if openid and openid.startswith("manual-"):
            identities.append(await self.bind_identity(customer_id, CHANNEL_MANUAL, openid, phone=phone))
        if external_userid:
            identities.append(await self.bind_identity(customer_id, CHANNEL_WECOM, external_userid, phone=phone))
        return [item for item in identities if item]
