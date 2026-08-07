from dataclasses import dataclass
from enum import Enum

from sqlalchemy.future import select

from app.core.logger import logger
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity
from app.services.base_service import BaseService


CHANNEL_PHONE = "phone"
CHANNEL_MINIAPP = "miniapp"
CHANNEL_WECOM = "wecom"
CHANNEL_MANUAL = "manual"


class JoinResolutionOutcome(str, Enum):
    SUCCESS = "success"
    UNVERIFIED_PHONE_BLOCKED = "unverified_phone_blocked"
    CUSTOMER_DISABLED = "customer_disabled"


@dataclass
class JoinCustomerResolution:
    outcome: JoinResolutionOutcome
    customer: Customer | None = None
    is_new_customer: bool = False
    matched_by: str | None = None
    blocked_customer_id: int | None = None
    phone_switch_old_customer_id: int | None = None
    phone_changed_old_phone: str | None = None
    openid_conflict_existing_id: int | None = None


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

    async def _update_join_customer_info(
        self,
        customer_service,
        existing_customer: Customer,
        *,
        phone: str,
        openid: str,
        auto_member_name: str,
        tenant_id: str,
    ) -> Customer:
        update_data = {}
        if existing_customer.name in (None, "", "会员", "小程序顾客"):
            update_data["name"] = auto_member_name
        if phone and existing_customer.phone != phone:
            update_data["phone"] = phone
        if openid and existing_customer.openid != openid:
            openid_customer = await customer_service.get_customer_by_openid_any_status(openid, tenant_id)
            if not openid_customer or openid_customer.id == existing_customer.id:
                update_data["openid"] = openid
            else:
                logger.info(
                    f"当前 customer.openid 已被其他会员占用，跳过更新 - "
                    f"current_customer_id: {existing_customer.id}, openid_customer_id: {openid_customer.id}"
                )
        if update_data:
            logger.info(f"更新会员信息 - customer_id: {existing_customer.id}, update_data: {update_data}")
            return await customer_service.update_customer(existing_customer.id, **update_data)
        return existing_customer

    async def resolve_customer_for_join(
        self,
        *,
        phone: str,
        phone_verified: bool,
        openid: str,
        unionid: str | None,
        auto_member_name: str,
    ) -> JoinCustomerResolution:
        """Determine which customer record a miniapp join should bind to.

        Phone must be WeChat-verified (phone_verified=True) before reusing an
        existing account matched only by phone string — never reintroduce
        unverified phone-based account takeover (see customer_service.create_customer
        IntegrityError comment, P0).
        """
        from app.services.customer_service import CustomerService

        tenant_id = self.require_tenant_id()
        customer_service = CustomerService(self.db)
        customer_service.set_tenant_id(tenant_id)

        phone_customer = (
            await customer_service.get_customer_by_phone_any_status(phone, tenant_id) if phone else None
        )
        logger.info(
            f"phone lookup result - phone: {phone}, found: {bool(phone_customer)}, "
            f"customer_id: {getattr(phone_customer, 'id', None)}, "
            f"customer_phone: {getattr(phone_customer, 'phone', None)}"
        )

        identity = await self.get_by_identity(CHANNEL_MINIAPP, openid)
        identity_customer_id = identity.customer_id if identity else None

        customer = None
        is_new_customer = False
        phone_switch_old_customer_id = None
        phone_changed_old_phone = None
        openid_conflict_existing_id = None

        if phone_customer:
            already_owns = bool(identity_customer_id) and identity_customer_id == phone_customer.id
            if not phone_verified and not already_owns:
                logger.warning(
                    f"未验证手机号匹配到已有会员，拒绝自动绑定 - "
                    f"phone_customer_id: {phone_customer.id}, openid: {openid}, phone: {phone}"
                )
                return JoinCustomerResolution(
                    outcome=JoinResolutionOutcome.UNVERIFIED_PHONE_BLOCKED,
                    blocked_customer_id=phone_customer.id,
                )

            customer = phone_customer
            if customer.status != 1:
                return JoinCustomerResolution(
                    outcome=JoinResolutionOutcome.CUSTOMER_DISABLED,
                    blocked_customer_id=customer.id,
                    matched_by="phone",
                )

            logger.info(f"手机号找到会员 - customer_id: {customer.id}, phone: {phone}")
            if identity_customer_id and identity_customer_id != customer.id:
                phone_switch_old_customer_id = identity_customer_id
                logger.info(
                    f"手机号已切换会员，openid 从旧会员迁移到当前手机号会员 - "
                    f"old_customer_id: {identity_customer_id}, new_customer_id: {customer.id}, phone: {phone}"
                )

            await self.rebind_identity(
                customer_id=customer.id,
                channel=CHANNEL_MINIAPP,
                channel_user_id=openid,
                phone=phone,
                unionid=unionid,
            )
            logger.info(f"重绑 identity（已有会员）- customer_id: {customer.id}, openid: {openid}")
            customer = await self._update_join_customer_info(
                customer_service,
                customer,
                phone=phone,
                openid=openid,
                auto_member_name=auto_member_name,
                tenant_id=tenant_id,
            )

        if not customer and identity_customer_id:
            existing_customer = await customer_service.get_customer_any_status(identity_customer_id)
            if existing_customer:
                if existing_customer.status != 1:
                    return JoinCustomerResolution(
                        outcome=JoinResolutionOutcome.CUSTOMER_DISABLED,
                        blocked_customer_id=existing_customer.id,
                        matched_by="identity",
                    )

                phone_changed_old_phone = existing_customer.phone
                logger.info(
                    f"identity 找到已有会员（手机号已更换）- customer_id: {existing_customer.id}, "
                    f"old_phone: {existing_customer.phone}, new_phone: {phone}"
                )
                customer = await self._update_join_customer_info(
                    customer_service,
                    existing_customer,
                    phone=phone,
                    openid=openid,
                    auto_member_name=auto_member_name,
                    tenant_id=tenant_id,
                )
                is_new_customer = False

        if not customer:
            customer_openid = openid
            openid_customer = await customer_service.get_customer_by_openid_any_status(openid, tenant_id)
            if openid_customer:
                customer_openid = f"phone:{phone}"
                openid_conflict_existing_id = openid_customer.id
                logger.info(
                    f"openid 已绑定到其他会员，当前用手机号注册新会员 - "
                    f"openid_customer_id: {openid_customer.id}, phone: {phone}"
                )

            customer = await customer_service.create_customer(
                tenant_id=tenant_id,
                openid=customer_openid,
                name=auto_member_name,
                phone=phone,
                tags=["小程序会员"],
            )
            if phone and customer.phone != phone:
                logger.warning(
                    f"create_customer returned mismatched phone - "
                    f"customer_id: {customer.id}, customer_phone: {customer.phone}, request_phone: {phone}"
                )
                matched_phone_customer = await customer_service.get_customer_by_phone_any_status(phone, tenant_id)
                if matched_phone_customer and matched_phone_customer.id != customer.id:
                    customer = matched_phone_customer
                    is_new_customer = False
                else:
                    customer = await customer_service.update_customer(
                        customer.id,
                        phone=phone,
                        name=customer.name or auto_member_name,
                    )
                    is_new_customer = False
            else:
                is_new_customer = True
            logger.info(f"新会员已建 - customer_id: {customer.id}, is_new_customer: {is_new_customer}")

            await self.rebind_identity(
                customer_id=customer.id,
                channel=CHANNEL_MINIAPP,
                channel_user_id=openid,
                phone=phone,
                unionid=unionid,
            )
            logger.info(f"重绑 identity（新会员）- customer_id: {customer.id}, openid: {openid}")

        return JoinCustomerResolution(
            outcome=JoinResolutionOutcome.SUCCESS,
            customer=customer,
            is_new_customer=is_new_customer,
            phone_switch_old_customer_id=phone_switch_old_customer_id,
            phone_changed_old_phone=phone_changed_old_phone,
            openid_conflict_existing_id=openid_conflict_existing_id,
        )
