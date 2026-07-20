import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.consumptions import router as consumption_router
from app.api.v1.coupon_templates import router as coupon_template_router
from app.api.v1.coupons import router as coupon_router
from app.api.v1.customers import router as customer_router
from app.api.v1.distribution import router as distribution_router
from app.api.v1.dining_sessions import router as dining_session_router
from app.api.v1.entrance_codes import router as entrance_code_router
from app.api.v1.login import router as login_router
from app.api.v1.member import router as member_router
from app.api.v1.merchant_system import router as merchant_system_router
from app.api.v1.membership import router as membership_router
from app.api.v1.miniapp import router as miniapp_router
from app.api.v1.plugins import router as plugin_router
from app.api.v1.pos import router as pos_router
from app.api.v1.queue import router as queue_router
from app.api.v1.stats import router as stats_router
from app.api.v1.tenant import router as tenant_router
from app.api.v1.verify import router as verify_router
from app.api.v1.wework import router as wework_router
from app.api.v1.channel_entries import router as channel_entries_router
from app.api.v1.public_channel import router as public_channel_router
from app.api.v1.h5_landing import router as h5_landing_router
from app.api.v1.marketing_templates import router as marketing_template_router
from app.api.v1.menu import router as menu_router
from app.api.v1.orders import router as order_router
from app.api.v1.super_admin import router as super_admin_router
from app.config import settings
from app.core.database import async_engine
from app.core.events import CONSUMPTION_CREATED, event_bus
from app.core.exceptions import (
    BusinessException,
    business_exception_handler,
    general_exception_handler,
    validation_exception_handler,
)
from app.core.rate_limiter import RateLimitExceeded, limiter, tenant_limiter
from app.core.response import RespVo, success_response
from app.core.schema_compat import ensure_bigint_ids, ensure_coupon_template_description, ensure_distribution_schema, ensure_queue_ticket_schema, ensure_tenant_schema
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.tenant_middleware import TenantMiddleware
from app.models import Base
from app.plugins.plugin_manager import plugin_manager
from app.services.consumption_event_handlers import handle_consumption_membership

os.makedirs("logs", exist_ok=True)
os.makedirs("static", exist_ok=True)

app = FastAPI(title="Multi-tenant Member Management SaaS", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.state.limiter = limiter
app.state.tenant_limiter = tenant_limiter

app.add_middleware(AuthMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["X-Process-Time-Ms"],
)

app.include_router(login_router)
app.include_router(member_router)
app.include_router(miniapp_router)
app.include_router(membership_router)
app.include_router(tenant_router)
app.include_router(merchant_system_router)
app.include_router(customer_router)
app.include_router(distribution_router)
app.include_router(dining_session_router)
app.include_router(consumption_router)
app.include_router(coupon_template_router)
app.include_router(coupon_router)
app.include_router(entrance_code_router)
app.include_router(verify_router)
app.include_router(wework_router)
app.include_router(plugin_router)
app.include_router(pos_router)
app.include_router(stats_router)
app.include_router(channel_entries_router)
app.include_router(public_channel_router)
app.include_router(h5_landing_router)
app.include_router(marketing_template_router, prefix="/api/admin")
app.include_router(menu_router)
app.include_router(order_router)
app.include_router(queue_router)
app.include_router(super_admin_router)

plugin_manager.register_app(app)
plugin_manager.load_plugins()
event_bus.register(CONSUMPTION_CREATED, handle_consumption_membership)
event_bus.register(CONSUMPTION_CREATED, plugin_manager.dispatch_event)

app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content=RespVo(code=429, msg="请求过于频繁，请稍后再试").to_response(),
    )


async def _stale_order_cleanup_loop():
    """Clean stale unpaid orders and restore locked coupons."""
    import asyncio
    from datetime import datetime as _dt, timedelta
    from app.core.database import AsyncSessionLocal
    from app.models.order import Order
    from app.models.coupon import Coupon as _Coupon
    from sqlalchemy.future import select as _select

    INTERVAL = 300  # 5分钟
    TIMEOUT_MINUTES = 15
    await asyncio.sleep(10)  # 等待应用完全启动
    while True:
        try:
            threshold = _dt.utcnow() - timedelta(minutes=TIMEOUT_MINUTES)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    _select(Order).where(
                        Order.status == "pending_payment",
                        Order.created_at < threshold,
                    )
                )
                stale = result.scalars().all()
                if stale:
                    from app.api.v1.orders import _recover_wxpay_order_if_paid
                for o in stale:
                    recovered = await _recover_wxpay_order_if_paid(o, db)
                    if recovered:
                        continue
                    o.status = "cancelled"
                    if o.coupon_id:
                        coupon = await db.get(_Coupon, o.coupon_id)
                        if coupon and coupon.status == "LOCKED":
                            coupon.status = "UNUSED"
                if stale:
                    await db.commit()
        except Exception:
            pass
        await asyncio.sleep(INTERVAL)


@app.on_event("startup")
async def startup():
    import asyncio
    if settings.AUTO_CREATE_TABLES:
        async with async_engine.begin() as conn:
            await ensure_bigint_ids(conn)
            await ensure_coupon_template_description(conn)
            await ensure_distribution_schema(conn)
            await ensure_tenant_schema(conn)
            await ensure_queue_ticket_schema(conn)
            await conn.run_sync(Base.metadata.create_all)

    # 初始化营销模
    from app.core.database import AsyncSessionLocal
    from app.services.marketing_template_init import MarketingTemplateInitService

    async with AsyncSessionLocal() as session:
        init_service = MarketingTemplateInitService(session)
        await init_service.init_default_templates()

    # 启动超时订单后台清理任务
    asyncio.create_task(_stale_order_cleanup_loop())


@app.get("/")
def read_root():
    return success_response(data={"message": "Multi-tenant Member Management SaaS API"})


@app.get("/health")
def health_check():
    return success_response(data={"status": "healthy"})

