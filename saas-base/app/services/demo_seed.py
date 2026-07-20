"""
演示账号种子数据。
调用 seed_demo_tenant(db) 可一次性建/重置演示数据。
"""
import random
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.utils.id_generator import generate_snowflake_id

DEMO_TENANT_ = "demo"
DEMO_PASSWORD = "demo123456"
DEMO_NAME = "味来餐厅（演示）"

# ── 菜品 ──────────────────────────────────────────────
MENU_ITEMS = [
    # 招牌热菜
    {"name": "招牌红烧肉", "price": 38, "category": "招牌热菜", "description": "入口即化，肥而不腻，每日限量", "emoji": "🥩", "tags": "招牌,热销", "sort_order": 1},
    {"name": "麻婆豆腐", "price": 22, "category": "招牌热菜", "description": "嫩滑鲜辣，下饭首选", "emoji": "🌶️", "tags": "辣,下饭", "sort_order": 2},
    {"name": "鱼香肉丝", "price": 26, "category": "招牌热菜", "description": "酸甜微辣，经典川味", "emoji": "🍖", "tags": "川味", "sort_order": 3},
    {"name": "宫保鸡丁", "price": 28, "category": "招牌热菜", "description": "香脆花生配嫩鸡，微辣鲜香", "emoji": "🐔", "tags": "辣,招牌", "sort_order": 4},
    # 汤类
    {"name": "番茄蛋花汤", "price": 12, "category": "例汤", "description": "新鲜番茄现熬，酸甜开胃", "emoji": "🍅", "tags": "暖胃", "sort_order": 10},
    {"name": "酸辣汤", "price": 14, "category": "例汤", "description": "酸辣爽口，开胃暖身", "emoji": "🍲", "tags": "辣,暖胃", "sort_order": 11},
    # 主食
    {"name": "白米饭", "price": 2, "category": "主食", "description": "", "emoji": "🍚", "tags": "", "sort_order": 20},
    {"name": "炒面", "price": 16, "category": "主食", "description": "手工拉面大火爆炒，根根劲道", "emoji": "🍜", "tags": "饱腹", "sort_order": 21},
    {"name": "蛋炒饭", "price": 14, "category": "主食", "description": "粒粒分明，蛋香浓郁", "emoji": "🍳", "tags": "热销", "sort_order": 22},
    # 饮品
    {"name": "冰镇可乐", "price": 6, "category": "饮品", "description": "", "emoji": "🥤", "tags": "", "sort_order": 30},
    {"name": "鲜榨橙汁", "price": 12, "category": "饮品", "description": "当季鲜橙现榨，不加糖不加水", "emoji": "🍊", "tags": "鲜榨,健康", "sort_order": 31},
    {"name": "老酸奶", "price": 8, "category": "饮品", "description": "凝固型老酸奶，浓稠绵密", "emoji": "🥛", "tags": "", "sort_order": 32, "stock": 0},  # 售罄演示
]

# ── 顾客姓名库 ─────────────────────────────────────────
_NAMES = [
    "张伟", "李娜", "王芳", "刘洋", "陈静", "杨帆", "赵雷", "周婷",
    "吴强", "孙丽", "徐明", "朱晓", "胡燕", "高峰", "林海", "何敏",
    "郭磊", "马丽", "曹阳", "谢红",
]

# ── 桌台 ──────────────────────────────────────────────
TABLES = [
    {"name": "01号桌", "table_no": "01", "scene": "table_01"},
    {"name": "02号桌", "table_no": "02", "scene": "table_02"},
    {"name": "03号桌", "table_no": "03", "scene": "table_03"},
    {"name": "04号桌", "table_no": "04", "scene": "table_04"},
    {"name": "外带取餐", "table_no": "", "scene": "takeaway", "channel": "TAKEAWAY"},
]

# ── 优惠券模 ──────────────────────────────────────────
_now = datetime.utcnow()
COUPON_TEMPLATES = [
    {
        "name": "新客立减5元",
        "type": "discount_amount",
        "value": 5,
        "min_amount": 30,
        "total_stock": 200,
        "used_stock": 47,
        "description": "新会员专属，消费满30元减5元",
        "start_time": _now - timedelta(days=30),
        "end_time": _now + timedelta(days=90),
    },
    {
        "name": "会员8.8折券",
        "type": "discount_rate",
        "value": 0.88,
        "min_amount": 50,
        "total_stock": 100,
        "used_stock": 12,
        "description": "会员专属折扣，满50元享8.8折",
        "start_time": _now - timedelta(days=15),
        "end_time": _now + timedelta(days=60),
    },
]


async def _clear_demo_data(db: AsyncSession):
    """清除演示租户的所有业务数据（保留租户账号本身）。"""
    # 先删 order_items（无 tenant_id，需要通过 order_id join）
    order_ids_result = await db.execute(
        select(Order.id).where(Order.tenant_id == DEMO_TENANT_)
    )
    order_ids = [r for r, in order_ids_result]
    if order_ids:
        await db.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))

    for model in (Order, MenuItem, Customer, EntranceCode, CouponTemplate):
        await db.execute(delete(model).where(model.tenant_id == DEMO_TENANT_))

    await db.commit()


async def _ensure_tenant(db: AsyncSession) -> None:
    """确保演示租户存在，不存在则建。"""
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == DEMO_TENANT_))
    tenant = result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(
            id=generate_snowflake_id(),
            tenant_id=DEMO_TENANT_,
            name=DEMO_NAME,
            password_hash=get_password_hash(DEMO_PASSWORD),
            phone="13800000000",
            address="示例街道88号",
            is_open=True,
            status=True,
        )
        db.add(tenant)
    else:
        tenant.name = DEMO_NAME
        tenant.password_hash = get_password_hash(DEMO_PASSWORD)
        tenant.is_open = True
    await db.commit()


def _days_ago(n: int, hour: int = 12, minute: int = 0) -> datetime:
    base = datetime.utcnow().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base - timedelta(days=n)


async def seed_demo_tenant(db: AsyncSession) -> dict:
    """建/重置演示账号数据，返回摘要信息。"""
    await _clear_demo_data(db)
    await _ensure_tenant(db)

    # ── 菜品 ──
    dish_map: dict[str, MenuItem] = {}
    for d in MENU_ITEMS:
        item = MenuItem(
            tenant_id=DEMO_TENANT_,
            name=d["name"],
            description=d.get("description") or None,
            price=d["price"],
            category=d["category"],
            emoji=d.get("emoji", "🍽️"),
            available=True,
            sort_order=d.get("sort_order", 0),
            tags=d.get("tags") or None,
            stock=d.get("stock", None),
            sales_count=random.randint(20, 200),
        )
        db.add(item)
        dish_map[d["name"]] = item
    await db.flush()  # 获取 id

    # ── 顾客 ──
    customers = []
    for i, name in enumerate(_NAMES):
        c = Customer(
            tenant_id=DEMO_TENANT_,
            openid=f"demo_openid_{i:03d}",
            name=name,
            phone=f"138{88880000 + i}",
            status=1,
            created_at=_days_ago(random.randint(0, 29), random.randint(9, 20)),
            updated_at=datetime.utcnow(),
        )
        db.add(c)
        customers.append(c)
    await db.flush()

    # ── 优惠券模 ──
    for ct in COUPON_TEMPLATES:
        db.add(CouponTemplate(
            tenant_id=DEMO_TENANT_,
            **ct,
        ))

    # ── 桌台二维码 ──
    for t in TABLES:
        db.add(EntranceCode(
            tenant_id=DEMO_TENANT_,
            name=t["name"],
            channel=t.get("channel", "TABLE"),
            scene=t["scene"],
            page="pages/entry/index",
            code_type="TEST",
            generation_status="SUCCESS",
            status=1,
            scan_count=random.randint(5, 80),
            member_count=random.randint(2, 30),
            table_no=t.get("table_no", ""),
        ))

    await db.commit()

    # ── 历史订单（近30天，约80笔）──
    dish_list = list(dish_map.values())
    available_dishes = [d for d in dish_list if d.stock != 0]

    order_count = 0
    for day in range(30, 0, -1):
        # 每天随机 1-5 笔
        day_orders = random.randint(1, 5)
        for _ in range(day_orders):
            hour = random.randint(10, 20)
            created = _days_ago(day, hour, random.randint(0, 59))
            items_sample = random.sample(available_dishes, k=random.randint(2, 4))
            total = sum(float(d.price) * random.randint(1, 2) for d in items_sample)
            customer = random.choice(customers) if random.random() > 0.3 else None

            order = Order(
                tenant_id=DEMO_TENANT_,
                customer_id=customer.id if customer else None,
                table_no=f"0{random.randint(1,4)}",
                total=round(total, 2),
                status="done",
                payment_status="paid",
                payment_method="mock",
                payment_time=created.isoformat(),
                source="h5",
                created_at=created,
                updated_at=created,
            )
            db.add(order)
            await db.flush()

            for dish in items_sample:
                qty = random.randint(1, 2)
                db.add(OrderItem(
                    order_id=order.id,
                    dish_id=dish.id,
                    name=dish.name,
                    price=dish.price,
                    qty=qty,
                ))
            order_count += 1

    # ── 今日订单（5笔，模拟当天有营业数据）──
    today_dishes_pool = random.sample(available_dishes, k=min(6, len(available_dishes)))
    today_order_count = 0
    for i in range(5):
        hour = 10 + i * 2
        created = datetime.utcnow().replace(hour=hour, minute=random.randint(0, 59), second=0, microsecond=0)
        if created > datetime.utcnow():
            created = datetime.utcnow() - timedelta(minutes=10)
        items_sample = random.sample(today_dishes_pool, k=random.randint(2, 3))
        total = sum(float(d.price) * random.randint(1, 2) for d in items_sample)
        customer = random.choice(customers)

        order = Order(
            tenant_id=DEMO_TENANT_,
            customer_id=customer.id,
            table_no=f"0{(i % 4) + 1}",
            total=round(total, 2),
            status="done",
            payment_status="paid",
            payment_method="mock",
            payment_time=created.isoformat(),
            source="h5",
            created_at=created,
            updated_at=created,
        )
        db.add(order)
        await db.flush()

        for dish in items_sample:
            qty = random.randint(1, 2)
            db.add(OrderItem(
                order_id=order.id,
                dish_id=dish.id,
                name=dish.name,
                price=dish.price,
                qty=qty,
            ))
        today_order_count += 1

    await db.commit()

    return {
        "tenant_id": DEMO_TENANT_,
        "login": DEMO_TENANT_,
        "password": DEMO_PASSWORD,
        "menu_items": len(MENU_ITEMS),
        "customers": len(customers),
        "history_orders": order_count,
        "today_orders": today_order_count,
        "tables": len(TABLES),
    }
