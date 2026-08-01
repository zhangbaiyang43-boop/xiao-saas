from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.models.queue_ticket import QueueTicket
from app.schemas.queue import QueueCallNext, QueueTicketCreate
from app.services.queue_service import QueueCallBlocked, QueueService, print_queue_test_ticket, serialize_queue_ticket
from app.services.kuaimai_service import KuaimaiPrintError

router = APIRouter(prefix="/api/queue", tags=["queue"])


def ok(data=None, message: str = "success"):
    return {"success": True, "message": message, "data": data}


def fail(message: str = "error", data=None):
    return {"success": False, "message": message, "data": data}


def _tenant_id(value) -> str:
    return str(value).strip()


def _merchant_tenant(request: Request) -> str | None:
    token_tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if token_tenant_id and token_type == "merchant":
        return str(token_tenant_id)
    return None


async def _log_queue_ticket_not_found(
    db: AsyncSession,
    request: Request,
    ticket_id: int,
    operation: str,
    effective_tenant_id: str | None,
    request_tenant_id: str | None,
) -> None:
    result = await db.execute(select(QueueTicket).options(defer(QueueTicket.query_token)).where(QueueTicket.id == ticket_id))
    existing = result.scalar_one_or_none()
    logger.warning(
        "queue ticket operation target not found: "
        f"operation={operation} ticket_id={ticket_id} "
        f"effective_tenant_id={effective_tenant_id} request_tenant_id={request_tenant_id} "
        f"state_tenant_id={getattr(request.state, 'tenant_id', None)} "
        f"token_type={getattr(request.state, 'token_type', None)} "
        f"existing_tenant_id={getattr(existing, 'tenant_id', None)} "
        f"existing_queue_no={getattr(existing, 'queue_no', None)} "
        f"existing_status={getattr(existing, 'status', None)}"
    )


@router.post("/tickets")
async def create_queue_ticket(body: QueueTicketCreate, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = _merchant_tenant(request) or _tenant_id(body.tenant_id)
    if not tenant_id:
        return fail("missing tenant_id")
    service = QueueService(db)
    try:
        ticket, ahead_count = await service.create_ticket(
            tenant_id=tenant_id,
            party_size=body.party_size,
            phone=body.phone,
            note=body.note,
        )
        data = serialize_queue_ticket(ticket, ahead_count=ahead_count)
        # TODO: future - show coupon entry after queue ticket created
        return ok(data)
    except Exception as exc:
        return fail(str(exc))


@router.get("/tickets")
async def list_queue_tickets(
    tenant_id: int | str,
    request: Request,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    # 这个接口带完整手机号，只给商家后台（QueueManage.vue）用，不能像 /status 那样兼容公开
    # 排队屏——之前没登录也能靠 tenant_id 查询参数拉到任意商家的排队顾客手机号列表。
    effective_tenant_id = _merchant_tenant(request)
    if not effective_tenant_id:
        return fail("merchant login required")
    service = QueueService(db)
    tickets = await service.list_tickets(effective_tenant_id, status=status)
    return ok([serialize_queue_ticket(ticket) for ticket in tickets])


@router.post("/call-next")
async def call_next_queue_ticket(
    body: QueueCallNext,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = _merchant_tenant(request)
    if not tenant_id:
        return fail("merchant login required")
    service = QueueService(db)
    try:
        ticket = await service.call_next(tenant_id, body.queue_type)
    except QueueCallBlocked as exc:
        return fail(f"请先入座或过号当前叫号 {exc.active_ticket.queue_no}")
    if not ticket:
        return fail("no waiting queue ticket")
    return ok(serialize_queue_ticket(ticket))


@router.post("/tickets/{ticket_id}/seat")
async def seat_queue_ticket(
    ticket_id: int,
    request: Request,
    tenant_id: int | str,
    db: AsyncSession = Depends(get_db),
):
    effective_tenant_id = _merchant_tenant(request)
    if not effective_tenant_id:
        return fail("merchant login required")
    ticket = await QueueService(db).mark_status(effective_tenant_id, ticket_id, "seated")
    if not ticket:
        await _log_queue_ticket_not_found(db, request, ticket_id, "seat", effective_tenant_id, _tenant_id(tenant_id))
        return fail("queue ticket not found")
    return ok(serialize_queue_ticket(ticket))


@router.post("/tickets/{ticket_id}/skip")
async def skip_queue_ticket(
    ticket_id: int,
    request: Request,
    tenant_id: int | str,
    db: AsyncSession = Depends(get_db),
):
    effective_tenant_id = _merchant_tenant(request)
    if not effective_tenant_id:
        return fail("merchant login required")
    ticket = await QueueService(db).mark_status(effective_tenant_id, ticket_id, "skipped")
    if not ticket:
        await _log_queue_ticket_not_found(db, request, ticket_id, "skip", effective_tenant_id, _tenant_id(tenant_id))
        return fail("queue ticket not found")
    return ok(serialize_queue_ticket(ticket))



@router.post("/print-test")
async def print_test_queue_ticket(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = _merchant_tenant(request)
    logger.warning("[PRINT_TEST_ROUTE_ENTER] tenant_id=%s", tenant_id)
    
    if not tenant_id:
        return fail("merchant login required")
    
    try:
        logger.warning("[PRINT_TEST_CALL_SERVICE] about to call print_queue_test_ticket")
        result = await print_queue_test_ticket(db, tenant_id)
        logger.warning("[PRINT_TEST_SERVICE_RESULT] result=%r", result)
        
        if isinstance(result, dict) and result.get("success"):
            logger.warning("[PRINT_TEST_RESPONSE] success=True task_id=%s", result.get("provider_task_id"))
            return {
                "success": True,
                "message": "测试打印任务已提交",
                "provider": result.get("provider", "kuaimai"),
                "provider_task_id": result.get("provider_task_id"),
            }
        
        if isinstance(result, dict) and not result.get("success"):
            error_msg = result.get("error") or "测试打印失败"
            logger.warning("[PRINT_TEST_RESPONSE] success=False error=%s", error_msg)
            raise HTTPException(
                status_code=502,
                detail={
                    "success": False,
                    "code": "KUAIMAI_REQUEST_FAILED",
                    "message": "快麦测试打印失败",
                    "detail": error_msg,
                },
            )
        
        if not result:
            logger.warning("[PRINT_TEST_RESPONSE] result is None/False")
            raise HTTPException(
                status_code=502,
                detail={
                    "success": False,
                    "code": "KUAIMAI_REQUEST_FAILED",
                    "message": "快麦测试打印失败",
                    "detail": "打印返回结果为空",
                },
            )
        
        logger.warning("[PRINT_TEST_RESPONSE] fallback success")
        return {
            "success": True,
            "message": "测试打印任务已提交",
            "provider": "kuaimai",
            "provider_task_id": None,
        }
    
    except KuaimaiPrintError as exc:
        logger.exception("[PRINT_TEST_RESPONSE] KuaimaiPrintError code=%s status=%s error=%s", exc.code, exc.status_code, str(exc))
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "success": False,
                "code": exc.code,
                "message": "快麦测试打印失败",
                "detail": str(exc),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[PRINT_TEST_RESPONSE] Exception type=%s error=%s", type(exc).__name__, str(exc))
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "code": "INTERNAL_ERROR",
                "message": "测试打印失败",
                "detail": str(exc),
            },
        )

@router.get("/status")
async def get_queue_status(
    request: Request,
    tenant_id: int | str | None = None,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    if token:
        data = await service.get_status_by_token(token)
        if not data:
            return fail("\u6392\u961f\u67e5\u8be2\u5df2\u5931\u6548")
        return ok(data)

    if tenant_id is None:
        return fail("missing tenant_id")
    effective_tenant_id = _merchant_tenant(request) or _tenant_id(tenant_id)
    data = await service.get_status(effective_tenant_id)
    return ok(data)


@router.post("/dev-seed")
async def seed_queue_demo_data(
    tenant_id: int | str = 1,
    db: AsyncSession = Depends(get_db),
):
    if not settings.DEBUG:
        return fail("dev seed only available in debug mode")
    data = await QueueService(db).seed_demo_data(_tenant_id(tenant_id))
    return ok(data)





