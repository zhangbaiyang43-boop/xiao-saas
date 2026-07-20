import random

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.base_service import BaseService

# 邀请码字符表：大写字母 + 数字，去掉易混淆字符 0/O/1/I/L
_INVITE_CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def _make_short_invite_code() -> str:
    """生成 6 位随机短邀请码。"""
    return ''.join(random.choices(_INVITE_CODE_CHARS, k=6))


class CustomerService(BaseService):
    async def get_customer(self, customer_id: int):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Customer).filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id,
                Customer.status == 1
            )
        )
        return result.scalars().first()

    async def get_customer_any_status(self, customer_id: int):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Customer).filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id
            )
        )
        return result.scalars().first()

    async def get_customer_by_phone(self, phone, tenant_id):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        phone = str(phone).strip() if phone else phone
        result = await self.db.execute(
            select(Customer).filter(
                Customer.phone == phone,
                Customer.tenant_id == tenant_id,
                Customer.status == 1
            )
        )
        return result.scalars().first()

    async def get_customer_by_phone_any_status(self, phone, tenant_id):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        phone = str(phone).strip() if phone else phone
        result = await self.db.execute(
            select(Customer).filter(
                Customer.phone == phone,
                Customer.tenant_id == tenant_id
            )
        )
        return result.scalars().first()

    async def get_customer_identity_phone(self, customer_id: int):
        from sqlalchemy.future import select
        from app.models.customer_identity import CustomerIdentity
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CustomerIdentity.phone)
            .filter(
                CustomerIdentity.customer_id == customer_id,
                CustomerIdentity.tenant_id == tenant_id,
                CustomerIdentity.phone.isnot(None),
            )
            .order_by(CustomerIdentity.bind_time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_customer_by_openid(self, openid, tenant_id):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        from app.models.customer_identity import CustomerIdentity
        result = await self.db.execute(
            select(Customer).join(CustomerIdentity).filter(
                CustomerIdentity.channel == "miniapp",
                CustomerIdentity.channel_user_id == openid,
                Customer.tenant_id == tenant_id,
                Customer.status == 1
            )
        )
        return result.scalars().first()

    async def get_customer_by_openid_any_status(self, openid, tenant_id):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        result = await self.db.execute(
            select(Customer).filter(
                Customer.openid == openid,
                Customer.tenant_id == tenant_id,
            )
        )
        return result.scalars().first()

    async def restore_customer(self, customer, **kwargs):
        if not customer:
            return None

        customer.status = 1
        customer.deleted_at = None
        for key, value in kwargs.items():
            if value is not None and hasattr(customer, key):
                setattr(customer, key, value)

        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def create_customer(self, tenant_id, **kwargs):
        from sqlalchemy.future import select
        from sqlalchemy.exc import IntegrityError
        from app.models.customer import Customer

        if kwargs.get("phone"):
            kwargs["phone"] = str(kwargs["phone"]).strip()

        # 新用户自动分配短邀请码（不校验唯一性，32^6≈10亿空间，小模商户碰撞概率可忽略）
        if "short_invite_code" not in kwargs:
            kwargs["short_invite_code"] = _make_short_invite_code()

        customer = Customer(tenant_id=tenant_id, **kwargs)
        self.db.add(customer)
        
        try:
            await self.db.commit()
            await self.db.refresh(customer)
            return customer
        except IntegrityError as e:
            # 唯一索引冲突，说明用户已存在，回滚并查询已存在的用户
            await self.db.rollback()
            
            # 根据 openid 或 phone 查询已存在的客户
            openid = kwargs.get('openid')
            phone = kwargs.get('phone')
            
            if phone:
                result = await self.db.execute(
                    select(Customer).filter(
                        Customer.tenant_id == tenant_id,
                        Customer.phone == phone,
                        Customer.status != -1
                    )
                )
                existing = result.scalars().first()
                if existing:
                    if existing.status == -1:
                        return await self.restore_customer(existing, **kwargs)
                    return existing

            if openid:
                result = await self.db.execute(
                    select(Customer).filter(
                        Customer.tenant_id == tenant_id,
                        Customer.openid == openid,
                        Customer.status != -1
                    )
                )
                existing = result.scalars().first()
                if existing:
                    if existing.status == -1:
                        return await self.restore_customer(existing, **kwargs)
                    if phone and existing.phone != phone:
                        existing.phone = phone
                        if kwargs.get("name") and not existing.name:
                            existing.name = kwargs.get("name")
                        await self.db.commit()
                        await self.db.refresh(existing)
                    return existing

                existing = await self.get_customer_by_openid_any_status(openid, tenant_id)
                if existing:
                    return await self.restore_customer(existing, **kwargs)
            
            # 如果还是找不到，重新抛出异常
            raise e

    async def update_customer(self, customer_id, **kwargs):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Customer).filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id,
                Customer.status != -1
            )
        )
        customer = result.scalars().first()
        if not customer:
            return None

        for key, value in kwargs.items():
            setattr(customer, key, value)

        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def delete_customer(self, customer_id):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Customer).filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id
            )
        )
        customer = result.scalars().first()
        if not customer:
            return False

        customer.status = -1
        await self.db.commit()
        return True

    async def list_customers(self, tenant_id, phone=None, name=None, tag=None, skip=0, limit=100):
        from sqlalchemy import func, or_
        from sqlalchemy.future import select
        from app.models.customer import Customer

        query = select(Customer).filter(Customer.tenant_id == tenant_id)
        if not (phone or name):
            query = query.filter(Customer.status == 1)

        if phone and name and phone == name:
            query = query.filter(
                or_(
                    Customer.phone.like(f"%{phone}%"),
                    Customer.name.like(f"%{name}%")
                )
            )
        else:
            if phone:
                query = query.filter(Customer.phone.like(f"%{phone}%"))
            if name:
                query = query.filter(Customer.name.like(f"%{name}%"))

        if tag:
            query = query.filter(Customer.tags.contains([tag]))

        total_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = total_result.scalar()

        query = query.order_by(Customer.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        customers = result.scalars().all()

        return list(customers), total

    async def get_customer_source(self, customer_id):
        from sqlalchemy.future import select
        from app.models.customer_identity import CustomerIdentity
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CustomerIdentity.channel)
            .filter(
                CustomerIdentity.customer_id == customer_id,
                CustomerIdentity.tenant_id == tenant_id
            )
            .order_by(CustomerIdentity.bind_time.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def merge_customers(self, source_customer_id, target_customer_id):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        from app.models.customer_identity import CustomerIdentity

        source = await self.db.execute(
            select(Customer).filter(Customer.id == source_customer_id)
        )
        source = source.scalars().first()

        target = await self.db.execute(
            select(Customer).filter(Customer.id == target_customer_id)
        )
        target = target.scalars().first()

        if not source or not target:
            return None

        if str(source.tenant_id) != str(target.tenant_id):
            return None

        await self.db.execute(
            CustomerIdentity.__table__.update()
            .where(CustomerIdentity.customer_id == source.id)
            .values(customer_id=target.id)
        )

        source.status = -1
        await self.db.commit()
        await self.db.refresh(target)

        return target

    async def get_customer_by_external_userid(self, external_userid, tenant_id):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        from app.models.customer_identity import CustomerIdentity
        result = await self.db.execute(
            select(Customer).join(CustomerIdentity).filter(
                CustomerIdentity.channel == "wecom",
                CustomerIdentity.channel_user_id == external_userid,
                Customer.tenant_id == tenant_id,
                Customer.status != -1
            )
        )
        return result.scalars().first()

    async def get_customers_by_ids(self, customer_ids, tenant_id):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        result = await self.db.execute(
            select(Customer).filter(
                Customer.id.in_(customer_ids),
                Customer.tenant_id == tenant_id,
                Customer.status != -1
            )
        )
        return result.scalars().all()

    async def search_customers(self, tenant_id, keyword, limit=20):
        from sqlalchemy import or_
        from sqlalchemy.future import select
        from app.models.customer import Customer
        query = select(Customer).filter(
            Customer.tenant_id == tenant_id,
            Customer.status != -1,
            or_(
                Customer.name.like(f"%{keyword}%"),
                Customer.phone.like(f"%{keyword}%")
            )
        ).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_customers(self, tenant_id):
        from sqlalchemy import func
        from sqlalchemy.future import select
        from app.models.customer import Customer
        result = await self.db.execute(
            select(func.count()).filter(
                Customer.tenant_id == tenant_id,
                Customer.status != -1
            )
        )
        return result.scalar()

    async def count_new_customers_today(self, tenant_id):
        from datetime import datetime, timezone
        from sqlalchemy import func
        from sqlalchemy.future import select
        from app.models.customer import Customer
        
        today = datetime.now(timezone.utc).date()
        result = await self.db.execute(
            select(func.count()).filter(
                Customer.tenant_id == tenant_id,
                Customer.status != -1,
                func.date(Customer.created_at) == today
            )
        )
        return result.scalar()

    async def count_active_customers_this_month(self, tenant_id):
        from datetime import datetime, timezone
        from sqlalchemy import func
        from sqlalchemy.future import select
        from app.models.customer import Customer
        
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(
            select(func.count(func.distinct(Customer.id))).filter(
                Customer.tenant_id == tenant_id,
                Customer.status != -1,
                Customer.last_active_at >= month_start
            )
        )
        return result.scalar()

    async def get_birthday_customers(self, tenant_id, month, day):
        from sqlalchemy import func
        from sqlalchemy.future import select
        from app.models.customer import Customer
        result = await self.db.execute(
            select(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.status != -1,
                func.extract('month', Customer.birthday) == month,
                func.extract('day', Customer.birthday) == day
            )
        )
        return result.scalars().all()

    async def add_tag_to_customer(self, customer_id, tag):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        result = await self.db.execute(
            select(Customer).filter(Customer.id == customer_id)
        )
        customer = result.scalars().first()
        if not customer:
            return False

        if tag not in customer.tags:
            customer.tags.append(tag)
            await self.db.commit()

        return True

    async def remove_tag_from_customer(self, customer_id, tag):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        result = await self.db.execute(
            select(Customer).filter(Customer.id == customer_id)
        )
        customer = result.scalars().first()
        if not customer:
            return False

        if tag in customer.tags:
            customer.tags.remove(tag)
            await self.db.commit()

        return True

    async def batch_update_customers(self, customer_ids, **kwargs):
        from app.models.customer import Customer
        result = await self.db.execute(
            Customer.__table__.update()
            .where(Customer.id.in_(customer_ids))
            .values(**kwargs)
        )
        await self.db.commit()
        return result.rowcount

    async def get_top_customers_by_consumption(self, tenant_id, limit=10):
        from sqlalchemy import func
        from sqlalchemy.future import select
        from app.models.customer import Customer
        from app.models.consumption import Consumption
        
        subq = select(
            Consumption.customer_id,
            func.sum(Consumption.amount).label('total_amount')
        ).filter(
            Consumption.tenant_id == tenant_id,
            Consumption.status == 1
        ).group_by(Consumption.customer_id).subquery()

        query = select(Customer).join(
            subq, Customer.id == subq.c.customer_id
        ).filter(
            Customer.tenant_id == tenant_id,
            Customer.status != -1
        ).order_by(subq.c.total_amount.desc()).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def list_tags(self):
        from app.core.tenant_context import TenantContext
        tenant_id = TenantContext.get_tenant_id()
        from sqlalchemy import func, distinct
        from sqlalchemy.future import select
        from app.models.customer import Customer
        
        result = await self.db.execute(
            select(Customer.tags).filter(
                Customer.tenant_id == tenant_id,
                Customer.status != -1
            )
        )
        all_tags = set()
        for tags in result.scalars().all():
            if tags:
                all_tags.update(tags)
        return list(all_tags)
    
    async def set_customer_status(self, customer_id, status):
        from sqlalchemy.future import select
        from app.models.customer import Customer
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Customer).filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id
            )
        )
        customer = result.scalars().first()
        if not customer:
            return None
        customer.status = status
        if status == 1:
            customer.deleted_at = None
        await self.db.commit()
        await self.db.refresh(customer)
        return customer
    
    async def soft_delete_customer(self, customer_id):
        from datetime import datetime
        from sqlalchemy.future import select
        from app.models.customer import Customer
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Customer).filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id
            )
        )
        customer = result.scalars().first()
        if not customer:
            return None
        customer.status = -1
        customer.deleted_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(customer)
        return customer
    
    async def list_customer_identities(self, customer_id):
        from sqlalchemy.future import select
        from app.models.customer_identity import CustomerIdentity
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CustomerIdentity).filter(
                CustomerIdentity.customer_id == customer_id,
                CustomerIdentity.tenant_id == tenant_id
            )
        )
        return result.scalars().all()
    
    async def get_customer_timeline(self, customer_id):
        from sqlalchemy.future import select
        from app.models.consumption import Consumption
        result = await self.db.execute(
            select(Consumption).filter(
                Consumption.customer_id == customer_id,
                Consumption.status == 1
            ).order_by(Consumption.created_at.desc())
        )
        consumptions = result.scalars().all()
        timeline = []
        for c in consumptions:
            timeline.append({
                'type': 'consumption',
                'id': str(c.id),
                'amount': float(c.amount) if c.amount else 0,
                'created_at': c.created_at,
            })
        return timeline
