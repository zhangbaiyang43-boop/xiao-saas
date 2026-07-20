from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache_helper import cache_result
from app.core.database import get_db
from app.core.rate_limiter import tenant_limit
from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.order import Order, OrderItem
from app.models.menu_item import MenuItem
from app.services.statistics_service import StatisticsService

router = APIRouter(prefix="/api/v1/stats", tags=["统计"])


@router.get("/dashboard", response_model=RespVo)
@tenant_limit()
@cache_result("stats:dashboard", ttl=60)
async def dashboard_stats(request: Request, db: AsyncSession = Depends(get_db)):
    data = await StatisticsService(db).dashboard()
    return success_response(data=data, msg="ok")


@router.post("/ai-analysis")
async def ai_daily_analysis(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    TenantContext.set_tenant_id(tenant_id)

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    # 今日订单
    today_orders_result = await db.execute(
        select(Order).where(
            Order.tenant_id == tenant_id,
            Order.created_at >= today_start,
            Order.payment_status == "paid",
        )
    )
    today_orders = today_orders_result.scalars().all()

    today_revenue = sum(float(o.total or 0) for o in today_orders)
    order_count = len(today_orders)
    avg_order_value = today_revenue / order_count if order_count else 0

    # 昨日营收
    yesterday_result = await db.execute(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.tenant_id == tenant_id,
            Order.created_at >= yesterday_start,
            Order.created_at < today_start,
            Order.payment_status == "paid",
        )
    )
    yesterday_revenue = float(yesterday_result.scalar() or 0)

    # 今日热销菜品
    order_ids = [o.id for o in today_orders]
    top_dishes = []
    if order_ids:
        items_result = await db.execute(
            select(OrderItem.name, func.sum(OrderItem.qty).label("total_qty"))
            .where(OrderItem.order_id.in_(order_ids))
            .group_by(OrderItem.name)
            .order_by(func.sum(OrderItem.qty).desc())
            .limit(5)
        )
        top_dishes = [{"name": row.name, "qty": int(row.total_qty)} for row in items_result]

    # 售罄菜品数
    sold_out_result = await db.execute(
        select(func.count()).select_from(MenuItem).where(
            MenuItem.tenant_id == tenant_id,
            MenuItem.stock == 0,
        )
    )
    sold_out_count = int(sold_out_result.scalar() or 0)

    # 今日新会员
    from app.models.customer import Customer
    new_members = int(await db.scalar(
        select(func.count()).select_from(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.created_at >= today_start,
        )
    ) or 0)

    analysis_data = {
        "today_revenue": today_revenue,
        "yesterday_revenue": yesterday_revenue,
        "order_count": order_count,
        "avg_order_value": avg_order_value,
        "new_members": new_members,
        "top_dishes": top_dishes,
        "sold_out_count": sold_out_count,
    }

    try:
        from app.services.ai_menu_service import generate_daily_analysis
        text = await generate_daily_analysis(analysis_data)
        return success_response(data={"analysis": text, "stats": analysis_data})
    except ValueError as e:
        return error_response(code=400, msg=str(e))
    except Exception as e:
        return error_response(code=500, msg=f"AI分析失败：{str(e)}")
