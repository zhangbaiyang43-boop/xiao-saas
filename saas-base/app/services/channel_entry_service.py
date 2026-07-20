import json
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.future import select

from app.config import settings
from app.models.channel_entry import ChannelEntry, ChannelEntryVisitLog
from app.models.coupon_template import CouponTemplate
from app.services.base_service import BaseService
from app.services.qrcode_service import QRCodeService
from app.utils.id_generator import generate_snowflake_id


CHANNEL_OPTIONS = [
    {"code": "douyin", "name": "抖音"},
    {"code": "kuaishou", "name": "快手"},
    {"code": "meituan", "name": "美团"},
    {"code": "eleme", "name": "饿了么"},
    {"code": "moments", "name": "朋友圈"},
    {"code": "offline", "name": "线下门店"},
    {"code": "custom", "name": "自定义"},
]


class ChannelEntryService(BaseService):
    async def list_entries(self, skip: int = 0, limit: int = 100) -> tuple:
        tenant_id = self.require_tenant_id()
        query = (
            select(ChannelEntry)
            .filter(ChannelEntry.tenant_id == tenant_id)
            .order_by(ChannelEntry.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        entries = result.scalars().all()

        count_result = await self.db.execute(
            select(func.count()).select_from(ChannelEntry).filter(ChannelEntry.tenant_id == tenant_id)
        )
        total = count_result.scalar()
        return list(entries), int(total)

    async def get_entry(self, entry_id: int) -> Optional[ChannelEntry]:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(ChannelEntry).filter(
                ChannelEntry.id == entry_id,
                ChannelEntry.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_entry_by_h5_url(self, h5_url: str) -> Optional[ChannelEntry]:
        result = await self.db.execute(select(ChannelEntry).filter(ChannelEntry.h5_url == h5_url))
        return result.scalar_one_or_none()

    async def create_entry(
        self,
        name: str,
        channel_code: str,
        landing_title: str = None,
        landing_subtitle: str = None,
        cover_image: str = None,
        coupon_template_id: int = None,
        mini_program_qrcode_url: str = None,
        status: int = 1,
    ) -> ChannelEntry:
        tenant_id = self.require_tenant_id()

        entry_id = generate_snowflake_id()
        h5_url = QRCodeService.generate_h5_url(
            QRCodeService.get_h5_base_url(),
            entry_id,
            channel_code
        )

        qrcode_file_name = f"{entry_id}.png"
        qrcode_url = await QRCodeService.generate_qrcode_file(h5_url, qrcode_file_name)

        entry = ChannelEntry(
            id=entry_id,
            tenant_id=tenant_id,
            name=name,
            channel_code=channel_code,
            landing_title=landing_title,
            landing_subtitle=landing_subtitle,
            cover_image=cover_image,
            coupon_template_id=coupon_template_id,
            mini_program_qrcode_url=mini_program_qrcode_url,
            h5_url=h5_url,
            qrcode_url=qrcode_url,
            status=status,
            visit_count=0,
            scan_count=0,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def update_entry(
        self,
        entry_id: int,
        name: str = None,
        landing_title: str = None,
        landing_subtitle: str = None,
        cover_image: str = None,
        coupon_template_id: int = None,
        status: int = None,
    ) -> Optional[ChannelEntry]:
        entry = await self.get_entry(entry_id)
        if not entry:
            return None

        if name is not None:
            entry.name = name
        if landing_title is not None:
            entry.landing_title = landing_title
        if landing_subtitle is not None:
            entry.landing_subtitle = landing_subtitle
        if cover_image is not None:
            entry.cover_image = cover_image
        if coupon_template_id is not None:
            entry.coupon_template_id = coupon_template_id
        if status is not None:
            entry.status = status

        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def delete_entry(self, entry_id: int) -> bool:
        entry = await self.get_entry(entry_id)
        if not entry:
            return False
        await self.db.delete(entry)
        await self.db.commit()
        return True

    async def toggle_status(self, entry_id: int) -> Optional[ChannelEntry]:
        entry = await self.get_entry(entry_id)
        if not entry:
            return None
        entry.status = 0 if entry.status == 1 else 1
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def record_visit(
        self,
        entry_id: int,
        user_agent: str = None,
        referer: str = None,
        ip: str = None,
        query_params: dict = None,
    ) -> Optional[ChannelEntry]:
        entry = await self.get_public_entry(entry_id)
        if not entry or entry.status != 1:
            return None

        entry.visit_count = int(entry.visit_count or 0) + 1

        visit_log = ChannelEntryVisitLog(
            id=generate_snowflake_id(),
            tenant_id=entry.tenant_id,
            entry_id=entry_id,
            channel_code=entry.channel_code,
            user_agent=user_agent[:1024] if user_agent else None,
            referer=referer[:2048] if referer else None,
            ip=ip,
            query_params=json.dumps(query_params) if query_params else None,
        )
        self.db.add(visit_log)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def get_public_entry(self, entry_id: int) -> Optional[ChannelEntry]:
        result = await self.db.execute(
            select(ChannelEntry).filter(
                ChannelEntry.id == entry_id,
                ChannelEntry.status == 1,
            )
        )
        return result.scalar_one_or_none()

    async def get_entry_with_coupon(self, entry_id: int) -> Optional[dict]:
        entry = await self.get_public_entry(entry_id)
        if not entry:
            return None

        coupon_template = None
        if entry.coupon_template_id:
            result = await self.db.execute(
                select(CouponTemplate).filter(CouponTemplate.id == entry.coupon_template_id)
            )
            template = result.scalar_one_or_none()
            if template and template.status == 1:
                coupon_template = {
                    "id": str(template.id),
                    "name": template.name,
                    "type": template.type,
                    "value": float(template.value or 0),
                    "min_amount": float(template.min_amount or 0),
                    "description": template.description,
                    "end_time": template.end_time.isoformat() if template.end_time else None,
                }

        return {
            "id": str(entry.id),
            "tenant_id": entry.tenant_id,
            "name": entry.name,
            "channel_code": entry.channel_code,
            "landing_title": entry.landing_title,
            "landing_subtitle": entry.landing_subtitle,
            "cover_image": entry.cover_image,
            "mini_program_qrcode_url": entry.mini_program_qrcode_url,
            "coupon": coupon_template,
        }

    @staticmethod
    def get_channel_options() -> list:
        return CHANNEL_OPTIONS
