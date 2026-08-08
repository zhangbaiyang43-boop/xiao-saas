import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.consumptions import router as consumption_router
from app.api.v1.customers import router as customer_router
from app.api.v1.distribution import router as distribution_router
from app.api.v1.dining_sessions import router as dining_session_router
from app.api.v1.entrance_codes import router as entrance_code_router
from app.api.v1.login import router as login_router
from app.api.v1.merchant_accounts import router as merchant_accounts_router
from app.api.v1.staff_auth import router as staff_auth_router
from app.api.v1.member import router as member_router
from app.api.v1.merchant_system import router as merchant_system_router
from app.api.v1.membership import router as membership_router
from app.api.v1.miniapp import router as miniapp_router
from app.api.v1.plugins import router as plugin_router
from app.api.v1.pos import router as pos_router
from app.api.v1.staff_referral import router as staff_referral_router
from app.api.v1.queue import router as queue_router
from app.api.v1.stats import router as stats_router
from app.api.v1.tenant import router as tenant_router
from app.api.v1.wework import router as wework_router
from app.api.v1.channel_entries import router as channel_entries_router
from app.api.v1.public_channel import router as public_channel_router
from app.api.v1.h5_landing import router as h5_landing_router
from app.api.v1.menu import router as menu_router
from app.api.v1.orders import router as order_router
from app.api.v1.perf import router as perf_router
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
app.include_router(merchant_accounts_router)
app.include_router(staff_auth_router)
app.include_router(member_router)
app.include_router(miniapp_router)
app.include_router(membership_router)
app.include_router(tenant_router)
app.include_router(merchant_system_router)
app.include_router(customer_router)
app.include_router(distribution_router)
app.include_router(staff_referral_router)
app.include_router(dining_session_router)
app.include_router(consumption_router)
# coupon_template_router / coupon_router / verify_router 不在这里重复注册——
# CouponPlugin.get_routers()（下面 plugin_manager.load_plugins() 里）已经注册
# 了这三个路由，这里再注册一次纯属历史遗留的重复挂载，只保留一处注册。
app.include_router(entrance_code_router)
app.include_router(wework_router)
app.include_router(plugin_router)
app.include_router(pos_router)
app.include_router(stats_router)
app.include_router(channel_entries_router)
app.include_router(public_channel_router)
app.include_router(h5_landing_router)
app.include_router(menu_router)
app.include_router(order_router)
app.include_router(perf_router)
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


STALE_ORDER_CLEANUP_TIMEOUT_MINUTES = 15


async def _stale_order_cleanup_once():
    """Run one pass of the stale-order cleanup. Split out from the loop below so it's
    directly callable from tests instead of having to drive the infinite loop's sleeps."""
    from datetime import datetime as _dt, timedelta
    from app.core.database import AsyncSessionLocal
    from app.models.order import Order
    from app.models.coupon import Coupon as _Coupon
    from sqlalchemy.future import select as _select

    threshold = _dt.utcnow() - timedelta(minutes=STALE_ORDER_CLEANUP_TIMEOUT_MINUTES)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            _select(Order).where(
                Order.status == "pending_payment",
                Order.created_at < threshold,
            )
        )
        stale = result.scalars().all()
        if stale:
            from app.api.v1.orders import _restore_order_stock
            from app.services.order_payment_service import OrderPaymentService

            payment_svc = OrderPaymentService(db)
        for o in stale:
            recovered = await payment_svc._recover_wxpay_order_if_paid(o)
            if recovered:
                continue
            await _restore_order_stock(o, db)
            o.status = "cancelled"
            if o.coupon_id:
                coupon = await db.get(_Coupon, o.coupon_id)
                if coupon and coupon.status == "LOCKED":
                    coupon.status = "UNUSED"
        if stale:
            await db.commit()


PENDING_PAYMENT_RECONCILE_AFTER_SECONDS = 90
PENDING_PAYMENT_RECONCILE_INTERVAL_SECONDS = 60


async def _pending_payment_reconcile_once():
    """只负责把"实际已经支付成功、但微信 webhook 还没落地"的订单尽快捞出来补票（触发
    _on_payment_success，含厨房出票），不做任何取消/退库存动作——刻意跟
    _stale_order_cleanup_once 分开，是因为"确认一笔钱是不是真的到账了"和"确定顾客真的
    没付款、可以取消退库存"这两件事该有的响应速度天差地别：前者应该几十秒就查一次，
    后者必须留足够长的等待窗口（15分钟）避免误伤正在正常支付中的顾客。这两件事之前共用
    同一个 15 分钟阈值，意味着顾客付款成功但 webhook 丢失时，厨房最坏要等 15 分钟才会
    补上这张票——直接命中"不能漏单"这条要求。一个门店在任意时刻处于 pending_payment
    的订单数量通常是个位数，_recover_wxpay_order_if_paid 内部只有查到真的支付成功才会
    有副作用，所以更高频地跑这个检查成本可以忽略。"""
    from datetime import datetime as _dt, timedelta
    from app.core.database import AsyncSessionLocal
    from app.models.order import Order
    from sqlalchemy.future import select as _select

    threshold = _dt.utcnow() - timedelta(seconds=PENDING_PAYMENT_RECONCILE_AFTER_SECONDS)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            _select(Order).where(
                Order.status == "pending_payment",
                Order.created_at < threshold,
            )
        )
        pending = result.scalars().all()
        if not pending:
            return
        from app.services.order_payment_service import OrderPaymentService

        payment_svc = OrderPaymentService(db)
        recovered_any = False
        for o in pending:
            if await payment_svc._recover_wxpay_order_if_paid(o):
                recovered_any = True
        if recovered_any:
            await db.commit()


async def _pending_payment_reconcile_loop():
    import asyncio

    await asyncio.sleep(10)  # 等待应用完全启动
    while True:
        try:
            await _pending_payment_reconcile_once()
        except Exception:
            pass
        await asyncio.sleep(PENDING_PAYMENT_RECONCILE_INTERVAL_SECONDS)


async def _stale_order_cleanup_loop():
    """Clean stale unpaid orders and restore locked coupons."""
    import asyncio

    INTERVAL = 300  # 5分钟
    await asyncio.sleep(10)  # 等待应用完全启动
    while True:
        try:
            await _stale_order_cleanup_once()
        except Exception:
            pass
        await asyncio.sleep(INTERVAL)


async def _marketing_recall_loop():
    """每天自动扫描各商户的沉睡客户并发放召回券。

    这是 admin-h5"老客召回券"开关文案("系统自动发券提醒")对应的真实执行体——
    此前该开关只更新 coupon_rules.enabled，从未有任何定时任务真正扫描客户，
    商家开了等于没开。CouponService.batch_issue_recall_coupon 内部已经会在
    未开启时直接跳过（reason: 老客召回券未开启），所以这里对全部商户无差别调用即可。
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.core.logger import logger
    from app.models.tenant import Tenant
    from app.services.coupon_service import CouponService
    from sqlalchemy.future import select as _select

    INTERVAL = 24 * 3600  # 每天一次
    await asyncio.sleep(60)  # 等待应用完全启动
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(_select(Tenant.tenant_id).where(Tenant.status == True))  # noqa: E712
                tenant_ids = [row[0] for row in result.all()]

            for tid in tenant_ids:
                try:
                    async with AsyncSessionLocal() as db:
                        service = CouponService(db)
                        service.set_tenant_id(tid)
                        outcome = await service.batch_issue_recall_coupon()
                        if outcome.get("success_count"):
                            logger.info(f"[marketing_recall] tenant={tid} issued={outcome['success_count']}")
                except Exception:
                    logger.exception(f"[marketing_recall] tenant={tid} failed")
        except Exception:
            logger.exception("[marketing_recall] loop failed")
        await asyncio.sleep(INTERVAL)


async def _coupon_expiry_reminder_loop():
    """扫描顾客主动申请过提醒（remind_requested）、还没发过（remind_sent_at 为空）、
    还没用掉、且快要过期的券，推一条微信订阅消息催回来用。

    只在配置了 WECHAT_COUPON_REMINDER_TEMPLATE_ID 时才跑，没配置直接跳过——这是
    需要商户/平台在微信公众平台"订阅消息"里申请模板之后手动填的，不是代码能替你做的。

    data 里的字段名（thing1/amount2/time3...）必须跟实际选用的订阅消息模板配置的
    字段名完全一致，这里给的是这类"到期提醒"模板最常见的字段命名，接入真实模板后
    需要对照微信公众平台的模板详情核对、按需调整。
    """
    import asyncio
    from datetime import datetime as _dt, timedelta
    from app.core.database import AsyncSessionLocal
    from app.core.logger import logger
    from app.models.coupon import Coupon
    from app.models.coupon_template import CouponTemplate
    from app.models.customer import Customer
    from app.services.wechat_service import WechatService
    from sqlalchemy.future import select as _select

    INTERVAL = 6 * 3600  # 每6小时扫一次，避免"提前一天提醒"因为一天只跑一次而被错过
    REMIND_WINDOW_HOURS = 30  # 快过期的定义：还剩不到30小时
    await asyncio.sleep(90)  # 等待应用完全启动

    while True:
        try:
            template_id = (settings.WECHAT_COUPON_REMINDER_TEMPLATE_ID or "").strip()
            if not template_id:
                await asyncio.sleep(INTERVAL)
                continue

            wechat = WechatService()
            now = _dt.utcnow()
            window_end = now + timedelta(hours=REMIND_WINDOW_HOURS)

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    _select(Coupon).where(
                        Coupon.remind_requested == True,  # noqa: E712
                        Coupon.remind_sent_at.is_(None),
                        Coupon.status == "UNUSED",
                        Coupon.expire_time > now,
                        Coupon.expire_time <= window_end,
                    ).limit(200)
                )
                due_coupons = result.scalars().all()

                for coupon in due_coupons:
                    try:
                        customer = await db.get(Customer, coupon.customer_id)
                        if not customer or not customer.openid:
                            coupon.remind_sent_at = now
                            continue
                        template = await db.get(CouponTemplate, coupon.template_id)

                        # 模板「优惠券到期提醒」关键词顺序：优惠券名称 → 有效期 → 备注
                        sent = await wechat.send_subscribe_message(
                            openid=customer.openid,
                            template_id=template_id,
                            data={
                                "thing1": {"value": ((template.name if template else "优惠券") or "优惠券")[:20]},
                                "time2": {"value": coupon.expire_time.strftime("%Y-%m-%d %H:%M")},
                                "thing3": {"value": "还没用完，记得回来点单哦"},
                            },
                        )
                        if sent:
                            coupon.remind_sent_at = now
                            logger.info(f"[coupon_reminder] sent coupon_id={coupon.id} customer_id={coupon.customer_id}")
                        else:
                            # 发送失败（比如授权额度已用完）也标记成已处理，不然会跟着这个
                            # 顾客的这张券每6小时重试一次，永远发不出去也永远占着扫描名额。
                            coupon.remind_sent_at = now
                    except Exception:
                        logger.exception(f"[coupon_reminder] coupon_id={coupon.id} failed")

                if due_coupons:
                    await db.commit()
        except Exception:
            logger.exception("[coupon_reminder] loop failed")
        await asyncio.sleep(INTERVAL)


@app.on_event("startup")
async def startup():
    import asyncio
    # 排队票 openid/customer_id 等补列：生产常关 AUTO_CREATE_TABLES，但仍需幂等补齐，
    # 否则顾客自助取号 INSERT 会因 Unknown column 连续失败。
    async with async_engine.begin() as conn:
        await ensure_queue_ticket_schema(conn)

    if settings.AUTO_CREATE_TABLES:
        async with async_engine.begin() as conn:
            await ensure_bigint_ids(conn)
            await ensure_coupon_template_description(conn)
            await ensure_distribution_schema(conn)
            await ensure_tenant_schema(conn)
            await conn.run_sync(Base.metadata.create_all)

    # 启动超时订单后台清理任务
    asyncio.create_task(_stale_order_cleanup_loop())

    # 更高频地确认"已支付但 webhook 未到"的订单，不等 15 分钟的取消阈值——见
    # _pending_payment_reconcile_once 上的注释
    asyncio.create_task(_pending_payment_reconcile_loop())

    # 启动老客召回自动发券任务
    asyncio.create_task(_marketing_recall_loop())

    # 启动优惠券到期提醒任务（订阅消息未配置模板 ID 时循环内部会直接跳过）
    asyncio.create_task(_coupon_expiry_reminder_loop())


@app.get("/")
def read_root():
    return success_response(data={"message": "Multi-tenant Member Management SaaS API"})


@app.get("/health")
def health_check():
    return success_response(data={"status": "healthy"})

