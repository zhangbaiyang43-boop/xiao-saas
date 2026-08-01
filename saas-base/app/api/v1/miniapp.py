from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.core.database import get_db
from app.core.rate_limiter import join_limit
from app.core.response import RespVo, error_response, success_response
from app.core.security import create_customer_access_token
from app.core.tenant_context import TenantContext
from app.core.logger import logger
from app.config import settings
from app.schemas.miniapp import EntryJoinRequest, MiniAppLoginRequest
from app.services.anti_fraud_service import AntiFraudService
from app.services.commission_service import CommissionService
from app.services.coupon_service import CouponService
from app.services.customer_operation_log_service import CustomerOperationLogService
from app.services.customer_service import CustomerService
from app.services.customer_identity_service import CHANNEL_MINIAPP, CustomerIdentityService
from app.services.entrance_code_service import EntranceCodeService
from app.services.membership_service import MembershipService
from app.services.tenant_service import TenantService
from app.services.wechat_service import WechatService

router = APIRouter(prefix="/api/v1/miniapp", tags=["小程序端"])


def current_member(request: Request):
    tenant_id = getattr(request.state, "tenant_id", None)
    customer_id = getattr(request.state, "customer_id", None)
    if not tenant_id or not customer_id:
        return None, None, error_response(code=401, msg="会员未登录或登录已过期")
    return tenant_id, int(customer_id), None


async def require_active_member(request: Request, db: AsyncSession):
    tenant_id, customer_id, error = current_member(request)
    if error:
        return None, None, None, error

    TenantContext.set_tenant_id(tenant_id)
    customer_service = CustomerService(db)
    customer_service.set_tenant_id(tenant_id)
    customer = await customer_service.get_customer(customer_id)
    if not customer:
        return tenant_id, customer_id, None, error_response(code=403, msg="会员不存在或已停用")
    return tenant_id, customer_id, customer, None


async def serialize_member_profile(customer, member_account, coupon_count):
    return {
        "customer_id": str(customer.id),
        "name": customer.name or "会员",
        "phone": customer.phone or "",
        "level_code": member_account.level_code if member_account else "LV1",
        "level_name": member_account.level_name if member_account else "普通会员",
        "points_balance": member_account.points_balance if member_account else 0,
        "total_consumption": float(member_account.total_consumption) if member_account else 0.0,
        "yearly_consumption": float(member_account.yearly_consumption) if member_account else 0.0,
        "available_coupon_count": coupon_count.get("UNUSED", 0),
        "used_coupon_count": coupon_count.get("USED", 0),
        "expired_coupon_count": coupon_count.get("EXPIRED", 0),
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
        "last_consume_time": customer.last_consume_time.isoformat() if customer.last_consume_time else None,
    }


async def serialize_coupon(coupon, template):
    now = datetime.utcnow()
    status = coupon.status
    if status == "UNUSED" and coupon.expire_time and coupon.expire_time < now:
        status = "EXPIRED"
    
    return {
        "id": str(coupon.id),
        "code": coupon.code,
        "name": template.name if template else "优惠券",
        "type": template.type if template else "FIXED",
        "value": template.value if template else 0,
        "min_amount": template.min_amount if template else 0,
        "status": status,
        "expire_time": coupon.expire_time.isoformat() if coupon.expire_time else None,
        "use_time": coupon.use_time.isoformat() if coupon.use_time else None,
        "created_at": coupon.created_at.isoformat() if coupon.created_at else None,
    }


async def serialize_point_log(ledger):
    return {
        "id": str(ledger.id),
        "event_type": ledger.event_type,
        "points": ledger.points,
        "balance_after": ledger.balance_after,
        "remark": ledger.remark or "",
        "source_channel": ledger.source_channel,
        "created_at": ledger.created_at.isoformat() if ledger.created_at else None,
    }


def build_auto_member_name(phone: str | None) -> str:
    clean_phone = (phone or "").strip()
    if len(clean_phone) >= 4:
        return f"尾号{clean_phone[-4:]}会员"
    return "小程序顾客"


@router.post("/login", response_model=RespVo)
async def miniapp_login(data: MiniAppLoginRequest, db: AsyncSession = Depends(get_db)):
    tenant_service = TenantService(db)
    tenant = await tenant_service.get_tenant(data.store_id)
    if not tenant or not tenant.status:
        return error_response(code=404, msg="门店不存在或已停用")

    TenantContext.set_tenant_id(data.store_id)
    
    # 閻?code 閹广垹褰?openid
    wechat_service = WechatService()
    wechat_result = await wechat_service.code2session(data.code)
    openid = wechat_result.get("openid")
    unionid = wechat_result.get("unionid")
    
    if not openid:
        return error_response(code=400, msg="微信登录失败")

    customer_service = CustomerService(db)
    identity_service = CustomerIdentityService(db)
    membership_service = MembershipService(db)

    identity = await identity_service.get_by_identity(CHANNEL_MINIAPP, openid)
    customer = None
    if identity:
        customer = await customer_service.get_customer(identity.customer_id)

    if not customer:
        customer = await customer_service.create_customer(
            tenant_id=data.store_id,
            openid=openid,
            name="小程序顾客",
            tags=["小程序会员"],
        )
        await identity_service.bind_identity(
            customer_id=customer.id,
            channel=CHANNEL_MINIAPP,
            channel_user_id=openid,
            unionid=unionid
        )
        await membership_service.ensure_account(customer)

    token = create_customer_access_token(data.store_id, customer.id, openid=openid)
    
    member_account = await membership_service.get_account_by_customer(customer.id)
    
    return success_response(data={
        "token": token,
        "token_type": "bearer",
        "store_id": data.store_id,
        "customer_id": str(customer.id),
        "profile": await serialize_member_profile(customer, member_account, {}),
    }, msg="登录成功")


@router.post("/entry/join", response_model=RespVo)
@join_limit()
async def entry_join(request: Request, data: EntryJoinRequest, db: AsyncSession = Depends(get_db)):
    try:
        logger.info(f"entry_join 请求 - scene: {data.scene}, phone: {data.phone}")
        if not data.agreement_accepted:
            return error_response(code=400, msg="请先阅读并同意注册协议")
        
        entrance_service = EntranceCodeService(db)
        entrance_code = None
        if data.scene:
            entrance_code = await entrance_service.get_by_scene(data.scene)
            if not entrance_code or entrance_code.status != 1:
                logger.warning(f"入口码无效或已停用 - scene: {data.scene}")
                return error_response(code=404, msg="入口码无效，请重新扫码")
            tenant_id = entrance_code.tenant_id
            logger.info(f"通过入口码找到租户 - tenant_id: {tenant_id}")
        elif data.tenant_id:
            tenant_id = data.tenant_id
            logger.info(f"通过 tenant_id 直接入会 - tenant_id: {tenant_id}, invite_code: {data.invite_code}")
        else:
            return error_response(code=400, msg="缺少入口码或商家信息，请重新扫码")

        tenant_service = TenantService(db)
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant or not tenant.status:
            logger.warning(f"商家不存在或已停用 - tenant_id: {tenant_id}")
            return error_response(code=404, msg="商家不存在或已停用")

        TenantContext.set_tenant_id(tenant_id)

        # 用 code 换取 openid
        wechat_service = WechatService()
        wechat_result = await wechat_service.code2session(data.code)
        openid = wechat_result.get("openid")
        unionid = wechat_result.get("unionid")
        logger.info(f"微信 code2session 结果 - openid: {openid}, unionid: {unionid}")

        if not openid:
            logger.error("微信登录失败，未获取到 openid")
            return error_response(code=400, msg="微信登录失败，请重试")

        phone = (data.phone or "").strip()
        # phone_verified 标记这个手机号是否经过微信 getPhoneNumber 验证——只有验证过的
        # 手机号才能用来把当前微信身份自动绑定/顶替到一个已存在的会员账号上，否则任何
        # 人只要知道受害者手机号，用自己的微信身份就能把对方账号接管了（P0）。
        phone_verified = False
        if not phone and data.phone_code:
            try:
                phone = await wechat_service.get_phone_number(data.phone_code)
                phone_verified = bool(phone)
            except Exception as phone_error:
                logger.warning(f"手机号获取失败 - error: {phone_error}")
                return error_response(code=400, msg="手机号获取失败，请重试或手动输入手机号")
        if not phone:
            return error_response(code=400, msg="请填写手机号或使用手机号快速登录")
        data.phone = phone
        auto_member_name = build_auto_member_name(phone)

        customer_id_for_log = None
        customer_service = CustomerService(db)
        identity_service = CustomerIdentityService(db)
        membership_service = MembershipService(db)
        coupon_service = CouponService(db)
        operation_log_service = CustomerOperationLogService(db)
        customer_service.set_tenant_id(tenant_id)
        identity_service.set_tenant_id(tenant_id)
        membership_service.set_tenant_id(tenant_id)
        coupon_service.set_tenant_id(tenant_id)
        operation_log_service.set_tenant_id(tenant_id)
        commission_service = CommissionService(db)
        commission_service.set_tenant_id(tenant_id)

        customer = None
        is_new_customer = False
        phone_customer = await customer_service.get_customer_by_phone_any_status(data.phone, tenant_id) if data.phone else None
        logger.info(
            f"phone lookup result - phone: {data.phone}, found: {bool(phone_customer)}, "
            f"customer_id: {getattr(phone_customer, 'id', None)}, "
            f"customer_phone: {getattr(phone_customer, 'phone', None)}"
        )

        async def update_join_customer_info(existing_customer):
            update_data = {}
            if existing_customer.name in (None, "", "会员", "小程序顾客"):
                update_data["name"] = auto_member_name
            if data.phone and existing_customer.phone != data.phone:
                update_data["phone"] = data.phone
            if openid and existing_customer.openid != openid:
                openid_customer = await customer_service.get_customer_by_openid_any_status(openid, tenant_id)
                if not openid_customer or openid_customer.id == existing_customer.id:
                    update_data["openid"] = openid
                else:
                    logger.info(
                        f"当前 customer.openid 已被其他会员占用，跳过更新 - "
                        f"current_customer_id: {existing_customer.id}, openid_customer_id: {openid_customer.id}"
                    )
            if update_data:
                logger.info(f"更新会员信息 - customer_id: {existing_customer.id}, update_data: {update_data}")
                return await customer_service.update_customer(existing_customer.id, **update_data)
            return existing_customer

        identity = await identity_service.get_by_identity(CHANNEL_MINIAPP, openid)
        identity_customer_id = identity.customer_id if identity else None

        # Phone is the member account key in the MVP. The WeChat openid is only the login
        # credential and can be rebound when the same device switches to another phone.
        #
        # 但这个"顶号"能力必须只对手机号本人开放：如果当前微信身份（openid）本来就不是
        # 这个账号的绑定身份，又是靠一个没经过微信验证的手填手机号才匹配上的，那就没有
        # 任何证据证明操作者真的拥有这个手机号——必须拒绝，引导用户走"微信授权手机号"
        # 验证流程，而不是直接把账号让出去。
        if phone_customer:
            already_owns = bool(identity_customer_id) and identity_customer_id == phone_customer.id
            if not phone_verified and not already_owns:
                logger.warning(
                    f"未验证手机号匹配到已有会员，拒绝自动绑定 - "
                    f"phone_customer_id: {phone_customer.id}, openid: {openid}, phone: {data.phone}"
                )
                await operation_log_service.record(
                    customer_id=phone_customer.id,
                    action="miniapp_join_unverified_phone_rebind_blocked",
                    source="miniapp",
                    actor_type="customer",
                    phone=data.phone,
                    openid=openid,
                    detail={
                        "message": "手填手机号匹配到已有会员但未经微信验证，已拒绝绑定",
                        "scene": data.scene,
                    },
                )
                return error_response(code=409, msg="该手机号已绑定其他会员，请使用微信授权手机号完成登录")
            customer = phone_customer
            if customer.status != 1:
                await operation_log_service.record(
                    customer_id=customer.id,
                    action="miniapp_join_blocked_disabled",
                    source="miniapp",
                    actor_type="customer",
                    phone=data.phone,
                    openid=openid,
                    detail={
                        "message": "会员已停用，阻止小程序入会",
                        "scene": data.scene,
                        "matched_by": "phone",
                        "blocked_customer_id": str(customer.id),
                    },
                )
                return error_response(code=403, msg="会员已停用，请联系商家")
            logger.info(f"手机号找到会员 - customer_id: {customer.id}, phone: {data.phone}")
            if identity_customer_id and identity_customer_id != customer.id:
                logger.info(
                    f"手机号已切换会员，openid 从旧会员迁移到当前手机号会员 - "
                    f"old_customer_id: {identity_customer_id}, new_customer_id: {customer.id}, phone: {data.phone}"
                )
                await operation_log_service.record(
                    customer_id=customer.id,
                    action="miniapp_phone_switch",
                    source="miniapp",
                    actor_type="customer",
                    phone=data.phone,
                    openid=openid,
                    detail={
                        "message": "同一微信身份切换手机号登录，已重新绑定到当前手机号会员",
                        "scene": data.scene,
                        "old_customer_id": str(identity_customer_id),
                        "new_customer_id": str(customer.id),
                    },
                )
            await identity_service.rebind_identity(
                customer_id=customer.id,
                channel=CHANNEL_MINIAPP,
                channel_user_id=openid,
                phone=data.phone,
                unionid=unionid
            )
            logger.info(f"重绑 identity（已有会员）- customer_id: {customer.id}, openid: {openid}")
            customer = await update_join_customer_info(customer)

        if not customer and identity_customer_id:
            # 手机号没查到匹配（顾客换手机号了），但这个微信身份本来就有账号——必须复用
            # 它，不能借口"手机号没查到"就当成新客户另建一个：那样会把老账号的积分/
            # 等级/优惠券/消费记录全部撇下，顾客只是换个手机号登录，资产却"清零"了。
            existing_customer = await customer_service.get_customer_any_status(identity_customer_id)
            if existing_customer:
                if existing_customer.status != 1:
                    await operation_log_service.record(
                        customer_id=existing_customer.id,
                        action="miniapp_join_blocked_disabled",
                        source="miniapp",
                        actor_type="customer",
                        phone=data.phone,
                        openid=openid,
                        detail={
                            "message": "会员已停用，阻止小程序入会",
                            "scene": data.scene,
                            "matched_by": "identity",
                            "blocked_customer_id": str(existing_customer.id),
                        },
                    )
                    return error_response(code=403, msg="会员已停用，请联系商家")
                logger.info(
                    f"identity 找到已有会员（手机号已更换）- customer_id: {existing_customer.id}, "
                    f"old_phone: {existing_customer.phone}, new_phone: {data.phone}"
                )
                await operation_log_service.record(
                    customer_id=existing_customer.id,
                    action="miniapp_phone_number_changed",
                    source="miniapp",
                    actor_type="customer",
                    phone=data.phone,
                    openid=openid,
                    detail={
                        "message": "同一微信身份填写了新手机号，已更新账号手机号并保留原有资产",
                        "scene": data.scene,
                        "old_phone": existing_customer.phone,
                    },
                )
                customer = await update_join_customer_info(existing_customer)
                is_new_customer = False

        if not customer:
            customer_openid = openid
            openid_customer = await customer_service.get_customer_by_openid_any_status(openid, tenant_id)
            if openid_customer:
                customer_openid = f"phone:{data.phone}"
                logger.info(
                    f"openid 已绑定到其他会员，当前用手机号注册新会员 - "
                    f"openid_customer_id: {openid_customer.id}, phone: {data.phone}"
                )
            customer = await customer_service.create_customer(
                tenant_id=tenant_id,
                openid=customer_openid,
                name=auto_member_name,
                phone=data.phone,
                tags=["小程序会员"],
            )
            if data.phone and customer.phone != data.phone:
                logger.warning(
                    f"create_customer returned mismatched phone - "
                    f"customer_id: {customer.id}, customer_phone: {customer.phone}, request_phone: {data.phone}"
                )
                matched_phone_customer = await customer_service.get_customer_by_phone_any_status(data.phone, tenant_id)
                if matched_phone_customer and matched_phone_customer.id != customer.id:
                    customer = matched_phone_customer
                    is_new_customer = False
                else:
                    customer = await customer_service.update_customer(
                        customer.id,
                        phone=data.phone,
                        name=customer.name or auto_member_name,
                    )
                    is_new_customer = False
            else:
                is_new_customer = True
            logger.info(f"新会员已建 - customer_id: {customer.id}, is_new_customer: {is_new_customer}")

            # 绑定 identity
            await identity_service.rebind_identity(
                customer_id=customer.id,
                channel=CHANNEL_MINIAPP,
                channel_user_id=openid,
                phone=data.phone,
                unionid=unionid
            )
            logger.info(f"重绑 identity（新会员）- customer_id: {customer.id}, openid: {openid}")

        await membership_service.ensure_account(customer)
        if is_new_customer and data.invite_code:
            customer = await commission_service.bind_inviter_for_new_customer(customer, data.invite_code)
        customer_id_for_log = customer.id
        logger.info(f"确认会员  - customer_id: {customer.id}")

        # 生成 token
        token = create_customer_access_token(tenant_id, customer.id, openid=openid)
        logger.info(f"生成 token 完成 - customer_id: {customer.id}")

        # Issue welcome coupon once. Coupon failure must not block member join.
        coupon_data = None
        coupon_error = None
        existing_welcome_coupon = await coupon_service.get_available_auto_coupon(customer.id, "new_customer_coupon")
        if existing_welcome_coupon:
            template = await coupon_service.get_template(existing_welcome_coupon.template_id)
            coupon_data = {
                "id": str(existing_welcome_coupon.id),
                "name": template.name if template else "新人券",
                "amount": float(template.value) if template else 0,
                "min_amount": float(template.min_amount) if template else 0,
                "expired_at": existing_welcome_coupon.expire_time.isoformat() if existing_welcome_coupon.expire_time else None,
            }
            logger.info(f"已有新人券，跳过发放 - customer_id: {customer.id}, coupon_id: {existing_welcome_coupon.id}")
        else:
            try:
                coupon_service.set_tenant_id(tenant_id)
                if entrance_code and data.scene:
                    await entrance_service.record_member_conversion(
                        data.scene,
                        customer_id=customer.id,
                        openid=openid,
                        ip=None,
                        user_agent=None,
                    )
                coupon_result = await coupon_service.issue_auto_coupon(customer.id, "new_customer_coupon")
                if coupon_result and coupon_result.get("success_count", 0) > 0:
                    sent_coupons = coupon_result.get("sent", [])
                    if sent_coupons:
                        coupon_info = sent_coupons[0]
                        template = await coupon_service.get_template(coupon_info.get("template_id"))
                        coupon_data = {
                            "id": coupon_info.get("id"),
                            "name": template.name if template else "新人券",
                            "amount": float(template.value) if template else 0,
                            "min_amount": float(template.min_amount) if template else 0,
                            "expired_at": coupon_info.get("expire_time"),
                        }
                    logger.info(f"新人券发放成功 - customer_id: {customer.id}, coupon_data: {coupon_data}")
                else:
                    coupon_error = (coupon_result or {}).get("reason") or "新人券未配置"
                    logger.info(f"新人券未发放 - customer_id: {customer.id}, coupon_result: {coupon_result}")
            except Exception as coupon_exc:
                await db.rollback()
                coupon_error = "新人券发放失败，请稍后重试"  # BUG-G fix
                logger.exception(f"新人券发放异常，已回滚券相关事务 - customer_id: {customer_id_for_log}, error: {coupon_error}")
        logger.info(f"入会完成 - customer_id: {customer.id}, tenant_id: {tenant_id}, is_new_customer: {is_new_customer}")
        await operation_log_service.record(
            customer_id=customer.id,
            action="miniapp_join_success",
            source="miniapp",
            actor_type="customer",
            phone=data.phone,
            openid=openid,
            detail={
                "message": "扫码入会成功" if is_new_customer else "老会员重新进入小程序",
                "scene": data.scene,
                "is_new_customer": is_new_customer,
                "coupon_id": coupon_data.get("id") if coupon_data else None,
            },
        )
        
        return success_response(data={
            "token": token,
            "tenant_id": tenant_id,
            "customer_id": str(customer.id),
            "phone": customer.phone or data.phone or "",
            "customer": {
                "id": str(customer.id),
                "name": customer.name or "会员",
                "phone": customer.phone or "",
            },
            "is_new_customer": is_new_customer,
            "entrance_scene": data.scene,
            "invite_code": data.invite_code,
            "entrance": {
                "id": str(entrance_code.id) if entrance_code else None,
                "tenant_id": entrance_code.tenant_id if entrance_code else tenant_id,
                "scene": entrance_code.scene if entrance_code else None,
                "channel": entrance_code.channel if entrance_code else "INVITE",
                "name": entrance_code.name if entrance_code else "好友邀请",
            },
            "coupon": coupon_data,
            "new_customer_coupon": coupon_data,
            "coupon_error": coupon_error if coupon_error in (None, "新人券未配置", "新人券发放失败，请稍后重试") else "新人券发放失败，请稍后重试",
        }, msg="入会成功")

    except Exception as e:
        logger.exception(f"entry_join 顶层异常 - scene: {data.scene}, phone: {data.phone}, error: {str(e)}")
        return error_response(code=500, msg="入会失败，请稍后重试")


@router.get("/member/profile", response_model=RespVo)
async def member_profile(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error
    
    TenantContext.set_tenant_id(tenant_id)
    
    membership_service = MembershipService(db)
    coupon_service = CouponService(db)
    
    member_account = await membership_service.get_account_by_customer(customer_id)
    coupon_service.set_tenant_id(tenant_id)

    # BUG-C 修复：与券包页保持相同的过期判断逻辑
    # 可用 = DB status=UNUSED 且 expire_time 未到期（运行时判断，与券包展示一致）
    # 已过期 = DB status=EXPIRED + DB status=UNUSED 但已到期的数量之和
    available_count = await coupon_service.count_customer_coupons(customer_id, "UNUSED", not_expired=True)
    used_count      = await coupon_service.count_customer_coupons(customer_id, "USED")
    db_expired      = await coupon_service.count_customer_coupons(customer_id, "EXPIRED")
    all_unused      = await coupon_service.count_customer_coupons(customer_id, "UNUSED")
    expired_count   = db_expired + max(0, all_unused - available_count)

    coupon_count = {
        "UNUSED": available_count,
        "USED": used_count,
        "EXPIRED": expired_count,
    }

    return success_response(data=await serialize_member_profile(customer, member_account, coupon_count), msg="ok")


@router.get("/member/invite", response_model=RespVo)
async def member_invite(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error

    TenantContext.set_tenant_id(tenant_id)
    service = CommissionService(db)
    service.set_tenant_id(tenant_id)
    summary = await service.summary_for_customer(customer_id)
    # summary["invite_code"] 已是短邀请码（6 位），用于分享路径
    summary.update({
        "tenant_id": tenant_id,
        "invite_path": f"pages/entry/index?tenant_id={tenant_id}&invite_code={summary['invite_code']}",
        "share_title": "邀请朋友领优惠券",
    })
    return success_response(data=summary, msg="ok")


@router.get("/member/commission-records", response_model=RespVo)
async def member_commission_records(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error

    TenantContext.set_tenant_id(tenant_id)
    service = CommissionService(db)
    service.set_tenant_id(tenant_id)
    records, total = await service.list_records(receiver_id=customer_id, skip=skip, limit=limit)
    return success_response(
        data={
            "items": [
                {
                    "id": str(item.id),
                    "user_id": str(item.user_id),
                    "amount": float(item.amount or 0),
                    "level": item.level,
                    "commission_amount": float(item.commission_amount or 0),
                    "status": item.status,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in records
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
        msg="ok",
    )


@router.get("/member/coupons", response_model=RespVo)
async def member_coupons(
    request: Request,
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error
    
    TenantContext.set_tenant_id(tenant_id)
    
    coupon_service = CouponService(db)
    
    all_coupons = await coupon_service.get_customer_coupons(customer_id)
    
    available = []
    used = []
    expired = []
    
    now = datetime.utcnow()
    
    # BUG-09: 批量加载模，避免 N+1 查询
    template_ids = [c.template_id for c in all_coupons]
    templates = await coupon_service.get_templates_batch(template_ids)

    for coupon in all_coupons:
        template = templates.get(coupon.template_id)
        serialized = await serialize_coupon(coupon, template)
        
        if coupon.status == "UNUSED":
            if coupon.expire_time and coupon.expire_time < now:
                expired.append(serialized)
            else:
                available.append(serialized)
        elif coupon.status == "USED":
            used.append(serialized)
        elif coupon.status == "EXPIRED":
            expired.append(serialized)
    
    selected = None
    if status == "UNUSED":
        selected = available
    elif status == "USED":
        selected = used
    elif status == "EXPIRED":
        selected = expired

    return success_response(data={
        "list": selected if selected is not None else available + used + expired,
        "available": available,
        "used": used,
        "expired": expired,
    }, msg="ok")


@router.get("/member/points/logs", response_model=RespVo)
async def member_points_logs(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error
    
    TenantContext.set_tenant_id(tenant_id)
    
    membership_service = MembershipService(db)
    logs = await membership_service.list_point_ledger(customer_id)
    
    return success_response(data=[await serialize_point_log(log) for log in logs], msg="ok")


@router.get("/member/coupons/{coupon_id}/verify-code", response_model=RespVo)
async def coupon_verify_code(request: Request, coupon_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error

    TenantContext.set_tenant_id(tenant_id)
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    openid = getattr(request.state, "openid", None)
    if not await AntiFraudService.allow_frequency(
        "member_verify_code",
        f"{tenant_id}:{openid or customer_id or ip}",
        {"tenant_id": tenant_id, "customer_id": str(customer_id), "openid": openid, "ip": ip},
    ):
        return error_response(code=429, msg="操作过于频繁，请稍后再试")

    coupon_service = CouponService(db)

    coupon = await coupon_service.get_customer_coupon(coupon_id, customer_id)
    if not coupon:
        return error_response(code=404, msg="优惠券不存在")

    if coupon.status != "UNUSED":
        return error_response(code=400, msg="优惠券已使用或已过期")
    if coupon.expire_time and coupon.expire_time < datetime.utcnow():
        return error_response(code=400, msg="优惠券已过期")

    template = await coupon_service.get_template(coupon.template_id)
    dynamic_code = AntiFraudService.build_dynamic_verify_code(
        tenant_id=tenant_id,
        coupon_id=coupon.id,
        customer_id=customer_id,
        coupon_code=coupon.code,
        ttl_seconds=settings.VERIFY_CODE_TTL_SECONDS,
    )

    verify_code = coupon.verify_code
    if not verify_code:
        verify_code = await coupon_service.assign_verify_code(coupon)

    return success_response(data={
        "coupon_id": str(coupon.id),
        "code": dynamic_code,
        "static_code": coupon.code,
        "verify_code": verify_code,
        "expires_in": settings.VERIFY_CODE_TTL_SECONDS,
        "refresh_after": settings.VERIFY_CODE_REFRESH_SECONDS,
        "name": template.name if template else "优惠券",
        "value": template.value if template else 0,
        "min_amount": template.min_amount if template else 0,
        "expire_time": coupon.expire_time.isoformat() if coupon.expire_time else None,
    }, msg="ok")


@router.get("/invite/summary", response_model=RespVo)
async def invite_summary(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error

    TenantContext.set_tenant_id(tenant_id)
    service = CommissionService(db)
    service.set_tenant_id(tenant_id)
    summary = await service.get_invite_summary_for_member(customer_id)
    # summary["invite_code"] 已是短邀请码（6 位），用于分享路径
    summary["tenant_id"] = tenant_id
    summary["invite_path"] = f"pages/entry/index?tenant_id={tenant_id}&invite_code={summary['invite_code']}"
    return success_response(data=summary, msg="ok")


@router.get("/invite/records", response_model=RespVo)
async def invite_records(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error

    TenantContext.set_tenant_id(tenant_id)
    service = CommissionService(db)
    service.set_tenant_id(tenant_id)
    rows = await service.list_invite_records_for_member(customer_id, skip=skip, limit=limit)
    return success_response(data=rows, msg="ok")


@router.post("/invite/bind", response_model=RespVo)
async def invite_bind(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error

    TenantContext.set_tenant_id(tenant_id)
    try:
        import json as _json
        raw = await request.body()
        body = _json.loads(raw) if raw else {}
    except Exception:
        return error_response(code=400, msg="请求体解析失败")

    invite_code = str(body.get("invite_code") or body.get("inviter_member_id") or "").strip()
    if not invite_code:
        return error_response(code=400, msg="请提供邀请码")

    if customer.inviter_id:
        return success_response(data={"bound": False, "reason": "已绑定过邀请人"}, msg="已绑定过邀请人")

    service = CommissionService(db)
    service.set_tenant_id(tenant_id)
    updated = await service.bind_inviter_for_new_customer(customer, invite_code)
    if updated.inviter_id:
        return success_response(data={"bound": True}, msg="邀请关系绑定成功")
    return error_response(code=400, msg="邀请码无效或不允许绑定")


@router.get("/member/coupons/{coupon_id}", response_model=RespVo)
async def member_coupon_detail(request: Request, coupon_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id, customer_id, customer, error = await require_active_member(request, db)
    if error:
        return error
    
    TenantContext.set_tenant_id(tenant_id)
    
    coupon_service = CouponService(db)
    
    coupon = await coupon_service.get_customer_coupon(coupon_id, customer_id)
    if not coupon:
        return error_response(code=404, msg="优惠券不存在")
    
    template = await coupon_service.get_template(coupon.template_id)
    
    return success_response(data={
        "id": str(coupon.id),
        "code": coupon.code,
        "name": template.name if template else "优惠券",
        "type": template.type if template else "FIXED",
        "value": float(template.value or 0) if template else 0,
        "min_amount": float(template.min_amount or 0) if template else 0,
        "status": coupon.status,
        "expire_time": coupon.expire_time.isoformat() if coupon.expire_time else None,
        "created_at": coupon.created_at.isoformat() if coupon.created_at else None,
        "used_at": coupon.use_time.isoformat() if coupon.use_time else None,
    }, msg="ok")
