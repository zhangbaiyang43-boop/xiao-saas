from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import build_page, normalize_pagination
from app.core.response import RespVo, error_response, success_response
from app.core.time_utils import to_utc_iso
from app.schemas.coupon import RecallCouponRequest, SendCouponsRequest
from app.services.coupon_service import CouponService
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/api/v1/coupons", tags=["优惠券"])


async def serialize_coupon_record(
    coupon,
    coupon_service: CouponService,
    customer_service: CustomerService,
):
    try:
        template = None
        customer = None
        try:
            template = await coupon_service.get_template(coupon.template_id)
        except Exception as e:
            print(f"Warning: failed to get template {coupon.template_id}: {e}")

        try:
            if hasattr(customer_service, "get_customer_any_status"):
                customer = await customer_service.get_customer_any_status(coupon.customer_id)
            else:
                customer = await customer_service.get_customer(coupon.customer_id)
        except Exception as e:
            print(f"Warning: failed to get customer {coupon.customer_id}: {e}")

        identity_phone = ""
        if customer_service and hasattr(customer_service, "get_customer_identity_phone"):
            try:
                identity_phone = await customer_service.get_customer_identity_phone(coupon.customer_id) or ""
            except Exception as e:
                print(f"Warning: failed to get customer identity phone {coupon.customer_id}: {e}")

        return {
            "id": str(coupon.id),
            "tenant_id": coupon.tenant_id,
            "template_id": str(coupon.template_id),
            "template_name": template.name if template else "优惠券",
            "type": template.type if template else "FIXED",
            "rule_type": template.description if template else None,
            "value": float(template.value or 0) if template else 0,
            "min_amount": float(template.min_amount or 0) if template else 0,
            "customer_id": str(coupon.customer_id),
            "customer_name": customer.name if customer else "",
            "customer_phone": (customer.phone if customer else "") or identity_phone,
            "code": coupon.code,
            "status": coupon.status,
            "use_time": to_utc_iso(coupon.use_time),
            "expire_time": to_utc_iso(coupon.expire_time),
            "revoke_time": to_utc_iso(coupon.revoke_time),
            "revoke_reason": coupon.revoke_reason or "",
            "abnormal_reason": coupon.abnormal_reason or "",
            "created_at": to_utc_iso(coupon.created_at),
            "updated_at": to_utc_iso(coupon.updated_at),
        }
    except Exception as e:
        print(f"Error serializing coupon record: {e}")
        return {
            "id": str(coupon.id),
            "tenant_id": coupon.tenant_id,
            "template_id": str(coupon.template_id),
            "template_name": "优惠券",
            "type": "FIXED",
            "value": 0,
            "min_amount": 0,
            "customer_id": str(coupon.customer_id),
            "customer_name": "",
            "customer_phone": "",
            "code": coupon.code,
            "status": getattr(coupon, 'status', 'UNKNOWN'),
            "source": "",
            "use_time": None,
            "expire_time": None,
            "revoke_time": None,
            "revoke_reason": "",
            "abnormal_reason": "",
            "created_at": None,
            "updated_at": None,
        }


@router.post("/send", response_model=RespVo)
async def send_coupons(request: Request, db: AsyncSession = Depends(get_db)):
    from app.core.tenant_context import TenantContext
    
    # 1. 读取原始请求体
    body = await request.body()

    # 2. 直接解析JSON，不依赖Pydantic
    import json
    raw_data = json.loads(body)

    # 3. 使用原始数据，保持为字符串
    template_id = raw_data.get('template_id')
    customer_ids = raw_data.get('customer_ids', [])
    
    # 获取租户，支持从请求状态或上下文获取
    tenant_id = getattr(request.state, 'tenant_id', None)
    if not tenant_id:
        tenant_id = TenantContext.get_tenant_id()
    
    # 租户校验
    if not tenant_id:
        return error_response(code=401, msg="缺少租户信息")
    
    # 设置租户上下文
    TenantContext.set_tenant_id(tenant_id)

    service = CouponService(db)
    service.set_tenant_id(tenant_id)
    
    # 调用发券服务
    result = await service.send_coupons_with_result(template_id, customer_ids)

    # 返回结果
    if result["success_count"] == 0:
        return error_response(code=400, msg=result["reason"] or "发放失败", data=result)
    return success_response(data={**result, "count": result["success_count"]}, msg="发放完成")


@router.post("/recall-batch", response_model=RespVo)
async def batch_recall_coupons(
    request: Request,
    inactive_days: int = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    from app.core.tenant_context import TenantContext
    tenant_id = request.state.tenant_id
    if tenant_id:
        TenantContext.set_tenant_id(tenant_id)

    service = CouponService(db)
    result = await service.batch_issue_recall_coupon(inactive_days=inactive_days, limit=limit)

    if result["success_count"] == 0:
        return error_response(code=400, msg=result["reason"], data=result)

    return success_response(data=result, msg=f"成功发放{result['success_count']}张老客召回券")


@router.get("/issued", response_model=RespVo)
async def list_issued_coupons(
    request: Request,
    customer_id: int = None,
    status: str = None,
    source: str = None,
    keyword: str = None,
    start_date: str = None,
    end_date: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    try:
        tenant_id = request.state.tenant_id

        if not tenant_id:
            return error_response(code=401, msg="缺少租户信息")

        skip, limit = normalize_pagination(skip, limit)
        coupon_service = CouponService(db)
        coupon_service.set_tenant_id(tenant_id)
        customer_service = CustomerService(db)
        customer_service.set_tenant_id(tenant_id)

        coupons = await coupon_service.list_issued_coupons(
            customer_id=customer_id, 
            status=status,
            skip=skip, 
            limit=limit,
            source=source,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date
        )
        total = await coupon_service.count_issued_coupons(
            customer_id=customer_id, 
            status=status,
            source=source,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date
        )

        records = [
            await serialize_coupon_record(coupon, coupon_service, customer_service)
            for coupon in coupons
        ]

        return success_response(data=build_page(records, total, skip, limit), msg="ok")
    except Exception as e:
        print(f"Error in list_issued_coupons: {e}")
        import traceback
        traceback.print_exc()
        return error_response(code=500, msg=f"查询发券记录失败: {str(e)}")


@router.post("/{coupon_id}/recall", response_model=RespVo)
async def recall_coupon(
    coupon_id: int,
    data: RecallCouponRequest,
    db: AsyncSession = Depends(get_db),
):
    service = CouponService(db)
    result = await service.recall_coupon(coupon_id, data.reason)
    if not result["success"]:
        return error_response(
            code=400,
            msg=result["message"],
            data={"success": False, "coupon_id": str(coupon_id)},
        )

    customer_service = CustomerService(db)
    return success_response(
        data=await serialize_coupon_record(result["coupon"], service, customer_service),
        msg=result["message"],
    )


@router.get("/", response_model=RespVo)
async def get_customer_coupons(
    request: Request,
    customer_id: int,
    status: str = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    from app.core.tenant_context import TenantContext
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return error_response(code=401, msg="缺少租户信息")

    skip, limit = normalize_pagination(skip, limit)

    customer_service = CustomerService(db)
    customer_service.set_tenant_id(tenant_id)
    customer = await customer_service.get_customer(customer_id)
    if not customer:
        return error_response(code=404, msg="客户不存在")

    coupon_service = CouponService(db)
    coupon_service.set_tenant_id(tenant_id)
    coupons = await coupon_service.get_customer_coupons(customer_id, status, skip, limit)
    total = await coupon_service.count_customer_coupons(customer_id, status)

    records = [
        await serialize_coupon_record(coupon, coupon_service, customer_service)
        for coupon in coupons
    ]
    return success_response(data=build_page(records, total, skip, limit), msg="ok")
