from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.logger import logger
from app.core.tenant_context import TenantContext
from app.core.database import get_db
from app.models.tenant import Tenant
from app.schemas.entrance_code import (
    CreateEntranceCodeRequest,
    EntranceCodeResponse,
    RegenerateEntranceCodeRequest,
)
from app.services.entrance_code_service import EntranceCodeService
from app.services.tenant_service import TenantService
from app.core.response import RespVo, error_response, success_response

router = APIRouter(prefix="/api/v1/entrance-codes", tags=["入口码"])


@router.get("/resolve", response_model=RespVo)
async def resolve_entrance_code(scene: str, request: Request, db=Depends(get_db)):
    service = EntranceCodeService(db)
    
    entrance_code = await service.get_by_scene(scene)
    if not entrance_code:
        logger.info(f"[ENTRY_RESOLVE_RESULT] scene={scene} tenant_id='' entry_type='' channel='' table_no='' target_page='' success=False reason='NOT_FOUND'")
        return error_response(code=404, msg="入口码不存在")
    
    if entrance_code.status != 1:
        logger.info(f"[ENTRY_RESOLVE_RESULT] scene={scene} tenant_id={entrance_code.tenant_id} entry_type='' channel={entrance_code.channel} table_no='' target_page='' success=False reason='DISABLED'")
        return error_response(code=410, msg="入口码已停用")
    
    tenant = await TenantService(db).get_tenant(entrance_code.tenant_id)
    if not tenant:
        logger.info(f"[ENTRY_RESOLVE_RESULT] scene={scene} tenant_id={entrance_code.tenant_id} entry_type='' channel={entrance_code.channel} table_no='' target_page='' success=False reason='TENANT_NOT_FOUND'")
        return error_response(code=404, msg="商户不存在")
    
    if getattr(tenant, "status", 1) != 1:
        logger.info(f"[ENTRY_RESOLVE_RESULT] scene={scene} tenant_id={entrance_code.tenant_id} entry_type='' channel={entrance_code.channel} table_no='' target_page='' success=False reason='TENANT_CLOSED'")
        return error_response(code=403, msg="商户已停业")
    
    item = await service.resolve_scene(
        scene,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    if not item:
        logger.info(f"[ENTRY_RESOLVE_RESULT] scene={scene} tenant_id={entrance_code.tenant_id} entry_type='' channel={entrance_code.channel} table_no='' target_page='' success=False reason='RESOLVE_FAILED'")
        return error_response(code=404, msg="入口码不存在或已停用")
    
    channel = getattr(item, "channel", "STORE").upper()
    entry_type = getattr(item, "entry_type", None)
    table_no = getattr(item, "table_no", None)
    table_id = getattr(item, "table_id", None)
    order_mode = getattr(item, "order_mode", None)
    target_page = getattr(item, "target_page", None)
    
    if not entry_type:
        if channel == "TABLE":
            entry_type = "table"
        elif channel in ["POSTER", "DOUYIN"]:
            entry_type = channel.lower()
        elif channel == "STORE":
            if table_no:
                entry_type = "table"
            else:
                entry_type = "poster"
        else:
            entry_type = "poster"
    
    if not order_mode:
        if entry_type == "takeaway":
            order_mode = "takeaway"
        elif entry_type == "pickup":
            order_mode = "pickup"
        else:
            order_mode = "dine_in"
    
    if not target_page:
        if entry_type in ["poster", "douyin"]:
            target_page = "pages/index/index"
        else:
            target_page = "subpkg-order/pages/menu"
    
    if entry_type == "table" and not table_no:
        logger.info(f"[ENTRY_RESOLVE_RESULT] scene={scene} tenant_id={item.tenant_id} entry_type={entry_type} channel={channel} table_no='' target_page='' success=False reason='TABLE_CONTEXT_MISSING'")
        return error_response(code=422, msg="TABLE_CONTEXT_MISSING:桌码缺少桌号，请重新生成")
    
    if channel == "TABLE" and entry_type != "table":
        logger.info(f"[ENTRY_RESOLVE_RESULT] scene={scene} tenant_id={item.tenant_id} entry_type={entry_type} channel={channel} table_no={table_no} target_page='' success=False reason='CHANNEL_ENTRY_TYPE_MISMATCH'")
        return error_response(code=422, msg="入口类型异常，请重新扫码")
    
    TenantContext.set_tenant_id(item.tenant_id)

    logger.info(f"[ENTRY_RESOLVE_RESULT] scene={scene} tenant_id={item.tenant_id} entry_type={entry_type} channel={channel} table_no={table_no} target_page={target_page} success=True")

    staff_invite_code = None
    staff_name = None
    if entry_type == "staff_share" and getattr(item, "staff_id", None):
        from app.models.staff import Staff
        from sqlalchemy.future import select as _select

        staff_result = await db.execute(
            _select(Staff).filter(Staff.tenant_id == item.tenant_id, Staff.id == item.staff_id)
        )
        staff = staff_result.scalar_one_or_none()
        if staff:
            staff_invite_code = staff.invite_code
            staff_name = staff.name

    return success_response(
        data={
            "scene": item.scene,
            "tenant_id": item.tenant_id,
            "shop_name": tenant.name if tenant else "",
            "entry_type": entry_type,
            "table_id": str(table_id) if table_id else None,
            "table_no": table_no,
            "order_mode": order_mode,
            "channel": channel,
            "target_page": target_page,
            "status": item.status,
            "invite_code": staff_invite_code,
            "staff_name": staff_name,
        },
        msg="识别成功",
    )


@router.get("/summary", response_model=RespVo)
async def get_entrance_code_summary(db=Depends(get_db)):
    """Get entrance code summary statistics."""
    from app.services.entrance_code_service import EntranceCodeService
    
    items = await EntranceCodeService(db).list_entrance_codes(skip=0, limit=1000)
    
    code_count = len(items)
    scan_count = sum(getattr(item, "scan_count", 0) or 0 for item in items)
    member_count = sum(getattr(item, "member_count", 0) or 0 for item in items)
    
    return success_response(data={
        "code_count": code_count,
        "scan_count": scan_count,
        "member_count": member_count,
    })


@router.post("/", response_model=RespVo)
async def create_entrance_code(data: CreateEntranceCodeRequest, db=Depends(get_db)):
    """Create a new entrance code."""
    from app.services.entrance_code_service import EntranceCodeService
    
    try:
        item = await EntranceCodeService(db).create_entrance_code(
            name=data.name,
            channel=data.channel,
            coupon_template_id=data.coupon_template_id,
            page=data.page,
            env_version=data.env_version,
            table_no=data.table_no,
            entry_type=data.entry_type,
            order_mode=data.order_mode,
            table_id=data.table_id,
            target_page=data.target_page,
            zone_type=data.zone_type,
        )
    except ValueError as exc:
        return error_response(code=404, msg=str(exc))
    return success_response(data=EntranceCodeResponse.model_validate(item))


@router.get("/", response_model=RespVo)
async def list_entrance_codes(
    db=Depends(get_db),
    page: Annotated[int, "Page number"] = 1,
    page_size: Annotated[int, "Page size"] = 20,
    channel: Annotated[str | None, "Filter by channel"] = None,
    status: Annotated[int | None, "Filter by status"] = None,
):
    """List entrance codes."""
    from app.services.entrance_code_service import EntranceCodeService
    
    items = await EntranceCodeService(db).list_entrance_codes(
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return success_response(data={"items": [EntranceCodeResponse.model_validate(i) for i in items], "total": len(items)})


@router.get("/{code_id}", response_model=RespVo)
async def get_entrance_code(code_id: int, db=Depends(get_db)):
    """Get entrance code by ID."""
    from app.services.entrance_code_service import EntranceCodeService
    
    item = await EntranceCodeService(db).get_by_id(code_id)
    if not item:
        return error_response(code=404, msg="入口码不存在")
    return success_response(data=EntranceCodeResponse.model_validate(item))


@router.delete("/{code_id}", response_model=RespVo)
async def delete_entrance_code(code_id: int, db=Depends(get_db)):
    """Delete entrance code."""
    from app.services.entrance_code_service import EntranceCodeService
    
    success = await EntranceCodeService(db).delete_entrance_code(code_id)
    if not success:
        return error_response(code=404, msg="入口码不存在")
    return success_response(msg="删除成功")


@router.put("/{code_id}/regenerate", response_model=RespVo)
async def regenerate_entrance_code(code_id: int, data: RegenerateEntranceCodeRequest, db=Depends(get_db)):
    """Regenerate entrance code."""
    from app.services.entrance_code_service import EntranceCodeService
    
    item = await EntranceCodeService(db).regenerate_entrance_code(code_id)
    if not item:
        return error_response(code=404, msg="入口码不存在")
    return success_response(data=EntranceCodeResponse.model_validate(item))
