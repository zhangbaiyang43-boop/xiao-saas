import logging
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)
from pydantic import BaseModel as PydanticBase
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified
from typing import Optional

from app.core.database import get_db
from app.core.response import error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.menu_item import MenuItem
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
    if not tenant:
        return error_response(code=404, msg="商家不存在")
    config = await svc.get_tenant_config(shop)
    biz = (config.business_info or {}) if config else {}

    # 静默发放进店券（Plan B）：登录用户进入菜单时自动领取
    entry_coupon = None
    customer_id = getattr(request.state, "customer_id", None)
    if customer_id:
        try:
            from app.services.coupon_service import CouponService
            cs = CouponService(db)
            entry_coupon = await cs.issue_entry_coupon(int(customer_id))
        except Exception:
            pass

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
        "remark_chips": biz.get("remark_chips", ["不要辣", "微辣", "不要香菜", "不要葱", "少盐", "打包"]),
        "category_order": biz.get("category_order", []),
        "entry_coupon": entry_coupon,  # 进店券，None 表示未登录或不满足条件
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
        # 顾客端：必须传 shop 参数，只返回上架菜品
        if not shop:
            return error_response(code=400, msg="缺少shop参数")
        tenant_id = shop
        query = select(MenuItem).where(MenuItem.tenant_id == shop, MenuItem.available == True)

    TenantContext.set_tenant_id(tenant_id)
    result = await db.execute(query.order_by(MenuItem.sort_order, MenuItem.id))
    items = result.scalars().all()
    specs_map = await load_menu_specs(db, tenant_id)
    return success_response(data=[serialize_item(i, specs_map) for i in items])


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
    try:
        from app.core.cos import upload_image
        content_type = file.content_type or f"image/{ext}"
        url = upload_image(content, file.filename or f"dish.{ext}", content_type)
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
