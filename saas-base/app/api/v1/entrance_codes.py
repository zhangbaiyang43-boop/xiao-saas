import base64
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.core.logger import logger
from app.core.tenant_context import TenantContext
from app.core.database import get_db
from app.models.tenant import Tenant
from app.schemas.entrance_code import (
    BatchDownloadEntranceCodeRequest,
    CreateEntranceCodeRequest,
    EntranceCodeResponse,
    RegenerateEntranceCodeRequest,
    TableStickerExportRequest,
    UpdateEntranceCodeStatusRequest,
)
from app.services.entrance_code_service import EntranceCodeService
import app.services.table_sticker_export_service as table_sticker_export_service
from app.services.tenant_service import TenantService
from app.core.response import RespVo, error_response, success_response

router = APIRouter(prefix="/api/v1/entrance-codes", tags=["入口码"])


@router.get("/resolve", response_model=RespVo)
async def resolve_entrance_code(
    scene: str,
    request: Request,
    db=Depends(get_db),
    client_id: str | None = None,
    participant_token: str | None = None,
):
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

    # 扫桌码进店，顾客十有八九马上就要建本桌身份（entry/index.vue 之前是先拿这个接口的
    # 结果、再单独调一次 /dining-sessions/resolve，两次串行网络往返）。这里顺带把会话建好，
    # 一起吐给前端，省掉扫码到进菜单页之间的一次网络往返。只在 entry_type=="table" 且前端
    # 带了 client_id 时才做——没带 client_id 说明前端还是没升级到能合并请求的版本，或者
    # 这次入口本来就不是桌码场景，两种情况都不该在这里硬凑一个身份出来。
    # 会话建立失败（比如桌台过期扫描踩到竞态）不能连累入口码识别本身失败：吞掉异常，
    # 前端拿不到这几个字段时会自动退回到单独调用 /dining-sessions/resolve 的老路径。
    dining_session_data = {}
    if entry_type == "table" and table_no and client_id:
        try:
            from app.services.dining_session_service import DiningSessionService

            customer_id = getattr(request.state, "customer_id", None)
            openid = getattr(request.state, "openid", None)
            session_data = await DiningSessionService(db).resolve_session(
                tenant_id=item.tenant_id,
                table_no=table_no,
                client_id=client_id,
                participant_token=participant_token,
                customer_id=int(customer_id) if customer_id else None,
                openid=openid,
            )
            await db.commit()
            dining_session_data = {
                "dining_session_id": session_data["dining_session_id"],
                "participant_id": session_data["participant_id"],
                "participant_token": session_data["participant_token"],
                "client_id": session_data["client_id"],
                "session_status": session_data["session_status"],
            }
        except Exception as exc:
            await db.rollback()
            logger.warning(f"[ENTRY_RESOLVE_SESSION_MERGE_FAILED] scene={scene} tenant_id={item.tenant_id} table_no={table_no} error={exc}")

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
            **dining_session_data,
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


@router.post("/batch-download")
async def batch_download_entrance_codes(data: BatchDownloadEntranceCodeRequest, db=Depends(get_db)):
    """Bundle the selected codes' existing images into one zip (no re-render)."""
    from urllib.parse import quote

    from fastapi.responses import Response

    from app.services.entrance_code_service import EntranceCodeService

    try:
        filename, blob = await EntranceCodeService(db).build_codes_zip(data.ids)
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


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


@router.post("/table-stickers/export")
async def export_table_stickers(data: TableStickerExportRequest, db=Depends(get_db)):
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        return error_response(code=401, msg="未登录或商户信息已失效")

    service = table_sticker_export_service.TableStickerExportService(db)
    try:
        codes = await service.load_valid_codes(tenant_id, data.entrance_code_ids)
        tenant = await TenantService(db).get_tenant(tenant_id)
        artifact = await run_in_threadpool(
            service.build_bundle,
            codes,
            tenant.name if tenant else "商户",
        )
    except table_sticker_export_service.TableStickerExportError as exc:
        logger.warning(
            f"[TABLE_STICKER_EXPORT] tenant_id={tenant_id} "
            f"count={len(data.entrance_code_ids)} success=False error_code={exc.code}"
        )
        return error_response(code=422, msg=exc.message)

    # ZIP 以 base64 塞进普通 JSON 返回，不走二进制响应体：
    # 三层自定义中间件（Auth/Tenant/Logging）都是 BaseHTTPMiddleware，加上 nginx/WAF
    # 对 application/zip + attachment 的处理，几 MB 的二进制响应体在链路上会被打断，
    # 浏览器报 net::ERR_FAILED（后端却记 success）。JSON 响应和其它所有接口同路径，稳。
    try:
        zip_bytes = artifact.zip_path.read_bytes()
    finally:
        artifact.cleanup()

    logger.info(
        f"[TABLE_STICKER_EXPORT] tenant_id={tenant_id} count={len(codes)} "
        f"success=True bytes={len(zip_bytes)}"
    )
    return success_response(data={
        "filename": artifact.download_name,
        "size": len(zip_bytes),
        "content_base64": base64.b64encode(zip_bytes).decode("ascii"),
    })


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

    try:
        success = await EntranceCodeService(db).delete_entrance_code(code_id)
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    if not success:
        return error_response(code=404, msg="入口码不存在")
    return success_response(msg="删除成功")


@router.put("/{code_id}/status", response_model=RespVo)
async def update_entrance_code_status(
    code_id: int, data: UpdateEntranceCodeStatusRequest, db=Depends(get_db)
):
    """Enable (1) or disable (0) an entrance code without deleting it."""
    from app.services.entrance_code_service import EntranceCodeService

    item = await EntranceCodeService(db).update_status(code_id, data.status)
    if not item:
        return error_response(code=404, msg="入口码不存在")
    return success_response(data=EntranceCodeResponse.model_validate(item))


@router.put("/{code_id}/regenerate", response_model=RespVo)
async def regenerate_entrance_code(code_id: int, data: RegenerateEntranceCodeRequest, db=Depends(get_db)):
    """Regenerate entrance code."""
    from app.services.entrance_code_service import EntranceCodeService
    
    item = await EntranceCodeService(db).regenerate_entrance_code(code_id)
    if not item:
        return error_response(code=404, msg="入口码不存在")
    return success_response(data=EntranceCodeResponse.model_validate(item))
