import logging
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)
from pydantic import BaseModel as PydanticBase
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified
from typing import Optional

from app.config import settings
from app.core.database import get_db
from app.core.response import error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.dish_library_item import DishLibraryItem
from app.models.menu_item import MenuItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/api/v1", tags=["点餐"])


class MenuItemCreate(PydanticBase):
    name: str
    description: Optional[str] = None
    price: float
    category: Optional[str] = "默认"
    emoji: Optional[str] = "🍽️"
    available: Optional[bool] = True
    sort_order: Optional[int] = 0
    image: Optional[str] = None
    sales_count: Optional[int] = None
    tags: Optional[str] = None
    original_price: Optional[float] = None
    stock: Optional[int] = None
    spec_groups: Optional[list] = None


class MenuItemUpdate(PydanticBase):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    emoji: Optional[str] = None
    available: Optional[bool] = None
    sort_order: Optional[int] = None
    image: Optional[str] = None
    sales_count: Optional[int] = None
    tags: Optional[str] = None
    original_price: Optional[float] = None
    stock: Optional[int] = None
    spec_groups: Optional[list] = None


async def load_menu_specs(db: AsyncSession, tenant_id: str) -> dict:
    result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
    config = result.scalar_one_or_none()
    business_info = (config.business_info or {}) if config else {}
    specs = business_info.get("menu_item_specs") or {}
    return specs if isinstance(specs, dict) else {}


async def save_menu_specs(db: AsyncSession, tenant_id: str, item_id: int, spec_groups: Optional[list]) -> None:
    config = await TenantService(db).ensure_tenant_config(tenant_id)
    business_info = dict(config.business_info or {})
    specs = dict(business_info.get("menu_item_specs") or {})
    key = str(item_id)
    if spec_groups:
        specs[key] = spec_groups
    else:
        specs.pop(key, None)
    business_info["menu_item_specs"] = specs
    config.business_info = business_info
    flag_modified(config, "business_info")


def serialize_item(item: MenuItem, specs_map: Optional[dict] = None):
    raw_tags = item.tags or ""
    tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []
    spec_groups = (specs_map or {}).get(str(item.id)) or []
    return {
        "id": str(item.id),
        "name": item.name,
        "description": item.description,
        "price": float(item.price),
        "category": item.category,
        "emoji": item.emoji,
        "available": item.available,
        "sort_order": item.sort_order,
        "image": item.image,
        "sales_count": item.sales_count,
        "tags": tags_list,
        "original_price": float(item.original_price) if item.original_price else None,
        "stock": item.stock,  # None=不限, 0=售罄, >0=剩余
        "sold_out": item.stock is not None and item.stock <= 0,
        "spec_groups": spec_groups,
        "has_options": bool(spec_groups),
    }


@router.get("/shop/info")
async def get_shop_info(shop: str, request: Request, db: AsyncSession = Depends(get_db)):
    TenantContext.set_tenant_id(shop)
    svc = TenantService(db)
    tenant = await svc.get_tenant(shop)
    if not tenant or not tenant.status:
        return error_response(code=404, msg="商家不存在")
    config = await svc.get_tenant_config(shop)
    biz = (config.business_info or {}) if config else {}

    # 静默发放进店券、新客券预览、邀请奖励开关三者互不依赖，并发执行以缩短
    # shop/info 响应时间；各任务使用独立 AsyncSession，不能共用外层 db。
    import asyncio

    from app.core.database import AsyncSessionLocal
    from app.services.commission_service import CommissionService
    from app.services.coupon_service import CouponService

    customer_id = getattr(request.state, "customer_id", None)

    async def _issue_entry_coupon():
        if not customer_id:
            return None
        try:
            async with AsyncSessionLocal() as session:
                cs = CouponService(session)
                return await cs.issue_entry_coupon(int(customer_id))
        except Exception:
            return None

    async def _preview_new_customer_coupon():
        try:
            async with AsyncSessionLocal() as session:
                preview_cs = CouponService(session)
                preview_cs.set_tenant_id(shop)
                return await preview_cs.preview_new_customer_coupon()
        except Exception:
            return None

    async def _get_invite_reward_enabled():
        try:
            async with AsyncSessionLocal() as session:
                dist_cs = CommissionService(session)
                dist_cs.set_tenant_id(shop)
                distribution_rules = await dist_cs.get_distribution_rules()
                return bool(distribution_rules.get("invite_reward_enabled", False))
        except Exception:
            return False

    entry_coupon, new_customer_coupon_preview, invite_reward_enabled = await asyncio.gather(
        _issue_entry_coupon(),
        _preview_new_customer_coupon(),
        _get_invite_reward_enabled(),
    )

    return success_response(data={
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "logo": tenant.logo_url,
        "address": tenant.address,
        "is_open": biz.get("is_open", True),
        "business_hours": biz.get("business_hours", ""),
        "dine_in_enabled": biz.get("dine_in_enabled", True),
        "pickup_enabled": biz.get("pickup_enabled", False),
        "delivery_enabled": biz.get("delivery_enabled", False),
        "delivery_fee": biz.get("delivery_fee", 0),
        "payment_mode": getattr(tenant, "payment_mode", "prepay") or "prepay",
        "remark_chips": biz.get("remark_chips", ["不要辣", "微辣", "不要香菜", "不要葱", "少盐", "打包"]),
        "order_remark_chips": biz.get("order_remark_chips", ["一起上菜", "全部打包", "加双筷子", "不用餐具", "有儿童用餐"]),
        "category_order": biz.get("category_order", []),
        "entry_coupon": entry_coupon,  # 进店券，None 表示未登录或不满足条件
        "new_customer_coupon_preview": new_customer_coupon_preview,  # 新客券预览，None 表示该店未开启
        "invite_reward_enabled": invite_reward_enabled,  # 邀请奖励是否开启，决定"邀请好友"入口显不显示
        "coupon_reminder_template_id": settings.WECHAT_COUPON_REMINDER_TEMPLATE_ID or "",  # 空字符串表示提醒功能还没配置模板，前端应隐藏"提醒我"按钮
        "queue_reminder_template_id": settings.WECHAT_QUEUE_REMINDER_TEMPLATE_ID or "",  # 空字符串表示排队订阅消息未配置
        "order_success_template_id": settings.WECHAT_ORDER_SUCCESS_TEMPLATE_ID or "",  # 点餐成功通知
        "pickup_reminder_template_id": settings.WECHAT_PICKUP_REMINDER_TEMPLATE_ID or "",  # 取餐提醒
        "pickup_no_enabled": bool(biz.get("pickup_no_enabled", False)),
        "pickup_no_count": int(biz.get("pickup_no_count") or 30),
    })


@router.get("/menu/items")
async def list_menu_items(
    request: Request,
    shop: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    token_type = getattr(request.state, "token_type", None)
    is_merchant = token_type == "merchant"

    if is_merchant:
        # 商户端：用 token 里的 tenant_id，返回全部菜品（含下架）
        tenant_id = getattr(request.state, "tenant_id", None)
        if not tenant_id:
            return error_response(code=401, msg="请先登录")
        query = select(MenuItem).where(MenuItem.tenant_id == tenant_id)
    else:
        # 顾客端：必须传 shop 参数，只返回上架菜品；商户被平台停用后菜单也不再对外展示
        if not shop:
            return error_response(code=400, msg="缺少shop参数")
        tenant_id = shop
        tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == shop))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant or not tenant.status:
            return success_response(data=[])
        query = select(MenuItem).where(MenuItem.tenant_id == shop, MenuItem.available == True)

    TenantContext.set_tenant_id(tenant_id)
    result = await db.execute(query.order_by(MenuItem.sort_order, MenuItem.id))
    items = result.scalars().all()
    specs_map = await load_menu_specs(db, tenant_id)
    # version 给客户端做"先用本地缓存秒出首屏、再拿这个字段跟缓存比对要不要换"用的——
    # 不是单独一次查询算出来的，就是这批已经查出来的菜品自己的 updated_at 取最大值，
    # 零额外开销。菜单没变过就是空列表，用 "0" 占位，不影响比对逻辑（缓存的 version
    # 只要不是 "0" 且跟这次不一样就会被换掉；本来就没缓存过也无所谓）。
    version = max((i.updated_at for i in items), default=None)
    return success_response(data={
        "items": [serialize_item(i, specs_map) for i in items],
        "version": version.isoformat() if version else "0",
    })


@router.post("/menu/items")
async def create_menu_item(
    body: MenuItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    TenantContext.set_tenant_id(tenant_id)
    item = MenuItem(
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        price=body.price,
        category=body.category or "默认",
        emoji=body.emoji or "🍽️",
        available=body.available if body.available is not None else True,
        sort_order=body.sort_order or 0,
        stock=body.stock,
        image=body.image,
        sales_count=body.sales_count,
        tags=body.tags,
        original_price=body.original_price,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    if body.spec_groups:
        await save_menu_specs(db, tenant_id, item.id, body.spec_groups)
        await db.commit()
    specs_map = await load_menu_specs(db, tenant_id)
    return success_response(data=serialize_item(item, specs_map), msg="建成功")


@router.put("/menu/items/{item_id}")
async def update_menu_item(
    item_id: int,
    body: MenuItemUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    TenantContext.set_tenant_id(tenant_id)
    result = await db.execute(
        select(MenuItem).where(MenuItem.id == item_id, MenuItem.tenant_id == tenant_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return error_response(code=404, msg="菜品不存在")
    body_data = body.dict(exclude_unset=True)
    fields_set = getattr(body, "model_fields_set", getattr(body, "__fields_set__", set()))
    spec_groups = body_data.pop("spec_groups", None)
    for field, value in body_data.items():
        setattr(item, field, value)
    if "spec_groups" in fields_set:
        await save_menu_specs(db, tenant_id, item.id, spec_groups)
    await db.commit()
    await db.refresh(item)
    specs_map = await load_menu_specs(db, tenant_id)
    return success_response(data=serialize_item(item, specs_map), msg="更新成功")


class StockUpdateBody(PydanticBase):
    stock: Optional[int] = None  # None=不限, 0=售罄, >0=补货数量


@router.patch("/menu/items/{item_id}/stock")
async def update_stock(
    item_id: int,
    body: StockUpdateBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    TenantContext.set_tenant_id(tenant_id)
    result = await db.execute(
        select(MenuItem).where(MenuItem.id == item_id, MenuItem.tenant_id == tenant_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return error_response(code=404, msg="菜品不存在")
    item.stock = body.stock
    await db.commit()
    await db.refresh(item)
    return success_response(data=serialize_item(item), msg="库存已更新")


def _sniff_image_content_type(content: bytes) -> str | None:
    """兼容旧测试导入路径；实现已迁到 app.core.cos.sniff_image_content_type。"""
    from app.core.cos import sniff_image_content_type
    return sniff_image_content_type(content)


@router.post("/menu/upload-image")
async def upload_menu_image(
    request: Request,
    file: UploadFile = File(...),
):
    """上传菜品图片到 COS，返回公开访问 URL"""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        return error_response(code=400, msg="仅支持 jpg/png/webp/gif")
    content = await file.read()
    if len(content) > 3 * 1024 * 1024:
        return error_response(code=400, msg="图片不能超过 3MB")
    from starlette.concurrency import run_in_threadpool
    from app.core.cos import process_image, sniff_image_content_type, upload_image
    if not sniff_image_content_type(content):
        return error_response(code=400, msg="文件内容不是有效图片")
    try:
        processed = await run_in_threadpool(process_image, content)
    except ValueError:
        return error_response(code=400, msg="图片内容无效或已损坏")
    except RuntimeError as e:
        return error_response(code=500, msg=str(e))
    try:
        url = upload_image(processed, "dish.webp", "image/webp", folder="dish_images")
        return success_response(data={"url": url}, msg="上传成功")
    except Exception as e:
        return error_response(code=500, msg=f"上传失败：{str(e)}")


class DishDescRequest(PydanticBase):
    name: str
    price: float = 0
    category: str = "热销推荐"


@router.post("/menu/generate-desc")
async def generate_dish_desc(body: DishDescRequest, request: Request):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    if not body.name.strip():
        return error_response(code=400, msg="请填写菜品名称")
    try:
        from app.services.ai_menu_service import generate_dish_description
        desc = await generate_dish_description(body.name.strip(), body.price, body.category)
        return success_response(data={"description": desc})
    except ValueError as e:
        return error_response(code=400, msg=str(e))
    except Exception as e:
        logger.error(f"菜品描述生成失败: {e}")
        return error_response(code=500, msg="AI生成失败，请稍后重试")


class MenuTextParseRequest(PydanticBase):
    text: str


@router.post("/menu/parse-text")
async def parse_menu_from_text(
    body: MenuTextParseRequest,
    request: Request,
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    if not body.text or not body.text.strip():
        return error_response(code=400, msg="请输入菜单文字")
    if len(body.text) > 5000:
        return error_response(code=400, msg="文字太长，请分批输入")
    try:
        from app.services.ai_menu_service import parse_menu_text
        items = await parse_menu_text(body.text)
        if not items:
            return error_response(code=400, msg="未识别到菜品，请检查输入格式")
        return success_response(data=items, msg=f"识别到 {len(items)} 个菜品，确认后点击导入")
    except ValueError as e:
        return error_response(code=400, msg=str(e))
    except Exception as e:
        logger.error(f"AI菜单解析失败: {e}")
        return error_response(code=500, msg="AI识别失败，请稍后重试")


@router.post("/menu/import-batch")
async def import_menu_batch(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    body = await request.json()
    items_data = body.get("items", [])
    if not items_data:
        return error_response(code=400, msg="没有要导入的菜品")
    TenantContext.set_tenant_id(tenant_id)
    created = []
    for d in items_data:
        name = str(d.get("name") or "").strip()
        if not name:
            continue
        item = MenuItem(
            tenant_id=tenant_id,
            name=name,
            description=d.get("description") or None,
            price=float(d.get("price") or 0),
            category=str(d.get("category") or "热销推荐").strip(),
            emoji="🍽️",
            available=True,
            sort_order=0,
        )
        db.add(item)
        created.append(name)
    await db.commit()
    return success_response(data={"count": len(created), "names": created}, msg=f"已导入 {len(created)} 个菜品")


class DishLibraryContributeRequest(PydanticBase):
    name: str
    category: Optional[str] = None
    cuisine_type: str  # sichuan | bbq | universal
    kind: Optional[str] = "dish"  # dish=现做菜品 | standard=标准品(瓶装/包装，图片完全通用)
    image: str
    reference_price: Optional[float] = None


class DishLibraryImportItem(PydanticBase):
    id: str
    price: Optional[float] = None
    category: Optional[str] = None


class DishLibraryImportBatchRequest(PydanticBase):
    items: list[DishLibraryImportItem]


def serialize_library_item(item: DishLibraryItem):
    return {
        "id": str(item.id),
        "name": item.name,
        "category": item.category,
        "cuisine_type": item.cuisine_type,
        "kind": item.kind,
        "image": item.image,
        "reference_price": float(item.reference_price) if item.reference_price is not None else None,
        "use_count": item.use_count or 0,
    }


@router.get("/dish-library")
async def list_dish_library(
    request: Request,
    cuisine_type: Optional[str] = None,
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """浏览/搜索菜品库。universal（标准品）不分菜系，任何 cuisine_type 筛选下都会带出来。"""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    query = select(DishLibraryItem)
    if cuisine_type:
        query = query.where(or_(DishLibraryItem.cuisine_type == cuisine_type, DishLibraryItem.cuisine_type == "universal"))
    if keyword and keyword.strip():
        query = query.where(DishLibraryItem.name.ilike(f"%{keyword.strip()}%"))
    query = query.order_by(DishLibraryItem.use_count.desc(), DishLibraryItem.id.desc()).limit(200)
    result = await db.execute(query)
    items = result.scalars().all()
    return success_response(data=[serialize_library_item(i) for i in items])


@router.post("/dish-library/contribute")
async def contribute_dish_library(
    body: DishLibraryContributeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """商户主动把自己拍的菜品图分享进库。同名同菜系已存在时不重复建条目，
    避免同一道菜被反复贡献出一堆近似重复的库存条目。"""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    name = body.name.strip()
    if not name:
        return error_response(code=400, msg="菜品名称不能为空")
    if not body.image:
        return error_response(code=400, msg="请先上传图片再分享")
    if body.cuisine_type not in ("sichuan", "bbq", "universal"):
        return error_response(code=400, msg="菜系参数不合法")
    result = await db.execute(
        select(DishLibraryItem).where(
            DishLibraryItem.name == name,
            DishLibraryItem.cuisine_type == body.cuisine_type,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if not existing.image:
            existing.image = body.image
            await db.commit()
        return success_response(msg="该菜品已在菜品库中")
    item = DishLibraryItem(
        name=name,
        category=body.category,
        cuisine_type=body.cuisine_type,
        kind=body.kind or "dish",
        image=body.image,
        reference_price=body.reference_price,
        source_tenant_id=tenant_id,
    )
    db.add(item)
    await db.commit()
    return success_response(msg="已分享到菜品库")


@router.post("/dish-library/import-batch")
async def import_dish_library_batch(
    body: DishLibraryImportBatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    if not body.items:
        return error_response(code=400, msg="没有要导入的菜品")
    ids = [int(i.id) for i in body.items]
    result = await db.execute(select(DishLibraryItem).where(DishLibraryItem.id.in_(ids)))
    lib_map = {str(i.id): i for i in result.scalars().all()}
    TenantContext.set_tenant_id(tenant_id)
    created = []
    for req_item in body.items:
        lib_item = lib_map.get(req_item.id)
        if not lib_item:
            continue
        price = req_item.price if req_item.price is not None else float(lib_item.reference_price or 0)
        menu_item = MenuItem(
            tenant_id=tenant_id,
            name=lib_item.name,
            price=price,
            category=req_item.category or lib_item.category or "默认",
            emoji="🍽️",
            available=True,
            sort_order=0,
            image=lib_item.image,
        )
        db.add(menu_item)
        lib_item.use_count = (lib_item.use_count or 0) + 1
        created.append(lib_item.name)
    await db.commit()
    return success_response(data={"count": len(created), "names": created}, msg=f"已导入 {len(created)} 个菜品")


@router.delete("/menu/items/{item_id}")
async def delete_menu_item(
    item_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    TenantContext.set_tenant_id(tenant_id)
    result = await db.execute(
        select(MenuItem).where(MenuItem.id == item_id, MenuItem.tenant_id == tenant_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return error_response(code=404, msg="菜品不存在")
    await save_menu_specs(db, tenant_id, item.id, [])
    await db.delete(item)
    await db.commit()
    return success_response(msg="删除成功")
