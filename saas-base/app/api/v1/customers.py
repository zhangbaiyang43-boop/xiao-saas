from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import build_page, normalize_pagination
from app.core.response import RespVo, error_response, success_response
from app.schemas.customer import (
    CreateCustomerRequest,
    MergeCustomerRequest,
    UpdateCustomerRequest,
    UpdateCustomerStatusRequest,
)
from app.services.customer_identity_service import CustomerIdentityService
from app.services.customer_operation_log_service import CustomerOperationLogService
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/api/v1/customers", tags=["客户管理"])


def serialize_customer(customer, source=None, account=None):
    data = {
        "id": str(customer.id),
        "tenant_id": customer.tenant_id,
        "store_member_no": customer.store_member_no,
        "openid": customer.openid,
        "external_userid": customer.external_userid,
        "name": customer.name,
        "phone": customer.phone,
        "tags": customer.tags or [],
        "last_consume_time": customer.last_consume_time,
        "status": customer.status,
        "source": source,
        "points": 0,
        "level_name": "普通会员",
        "level": "LV1",
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
    }
    if account:
        data["points"] = int(account.points_balance or 0)
        data["level_name"] = account.level_name or "普通会员"
        data["level"] = account.level_code or "LV1"
    return data


def serialize_identity(identity):
    return {
        "id": str(identity.id),
        "customer_id": str(identity.customer_id),
        "channel": identity.channel,
        "channel_user_id": identity.channel_user_id,
        "phone": identity.phone,
        "unionid": identity.unionid,
        "bind_time": identity.bind_time,
    }


def serialize_operation_log(item):
    return {
        "id": str(item.id),
        "customer_id": str(item.customer_id) if item.customer_id else None,
        "action": item.action,
        "source": item.source,
        "actor_type": item.actor_type,
        "actor_id": item.actor_id,
        "actor_name": item.actor_name,
        "phone": item.phone,
        "openid": item.openid,
        "detail": item.detail or {},
        "created_at": item.created_at,
    }


def build_disabled_fallback_log(customer):
    event_time = customer.deleted_at or customer.updated_at or customer.created_at
    return {
        "id": f"disabled-{customer.id}",
        "customer_id": str(customer.id),
        "action": "system_disabled_snapshot",
        "source": "system",
        "actor_type": "system",
        "actor_id": None,
        "actor_name": "系统识别",
        "phone": customer.phone,
        "openid": customer.openid,
        "detail": {
            "message": "该会员当前已停用。历史停用发生在操作日志上线前时，会显示这条系统兜底记录。",
            "status": customer.status,
            "deleted_at": customer.deleted_at.isoformat() if customer.deleted_at else None,
        },
        "created_at": event_time,
    }


def merchant_actor(request: Request):
    return {
        "actor_type": "merchant",
        "actor_id": getattr(request.state, "user_id", None),
        "actor_name": "商家后台",
    }


def is_disabled_customer(customer):
    return customer.status != 1


async def build_customer_logs(db, customer, skip=0, limit=50):
    log_service = CustomerOperationLogService(db)
    log_service.set_tenant_id(customer.tenant_id)
    logs = await log_service.list_by_customer(customer.id, skip=skip, limit=limit)
    data = [serialize_operation_log(item) for item in logs]
    if is_disabled_customer(customer) and not data:
        data = [build_disabled_fallback_log(customer)]
    return data


async def record_customer_log(db, tenant_id, customer, action, request=None, detail=None, source="admin"):
    log_service = CustomerOperationLogService(db)
    log_service.set_tenant_id(tenant_id)
    actor = merchant_actor(request) if request else {}
    return await log_service.record(
        customer_id=customer.id,
        action=action,
        source=source,
        phone=customer.phone,
        openid=customer.openid,
        detail=detail or {},
        **actor,
    )


@router.get("/", response_model=RespVo)
async def list_customers(
    search: str = None,
    tag: str = None,
    skip: int = 0,
    limit: int = 100,
    page: int = None,
    page_size: int = None,
    db: AsyncSession = Depends(get_db),
):
    from app.core.tenant_context import TenantContext
    from app.models.member_account import MemberAccount
    from sqlalchemy.future import select

    tenant_id = TenantContext.get_tenant_id()
    if page and page_size:
        skip = (page - 1) * page_size
        limit = page_size
    skip, limit = normalize_pagination(skip, limit)

    service = CustomerService(db)
    customers, total = await service.list_customers(
        tenant_id=tenant_id,
        phone=search,
        name=search,
        tag=tag,
        skip=skip,
        limit=limit,
    )

    customer_ids = [item.id for item in customers]
    accounts = {}
    if customer_ids:
        result = await db.execute(select(MemberAccount).where(MemberAccount.customer_id.in_(customer_ids)))
        for account in result.scalars().all():
            accounts[account.customer_id] = account

    return success_response(
        data=build_page([serialize_customer(item, account=accounts.get(item.id)) for item in customers], total, skip, limit),
        msg="ok",
    )


@router.post("/", response_model=RespVo)
async def create_customer(data: CreateCustomerRequest, request: Request, db: AsyncSession = Depends(get_db)):
    from app.core.tenant_context import TenantContext

    tenant_id = TenantContext.get_tenant_id()
    customer_service = CustomerService(db)
    customer = await customer_service.create_customer(
        tenant_id=tenant_id,
        openid=data.openid,
        external_userid=data.external_userid,
        name=data.name,
        phone=data.phone,
        tags=data.tags,
    )
    await CustomerIdentityService(db).bind_customer_identities(
        customer_id=customer.id,
        phone=data.phone,
        openid=data.openid,
        external_userid=data.external_userid,
    )
    await record_customer_log(
        db,
        tenant_id,
        customer,
        "merchant_create_customer",
        request=request,
        detail={"message": "商家后台新增会员", "name": customer.name},
    )
    return success_response(data=serialize_customer(customer), msg="建成功")


@router.get("/tags", response_model=RespVo)
async def list_tags(db: AsyncSession = Depends(get_db)):
    tags = await CustomerService(db).list_tags()
    return success_response(data=tags, msg="ok")


@router.post("/merge", response_model=RespVo)
async def merge_customers(data: MergeCustomerRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = CustomerService(db)
    customer = await service.merge_customers(data.source_customer_id, data.target_customer_id)
    if not customer:
        return error_response(code=404, msg="会员不存在或不能合并")
    await record_customer_log(
        db,
        customer.tenant_id,
        customer,
        "merchant_merge_customer",
        request=request,
        detail={
            "message": "商家后台合并重复会员",
            "source_customer_id": str(data.source_customer_id),
            "target_customer_id": str(data.target_customer_id),
        },
    )
    source = await service.get_customer_source(customer.id)
    return success_response(data=serialize_customer(customer, source), msg="合并成功")


@router.put("/{customer_id}", response_model=RespVo)
async def update_customer(customer_id: int, data: UpdateCustomerRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = CustomerService(db)
    before = await service.get_customer_any_status(customer_id)
    customer = await service.update_customer(customer_id, **data.model_dump(exclude_unset=True))
    if not customer:
        return error_response(code=404, msg="会员不存在")

    if data.phone:
        await CustomerIdentityService(db).bind_customer_identities(customer_id=customer.id, phone=data.phone)

    await record_customer_log(
        db,
        customer.tenant_id,
        customer,
        "merchant_update_customer",
        request=request,
        detail={
            "message": "商家后台修改会员资料",
            "before": {
                "name": before.name if before else None,
                "phone": before.phone if before else None,
                "tags": before.tags if before else None,
            },
            "after": data.model_dump(exclude_unset=True),
        },
    )
    source = await service.get_customer_source(customer.id)
    return success_response(data=serialize_customer(customer, source), msg="更新成功")


@router.put("/{customer_id}/status", response_model=RespVo)
async def update_customer_status(
    customer_id: int,
    data: UpdateCustomerStatusRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = CustomerService(db)
    before = await service.get_customer_any_status(customer_id)
    customer = await service.set_customer_status(customer_id, data.status)
    if not customer:
        return error_response(code=404, msg="会员不存在")

    action = "merchant_restore_customer" if data.status == 1 and before and before.status != 1 else "merchant_change_customer_status"
    message = "商家后台恢复会员" if action == "merchant_restore_customer" else "商家后台修改会员状态"
    await record_customer_log(
        db,
        customer.tenant_id,
        customer,
        action,
        request=request,
        detail={
            "message": message,
            "before_status": before.status if before else None,
            "after_status": customer.status,
        },
    )
    source = await service.get_customer_source(customer.id)
    return success_response(data=serialize_customer(customer, source), msg="状态已更新")


@router.post("/{customer_id}/restore", response_model=RespVo)
async def restore_customer(customer_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    service = CustomerService(db)
    before = await service.get_customer_any_status(customer_id)
    customer = await service.set_customer_status(customer_id, 1)
    if not customer:
        return error_response(code=404, msg="会员不存在")
    await record_customer_log(
        db,
        customer.tenant_id,
        customer,
        "merchant_restore_customer",
        request=request,
        detail={
            "message": "商家后台恢复会员",
            "before_status": before.status if before else None,
            "after_status": customer.status,
        },
    )
    source = await service.get_customer_source(customer.id)
    return success_response(data=serialize_customer(customer, source), msg="恢复成功")


@router.delete("/{customer_id}", response_model=RespVo)
async def delete_customer(customer_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    customer = await CustomerService(db).soft_delete_customer(customer_id)
    if not customer:
        return error_response(code=404, msg="会员不存在")
    await record_customer_log(
        db,
        customer.tenant_id,
        customer,
        "merchant_disable_customer",
        request=request,
        detail={"message": "商家后台停用会员", "after_status": customer.status},
    )
    return success_response(msg="停用成功")


@router.get("/{customer_id}", response_model=RespVo)
async def get_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    service = CustomerService(db)
    customer = await service.get_customer_any_status(customer_id)
    if not customer:
        return error_response(code=404, msg="会员不存在")

    data = serialize_customer(customer, await service.get_customer_source(customer_id))
    identities = await service.list_customer_identities(customer_id)
    data["identities"] = [serialize_identity(item) for item in identities]
    data["operation_logs"] = await build_customer_logs(db, customer, skip=0, limit=20)
    if is_disabled_customer(customer):
        data["status_text"] = "已停用"
        data["disabled_at"] = customer.deleted_at or customer.updated_at
        data["disabled_reason"] = "该会员已被商家停用，小程序扫码入会会被拦截。"
    return success_response(data=data, msg="ok")


@router.get("/{customer_id}/operation-logs", response_model=RespVo)
async def get_customer_operation_logs(
    customer_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    service = CustomerService(db)
    customer = await service.get_customer_any_status(customer_id)
    if not customer:
        return error_response(code=404, msg="会员不存在")

    data = await build_customer_logs(db, customer, skip=skip, limit=limit)
    return success_response(data=data, msg="ok")


@router.get("/{customer_id}/identities", response_model=RespVo)
async def get_customer_identities(customer_id: int, db: AsyncSession = Depends(get_db)):
    service = CustomerService(db)
    customer = await service.get_customer_any_status(customer_id)
    if not customer:
        return error_response(code=404, msg="会员不存在")
    identities = await service.list_customer_identities(customer_id)
    return success_response(data=[serialize_identity(item) for item in identities], msg="ok")


@router.get("/{customer_id}/timeline", response_model=RespVo)
async def get_customer_timeline(customer_id: int, db: AsyncSession = Depends(get_db)):
    service = CustomerService(db)
    # P0 安全修复：跟其它 /customers/{id}/* 接口一样，先确认这个客户属于当前商家，
    # 否则随便猜一个客户 ID 就能拉到别的商家客户的完整消费记录。
    customer = await service.get_customer_any_status(customer_id)
    if not customer:
        return error_response(code=404, msg="会员不存在")
    timeline = await service.get_customer_timeline(customer_id)
    return success_response(data=timeline, msg="ok")
