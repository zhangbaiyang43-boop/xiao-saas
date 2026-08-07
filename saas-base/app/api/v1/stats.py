from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_helper import cache_result
from app.core.database import get_db
from app.core.rate_limiter import tenant_limit
from app.core.response import RespVo, error_response, success_response
from app.services.statistics_service import StatisticsService

router = APIRouter(prefix="/api/v1/stats", tags=["统计"])


@router.get("/dashboard", response_model=RespVo)
@tenant_limit()
@cache_result("stats:dashboard", ttl=60)
async def dashboard_stats(request: Request, db: AsyncSession = Depends(get_db)):
    service = StatisticsService(db)
    data = await service.dashboard()
    data.update(await service.order_overview())
    return success_response(data=data, msg="ok")


@router.get("/table-coupon-activity", response_model=RespVo)
@tenant_limit()
@cache_result("stats:table_coupon_activity", ttl=60)
async def table_coupon_activity(request: Request, date: str | None = None, db: AsyncSession = Depends(get_db)):
    """按桌统计当天有多少个"首单新客"扎堆同一桌——拆单套券这类问题选择用这个
    做人工核实的观测入口，不做自动拦截（见 statistics_service.table_coupon_activity 的说明）。"""
    day = None
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return error_response(code=400, msg="date 格式应为 YYYY-MM-DD")
    data = await StatisticsService(db).table_coupon_activity(day)
    return success_response(data=data, msg="ok")


@router.get("/marketing-effectiveness", response_model=RespVo)
@tenant_limit()
@cache_result("stats:marketing_effectiveness", ttl=60)
async def marketing_effectiveness(request: Request, days: int = 30, db: AsyncSession = Depends(get_db)):
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    data = await StatisticsService(db).marketing_effectiveness(start, end)
    return success_response(
        data={
            "rows": data,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": days,
        },
        msg="ok",
    )
