from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import build_page, normalize_pagination
from app.core.response import RespVo, error_response, success_response
from app.services.channel_entry_service import ChannelEntryService

router = APIRouter(prefix="/api/v1/channel-entries", tags=["渠道入口管理"])


def serialize_entry(entry, coupon_name=None):
    return {
        "id": str(entry.id),
        "tenant_id": entry.tenant_id,
        "name": entry.name,
        "channel_code": entry.channel_code,
        "landing_title": entry.landing_title,
        "landing_subtitle": entry.landing_subtitle,
        "cover_image": entry.cover_image,
        "coupon_template_id": str(entry.coupon_template_id) if entry.coupon_template_id else None,
        "coupon_name": coupon_name,
        "mini_program_qrcode_url": entry.mini_program_qrcode_url,
        "h5_url": entry.h5_url,
        "qrcode_url": entry.qrcode_url,
        "status": entry.status,
        "visit_count": entry.visit_count or 0,
        "scan_count": entry.scan_count or 0,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


@router.get("/", response_model=RespVo)
async def list_entries(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    skip, limit = normalize_pagination(skip, limit)
    service = ChannelEntryService(db)
    entries, total = await service.list_entries(skip, limit)

    from app.models.coupon_template import CouponTemplate
    from sqlalchemy.future import select

    coupon_ids = [e.coupon_template_id for e in entries if e.coupon_template_id]
    coupon_map = {}
    if coupon_ids:
        result = await db.execute(
            select(CouponTemplate.id, CouponTemplate.name).filter(
                CouponTemplate.id.in_(coupon_ids),
                CouponTemplate.tenant_id == entries[0].tenant_id,
            )
        )
        for row in result.all():
            coupon_map[row[0]] = row[1]

    return success_response(
        data=build_page(
            [serialize_entry(e, coupon_map.get(e.coupon_template_id)) for e in entries],
            total,
            skip,
            limit,
        ),
        msg="ok",
    )


@router.get("/{entry_id}", response_model=RespVo)
async def get_entry(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = ChannelEntryService(db)
    entry = await service.get_entry(entry_id)
    if not entry:
        return error_response(code=404, msg="渠道入口不存在")

    coupon_name = None
    if entry.coupon_template_id:
        from app.models.coupon_template import CouponTemplate
        from sqlalchemy.future import select

        result = await db.execute(
            select(CouponTemplate.name).filter(
                CouponTemplate.id == entry.coupon_template_id,
                CouponTemplate.tenant_id == entry.tenant_id,
            )
        )
        coupon_name = result.scalar_one_or_none()

    return success_response(data=serialize_entry(entry, coupon_name), msg="ok")


@router.post("/", response_model=RespVo)
async def create_entry(
    request: Request,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    service = ChannelEntryService(db)
    try:
        entry = await service.create_entry(
            name=data.get("name"),
            channel_code=data.get("channel_code"),
            landing_title=data.get("landing_title"),
            landing_subtitle=data.get("landing_subtitle"),
            cover_image=data.get("cover_image"),
            coupon_template_id=data.get("coupon_template_id"),
            mini_program_qrcode_url=data.get("mini_program_qrcode_url"),
            status=data.get("status", 1),
        )
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return success_response(data=serialize_entry(entry), msg="创建成功")


@router.put("/{entry_id}", response_model=RespVo)
async def update_entry(
    request: Request,
    entry_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    service = ChannelEntryService(db)
    try:
        entry = await service.update_entry(
            entry_id,
            name=data.get("name"),
            landing_title=data.get("landing_title"),
            landing_subtitle=data.get("landing_subtitle"),
            cover_image=data.get("cover_image"),
            coupon_template_id=data.get("coupon_template_id"),
            status=data.get("status"),
        )
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    if not entry:
        return error_response(code=404, msg="渠道入口不存在")
    return success_response(data=serialize_entry(entry), msg="更新成功")


@router.delete("/{entry_id}", response_model=RespVo)
async def delete_entry(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = ChannelEntryService(db)
    result = await service.delete_entry(entry_id)
    if not result:
        return error_response(code=404, msg="渠道入口不存在")
    return success_response(msg="删除成功")


@router.patch("/{entry_id}/status", response_model=RespVo)
async def toggle_status(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = ChannelEntryService(db)
    entry = await service.toggle_status(entry_id)
    if not entry:
        return error_response(code=404, msg="渠道入口不存在")
    return success_response(data=serialize_entry(entry), msg="状态已更新")


@router.get("/options/channels", response_model=RespVo)
async def get_channel_options(request: Request, db: AsyncSession = Depends(get_db)):
    return success_response(data=ChannelEntryService.get_channel_options(), msg="ok")
