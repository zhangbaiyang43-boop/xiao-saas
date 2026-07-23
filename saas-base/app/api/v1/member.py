from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.v1.consumptions import serialize_consumption
from app.core.database import get_db
from app.core.logger import logger
from app.core.pagination import normalize_pagination
from app.core.response import RespVo, error_response, success_response
from app.core.security import create_customer_access_token
from app.core.tenant_context import TenantContext
from app.models.consumption import Consumption
from app.schemas.member import MemberLoginOrCreateRequest
from app.services.consumption_service import ConsumptionService
from app.services.coupon_service import CouponService
from app.services.customer_identity_service import CHANNEL_MINIAPP, CHANNEL_PHONE, CustomerIdentityService
from app.services.customer_service import CustomerService
from app.services.entrance_code_service import EntranceCodeService
from app.services.membership_service import MembershipService
from app.services.tenant_service import TenantService
from app.services.wechat_service import WechatService

router = APIRouter(prefix="/api/v1/member", tags=["顾客端"])


def current_customer(request: Request):
    customer_id = getattr(request.state, "customer_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or not customer_id:
        return None, None, error_response(code=401, msg="顾客未登录或登录已过期")
    return tenant_id, int(customer_id), None


def serialize_customer(customer, account=None):
    data = {
        "id": str(customer.id),
        "tenant_id": customer.tenant_id,
        "openid": customer.openid,
        "name": customer.name,
        "phone": customer.phone,
        "tags": customer.tags or [],
        "last_consume_time": customer.last_consume_time,
        "created_at": customer.created_at,
        "store_member_no": customer.store_member_no,
        "points": 0,
        "level": None,
    }
    if account:
        data["points"] = int(account.points_balance or 0)
        data["balance"] = float(account.balance or 0)
        data["level"] = account.level_name
        data["level_code"] = account.level_code
    return data


def serialize_entrance(entrance_code):
    if not entrance_code:
        return None
    return {
        "id": str(entrance_code.id),
        "tenant_id": entrance_code.tenant_id,
        "scene": entrance_code.scene,
        "channel": entrance_code.channel,
        "name": entrance_code.name,
    }


async def serialize_coupon(coupon, coupon_service: CouponService):
    template = await coupon_service.get_template(coupon.template_id)
    result = {
        "id": str(coupon.id),
        "template_id": str(coupon.template_id),
        "customer_id": str(coupon.customer_id),
        "code": coupon.code,
        "verify_code": coupon.verify_code,
        "status": coupon.status,
        "use_time": coupon.use_time,
        "expire_time": coupon.expire_time,
        "created_at": coupon.created_at,
        "name": template.name if template else "优惠券",
        "type": template.type if template else "FIXED",
        "value": float(template.value or 0) if template else 0,
        "min_amount": float(template.min_amount or 0) if template else 0,
        "description": template.description if template else None,
    }
    
    # 生成使用则说明
    rules = []
    if template:
        float_min_amount = float(template.min_amount or 0)
        float_value = float(template.value or 0)
        template_type = template.type
        template_desc = template.description
        
        # 基础则
        if template_type == "FIXED":
            if float_min_amount > 0:
                rules.append(f"满{float_min_amount}元可用，立减{float_value}元")
            else:
                rules.append(f"立减{float_value}元")
        elif template_type == "PERCENT":
            if float_min_amount > 0:
                rules.append(f"满{float_min_amount}元可用，{float_value}%折扣")
            else:
                rules.append(f"{float_value}%折扣")
        
        # 有效期则
        rules.append(f"有效期：{format_date(template.start_time)} 至 {format_date(template.end_time)}")
        
        if template_desc:
            rules.append(template_desc)
    
    result["rules"] = rules
    return result


def format_date(dt):
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d")


@router.post("/login-or-create", response_model=RespVo)
async def login_or_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # 直接读取原始请求体，避免 Pydantic 类型检查问题
    try:
        body = await request.body()
        import json
        raw_data = json.loads(body)
        tenant_id = str(raw_data.get('tenant_id', ''))
        phone = raw_data.get('phone')  # 仅作为新建客户的展示信息，不用于身份匹配
        name = raw_data.get('name')
        code = raw_data.get('code')  # 微信 wx.login() 返回的 code，用于换取经微信校验的 openid
        entrance_scene = raw_data.get('entrance_scene')
    except Exception as e:
        return error_response(code=400, msg="请求体解析失败")
    
    entrance_service = EntranceCodeService(db)
    entrance_code = None

    if entrance_scene:
        entrance_code = await entrance_service.get_by_scene(entrance_scene)
        if not entrance_code or entrance_code.status != 1:
            return error_response(code=404, msg="入口码不存在或已停用")
        if tenant_id != str(entrance_code.tenant_id):
            return error_response(code=400, msg="入口码与商家不匹配，请重新扫码")
        tenant_id = str(entrance_code.tenant_id)

    tenant_service = TenantService(db)
    tenant = None
    
    if tenant_id:
        tenant = await tenant_service.get_tenant(tenant_id)
    else:
        # 如果没有tenant_id，尝试获取第一个可用的商家作为默认商家
        tenants = await tenant_service.list_tenants(status=1)
        if tenants:
            tenant = tenants[0]
            tenant_id = str(tenant.id)
    
    if not tenant or not tenant.status:
        return error_response(code=404, msg="商家不存在或已停用")

    TenantContext.set_tenant_id(tenant_id)
    customer_service = CustomerService(db)
    identity_service = CustomerIdentityService(db)

    if not code:
        return error_response(code=400, msg="请提供微信登录 code")

    # P0 安全修复：openid 必须经微信 code2session 校验，不能直接信任客户端传入的
    # openid/手机号——否则任何人只要知道受害者手机号，或者随便编一个 openid，
    # 就能顶替/接管已有会员账户（余额、积分、优惠券、订单历史）。
    wechat_result = await WechatService().code2session(code)
    openid = wechat_result.get("openid")
    if not openid:
        return error_response(code=400, msg="微信登录校验失败，请重试")

    customer = None
    is_new_customer = False

    # 入会逻辑：身份完全由经微信校验的 openid 决定；手机号只作为新建客户时的
    # 展示信息保存，不再用于匹配/复用已有客户——避免仅凭手机号顶替他人账户。
    # 手机号如需真正校验绑定，走已有的 /send-verify-code + /bind-phone 流程。
    identity = await identity_service.get_by_identity(CHANNEL_MINIAPP, openid)
    if identity:
        customer = await customer_service.get_customer(identity.customer_id)
        if customer:
            update_data = {}
            if name:
                update_data["name"] = name
            if phone and not customer.phone:
                update_data["phone"] = phone
            if update_data:
                customer = await customer_service.update_customer(customer.id, **update_data)

    if not customer:
        customer = await customer_service.create_customer(
            tenant_id=tenant_id,
            openid=openid,
            name=name or "会员",
            phone=phone,
            tags=["小程序会员"],
        )
        is_new_customer = True
        await identity_service.bind_identity(
            customer_id=customer.id,
            channel=CHANNEL_MINIAPP,
            channel_user_id=openid,
            phone=phone,
        )

    # 确保用户有会员账户
    account = await MembershipService(db).ensure_account(customer)

    new_customer_coupon_result = None
    if is_new_customer:
        coupon_service = CouponService(db)
        new_customer_coupon_result = await coupon_service.issue_auto_coupon(
            customer.id,
            "new_customer_coupon"
        )
    
    entrance_result = None
    if entrance_code and is_new_customer:
        entrance_code = await entrance_service.record_member_conversion(
            entrance_scene,
            customer_id=customer.id,
            openid=openid,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        if entrance_code:
            entrance_result = await entrance_service.issue_new_customer_coupon(entrance_code, customer.id)

    token = create_customer_access_token(tenant_id, customer.id, openid=openid)
    return success_response(
        data={
            "token": token,
            "token_type": "bearer",
            "tenant_id": tenant_id,
            "customer_id": str(customer.id),
            "customer": serialize_customer(customer, account),
            "is_new_customer": is_new_customer,
            "entrance_scene": entrance_scene,
            "entrance": serialize_entrance(entrance_code),
            "new_customer_coupon": new_customer_coupon_result or entrance_result,
        },
        msg="登录成功",
    )


@router.get("/profile", response_model=RespVo)
async def profile(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    customer = await CustomerService(db).get_customer(customer_id)
    if not customer:
        return error_response(code=404, msg="顾客不存在")
    profile_log = (
        f"member profile resolved: tenant_id={tenant_id}, "
        f"token_customer_id={customer_id}, customer_id={customer.id}, phone={customer.phone}"
    )
    logger.info(profile_log)
    account = await MembershipService(db).get_account_by_customer(customer_id)
    return success_response(data=serialize_customer(customer, account), msg="ok")


@router.put("/profile", response_model=RespVo)
async def update_profile(request: Request, update_data: dict, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer(customer_id)
    if not customer:
        return error_response(code=404, msg="顾客不存在")
    
    update_fields = {}
    allowed_fields = ['name', 'avatar']
    for field in allowed_fields:
        if field in update_data and update_data[field] is not None:
            update_fields[field] = update_data[field]
    
    if update_fields:
        await customer_service.update_customer(customer_id, **update_fields)
        customer = await customer_service.get_customer(customer_id)
    
    account = await MembershipService(db).get_account_by_customer(customer_id)
    return success_response(data=serialize_customer(customer, account), msg="更新成功")


@router.post("/send-verify-code", response_model=RespVo)
async def send_verify_code(request: Request, phone: str, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    
    import random
    import re
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return error_response(code=400, msg="手机号格式不正确")
    
    code = str(random.randint(100000, 999999))
    
    redis_client = request.app.state.redis
    cache_key = f"phone_code:{tenant_id}:{phone}"
    await redis_client.setex(cache_key, 300, code)
    
    # TODO: 后续接入真实短信服务，当前仅记录日志
    print(f"[SMS] 验证码通知: 手机号 {phone} 的验证码为 {code}")
    
    return success_response(data={"expires_in": 300}, msg="验证码已发送")


@router.post("/bind-phone", response_model=RespVo)
async def bind_phone(request: Request, phone: str, code: str, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    
    redis_client = request.app.state.redis
    cache_key = f"phone_code:{tenant_id}:{phone}"
    cached_code = await redis_client.get(cache_key)
    
    if not cached_code:
        return error_response(code=400, msg="验证码已过期，请重新获取")
    
    if cached_code != code:
        return error_response(code=400, msg="验证码错误")
    
    await redis_client.delete(cache_key)
    
    customer_service = CustomerService(db)
    existing = await customer_service.get_customer_by_phone(phone, tenant_id)
    if existing and existing.id != customer_id:
        return error_response(code=400, msg="该手机号已被其他会员绑定")
    
    await customer_service.update_customer(customer_id, phone=phone)
    customer = await customer_service.get_customer(customer_id)
    account = await MembershipService(db).get_account_by_customer(customer_id)
    
    return success_response(data=serialize_customer(customer, account), msg="手机号绑定成功")


@router.get("/consumptions", response_model=RespVo)
async def consumptions(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    data = await ConsumptionService(db).get_customer_consumptions(customer_id)
    tenant_service = TenantService(db)
    tenant = await tenant_service.get_tenant(tenant_id)
    tenant_name = tenant.name if tenant else ""
    
    result = []
    for item in data:
        serialized = serialize_consumption(item)
        serialized["product_name"] = item.project
        serialized["tenant_name"] = tenant_name
        serialized["points_gained"] = 0
        serialized["coupon_issued"] = False
        result.append(serialized)
    return success_response(data=result, msg="ok")


@router.get("/consumptions/{consumption_id}", response_model=RespVo)
async def consumption_detail(request: Request, consumption_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    
    service = ConsumptionService(db)
    service.require_tenant_id()
    query = service.filter_by_tenant(select(Consumption), Consumption)
    query = query.filter(Consumption.id == consumption_id, Consumption.customer_id == customer_id)
    result = await service.db.execute(query)
    consumption = result.scalar_one_or_none()
    
    if not consumption:
        return error_response(code=404, msg="消费记录不存在")
    
    tenant_service = TenantService(db)
    tenant = await tenant_service.get_tenant(tenant_id)
    
    data = serialize_consumption(consumption)
    data["product_name"] = consumption.project
    data["tenant_name"] = tenant.name if tenant else ""
    data["points_gained"] = 0
    data["coupon_issued"] = False
    
    return success_response(data=data, msg="ok")


@router.get("/coupons", response_model=RespVo)
async def coupons(
    request: Request,
    status: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    skip, limit = normalize_pagination(skip, limit)
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    service = CouponService(db)
    data = await service.get_customer_coupons(customer_id, status, skip, limit)
    return success_response(data=[await serialize_coupon(item, service) for item in data], msg="ok")


@router.get("/coupons/{coupon_id}", response_model=RespVo)
async def coupon_detail(request: Request, coupon_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    service = CouponService(db)
    coupon = await service.get_customer_coupon(coupon_id, customer_id)
    if not coupon:
        return error_response(code=404, msg="优惠券不存在")
    return success_response(data=await serialize_coupon(coupon, service), msg="ok")


@router.get("/points", response_model=RespVo)
async def points_history(
    request: Request,
    skip: int = 0,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """积分明细"""
    from app.models.point_ledger import PointLedger
    skip, limit = normalize_pagination(skip, limit)
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    account = await MembershipService(db).get_account_by_customer(customer_id)
    result = await db.execute(
        select(PointLedger)
        .where(PointLedger.tenant_id == tenant_id, PointLedger.customer_id == customer_id)
        .order_by(PointLedger.created_at.desc())
        .offset(skip).limit(limit)
    )
    records = result.scalars().all()
    event_labels = {
        "register": "注册奖励", "consumption": "消费获积分", "invite": "邀请奖励",
        "deduct": "积分兑换", "expire": "积分过期", "manual": "人工调整",
    }
    return success_response(data={
        "balance": int(account.points_balance if account else 0),
        "records": [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "label": event_labels.get(r.event_type, r.event_type),
                "points": r.points,
                "balance_after": r.balance_after,
                "remark": r.remark,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    }, msg="ok")


@router.get("/balance", response_model=RespVo)
async def get_balance(request: Request, db: AsyncSession = Depends(get_db)):
    """查询储值余额"""
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    account = await MembershipService(db).get_account_by_customer(customer_id)
    bal = float(account.balance) if account and account.balance else 0.0
    return success_response(data={"balance": bal}, msg="ok")


@router.post("/recharge", response_model=RespVo)
async def recharge(request: Request, db: AsyncSession = Depends(get_db)):
    """储值充值入口。当前为模拟支付，仅限测试环境。生产环境需替换为真实微信支付回调。"""
    from decimal import Decimal as D
    from app.config import settings
    from app.models.member_account import MemberAccount

    # P0 安全锁：这里没有接真实支付，不能只靠 settings.DEBUG 拦截——这个项目
    # 实际部署环境里 DEBUG=true，不能拿来当"是否生产环境"的依据。必须显式开启
    # 一个专用开关才放行，默认关闭，防止任何登录用户凭空刷出真实可消费余额。
    if not settings.ALLOW_MOCK_MONEY_ENDPOINTS:
        return error_response(code=403, msg="储值充值功能暂未开放，敬请期待")

    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    TenantContext.set_tenant_id(tenant_id)
    try:
        body = await request.json()
    except Exception:
        return error_response(code=400, msg="请求体解析失败")
    amount = float(body.get("amount", 0))
    if amount < 1 or amount > 5000:
        return error_response(code=400, msg="充值金额需在 1 ~ 5000 元之间")
    membership_svc = MembershipService(db)
    account_result = await db.execute(
        select(MemberAccount).where(
            MemberAccount.tenant_id == tenant_id, MemberAccount.customer_id == customer_id
        ).with_for_update()
    )
    account = account_result.scalar_one_or_none()
    if not account:
        account = await membership_svc.get_or_create_account(customer_id)
    if not account:
        return error_response(code=404, msg="会员账户不存在")
    account.balance = D(str(float(account.balance or 0) + amount)).quantize(D("0.01"))
    await db.commit()
    await db.refresh(account)
    return success_response(
        data={"balance": float(account.balance), "recharged": amount},
        msg=f"充值 ¥{amount:.2f} 成功",
    )


@router.get("/verify-code", response_model=RespVo)
async def verify_code(request: Request):
    tenant_id, customer_id, error = current_customer(request)
    if error:
        return error
    return success_response(
        data={
            "type": "member",
            "tenant_id": tenant_id,
            "customer_id": str(customer_id),
            "code": f"M-{tenant_id}-{customer_id}",
        },
        msg="ok",
    )
