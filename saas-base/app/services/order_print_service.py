import asyncio
import json
from collections.abc import Coroutine
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.logger import logger
from app.core.tenant_context import TenantContext
from app.models.order import Order

PRINT_META_MARKER = "\n__PRINT_META__="
MAX_PRINT_RETRY_ATTEMPTS = 3
PRINT_RETRY_COOLDOWN_SECONDS = 30
PRINT_RECONCILE_GRACE_SECONDS = 15
PRINT_RECONCILE_BATCH_LIMIT = 8

_KUAIMAI_UNKNOWN_CODES = frozenset({
    "KUAIMAI_TIMEOUT",
    "KUAIMAI_UNKNOWN_ERROR",
    "KUAIMAI_INVALID_RESPONSE",
})
_AUTO_RECONCILE_STATUSES = frozenset({"pending", "preparing", "done"})
_FULFILLABLE_STATUSES = frozenset({"pending", "preparing", "done", "settled"})


def can_reprint_order(order: Order, print_type: str = "kitchen") -> tuple[bool, str | None]:
    status = getattr(order, "status", None)
    payment_mode = getattr(order, "payment_mode", "prepay") or "prepay"
    payment_status = getattr(order, "payment_status", None)
    if status in ("cancelled", "rejected"):
        return False, "order cancelled"
    if print_type == "receipt":
        return (payment_status == "paid", None if payment_status == "paid" else "order not paid")
    if print_type == "kitchen":
        if payment_mode == "prepay":
            return (payment_status == "paid", None if payment_status == "paid" else "order not paid")
        if payment_mode in ("postpay", "table_account"):
            return True, None
    return False, "unsupported print type"


def evaluate_print_eligibility(
    order: Order,
    *,
    defer_kitchen_print: bool = False,
    manual: bool = False,
) -> dict:
    """Decide whether an order may be printed (auto or manual)."""
    status = getattr(order, "status", None)
    payment_mode = getattr(order, "payment_mode", "prepay") or "prepay"
    payment_status = getattr(order, "payment_status", None)
    db_print_status = str(getattr(order, "print_status", "") or "").upper()
    meta = _get_print_meta(order)

    if status in ("cancelled", "rejected"):
        return {"code": "NOT_PRINTABLE", "reason": "order cancelled or rejected"}

    if not manual and (db_print_status == "SUCCESS" or meta.get("status") == "printed"):
        return {"code": "ALREADY_SUCCESS", "reason": "already printed successfully"}

    if defer_kitchen_print and not manual:
        return {"code": "WAITING_PICKUP_NO", "reason": "waiting for pickup number before kitchen print"}

    if payment_mode == "prepay" and payment_status != "paid":
        return {"code": "NOT_YET_PAYABLE", "reason": "prepay order not paid"}

    if status == "pending_payment":
        return {"code": "NOT_YET_PAYABLE", "reason": "order still pending payment"}

    # postpay / table_account unpaid OR paid → eligible in fulfillable statuses
    if status in _FULFILLABLE_STATUSES:
        return {"code": "ELIGIBLE", "reason": "eligible for print"}

    return {"code": "NOT_PRINTABLE", "reason": f"status {status!r} is not printable"}


def build_staff_print_summary(order: Order, *, defer_kitchen_print: bool = False) -> dict:
    """Safe print fields for staff workbench DTOs — no raw meta / secrets / traces."""
    meta = _get_print_meta(order)
    db_status = str(getattr(order, "print_status", "") or "").upper()
    meta_status = meta.get("status") if meta else None

    print_status: str | None
    if db_status in ("SUCCESS", "FAILED", "UNKNOWN", "PENDING"):
        print_status = db_status
    elif meta_status == "printed":
        print_status = "SUCCESS"
    elif meta_status == "failed":
        print_status = "FAILED"
    elif meta_status == "unknown":
        print_status = "UNKNOWN"
    elif meta_status in ("printing", "not_started"):
        print_status = "PENDING"
    else:
        print_status = None

    waiting = bool(
        defer_kitchen_print
        and print_status not in ("SUCCESS",)
        and meta_status != "printed"
    )

    print_issue = None
    if print_status == "FAILED" or meta_status == "failed":
        print_issue = "failed"
    elif print_status == "UNKNOWN" or meta_status == "unknown":
        print_issue = "unknown"
    elif waiting:
        print_issue = "waiting_pickup"

    if print_issue == "waiting_pickup":
        label = "等待桌牌后打印"
    elif print_status == "SUCCESS":
        label = "已提交打印"
    elif print_status == "FAILED":
        label = "打印失败"
    elif print_status == "UNKNOWN":
        label = "打印状态未知"
    else:
        label = ""

    can_reprint, _ = can_reprint_order(order, print_type="kitchen")
    return {
        "print_status": print_status,
        "print_status_label": label,
        "print_attempts": int(meta.get("attempts") or 0) if meta else 0,
        "print_issue": print_issue,
        "can_reprint": bool(can_reprint),
    }


def _split_merchant_note_and_print_meta(raw_note: str | None) -> tuple[str | None, dict]:
    raw = raw_note or ""
    if PRINT_META_MARKER not in raw:
        return (raw.strip() or None), {}
    note, meta_raw = raw.rsplit(PRINT_META_MARKER, 1)
    try:
        meta = json.loads(meta_raw) if meta_raw.strip() else {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    return (note.strip() or None), meta


def _compose_merchant_note_with_print_meta(note: str | None, meta: dict | None) -> str | None:
    clean_note = (note or "").strip()
    if not meta:
        return clean_note or None
    meta = dict(meta)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    return f"{clean_note}{PRINT_META_MARKER}{json.dumps(meta, ensure_ascii=False, separators=(',', ':'))}"


def _get_print_meta(order: Order) -> dict:
    _, meta = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    return meta


def _set_print_meta(order: Order, meta: dict, note: str | None = None) -> dict:
    current_note, _ = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    order.merchant_note = _compose_merchant_note_with_print_meta(current_note if note is None else note, meta)
    return meta


def _db_print_status_to_meta_status(order: Order) -> str | None:
    status = str(getattr(order, "print_status", "") or "").upper()
    if status == "SUCCESS":
        return "printed"
    if status == "FAILED":
        return "failed"
    if status == "UNKNOWN":
        return "unknown"
    return None


def _mark_order_print_state(
    order: Order, status: str, printed_at: datetime | None = None
) -> None:
    if hasattr(order, "print_status"):
        order.print_status = status
    if status == "SUCCESS" and hasattr(order, "printed_at"):
        order.printed_at = printed_at or datetime.utcnow()


def _serialize_print_meta(order: Order) -> dict:
    note, meta = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    status = _db_print_status_to_meta_status(order)
    if not status:
        status = meta.get("status") if meta else None
    if not status and getattr(order, "payment_status", None) == "paid":
        status = "not_started"
    return {
        "merchant_note": note,
        "print_status": status,
        "print_attempts": int(meta.get("attempts") or 0) if meta else 0,
        "print_error_code": meta.get("last_error_code") if meta else None,
        "print_error": meta.get("last_error") if meta else None,
        "print_provider_task_id": meta.get("provider_task_id") if meta else None,
        "print_manual_reprint": bool(meta.get("manual_reprint")) if meta else False,
        "print_manual_reprint_by": meta.get("manual_reprint_by") if meta else None,
        "print_manual_reprint_at": meta.get("manual_reprint_at") if meta else None,
        "print_last_reason": meta.get("last_reason") if meta else None,
    }


class PrintResultUnknownError(RuntimeError):
    """飞鹅云请求超时/网络异常导致没拿到响应——不知道这次到底有没有打印成功，跟"服务端
    明确说打印失败"是两码事，调用方必须分开处理（不能自动重试，见 print_order 的说明）。"""


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _eligible_at_for_reconcile(order: Order) -> datetime | None:
    payment_mode = getattr(order, "payment_mode", "prepay") or "prepay"
    if payment_mode == "prepay":
        return _parse_dt(getattr(order, "payment_time", None)) or _parse_dt(getattr(order, "created_at", None))
    return _parse_dt(getattr(order, "created_at", None))


def _is_unknown_print_exception(exc: BaseException) -> bool:
    if isinstance(exc, PrintResultUnknownError):
        return True
    code = str(getattr(exc, "code", None) or "").strip()
    if code in _KUAIMAI_UNKNOWN_CODES:
        return True
    message = str(exc or "").strip()
    if message in _KUAIMAI_UNKNOWN_CODES:
        return True
    return False


async def _print_paid_order_ticket(
    order: Order,
    db: AsyncSession,
    *,
    manual: bool = False,
    reason: str = "auto",
    operator: str | None = None,
    operator_role: str | None = None,
) -> dict:
    """Print an order ticket and persist recoverable print state in existing order metadata."""
    if not order:
        return {"success": False, "skipped": True, "code": "ORDER_NOT_FOUND"}

    locked_result = await db.execute(select(Order).where(Order.id == order.id).with_for_update())
    locked_order = locked_result.scalar_one_or_none()
    if locked_order:
        order = locked_order

    defer_kitchen_print = False
    if not manual:
        from app.services.pickup_no_service import load_pickup_settings, should_defer_kitchen_print

        pickup_settings = await load_pickup_settings(db, str(order.tenant_id))
        defer_kitchen_print = should_defer_kitchen_print(order, pickup_settings)

    eligibility = evaluate_print_eligibility(
        order,
        defer_kitchen_print=defer_kitchen_print,
        manual=manual,
    )
    code = eligibility.get("code")
    if code == "ALREADY_SUCCESS":
        meta = _get_print_meta(order)
        logger.warning(
            "[PRINT_SKIPPED_ALREADY_SUCCESS] order_id=%s print_status=%s status=%s attempts=%s provider_task_id=%s",
            order.id,
            str(getattr(order, "print_status", "") or ""),
            meta.get("status"),
            meta.get("attempts", 0),
            meta.get("provider_task_id"),
        )
        logger.warning(
            "[PRINT_IDEMPOTENT_HIT] order_id=%s reason=%s manual=%s",
            order.id,
            reason,
            manual,
        )
        return {"success": True, "skipped": True, "status": "printed"}
    if code == "WAITING_PICKUP_NO":
        logger.warning(
            "[PRINT_DEFERRED_WAITING_PICKUP_NO] order_id=%s reason=%s",
            order.id,
            reason,
        )
        return {"success": False, "skipped": True, "code": "WAITING_PICKUP_NO"}
    if code == "NOT_YET_PAYABLE":
        return {"success": False, "skipped": True, "code": "NOT_YET_PAYABLE"}
    if code != "ELIGIBLE":
        return {"success": False, "skipped": True, "code": code or "NOT_PRINTABLE"}

    meta = _get_print_meta(order)
    attempts = int(meta.get("attempts") or 0)
    if not manual and attempts >= MAX_PRINT_RETRY_ATTEMPTS:
        logger.warning(
            "[PRINT_ORDER_RETRY_LIMIT] order_id=%s attempts=%s last_error_code=%s",
            order.id,
            attempts,
            meta.get("last_error_code"),
        )
        return {"success": False, "skipped": True, "code": "PRINT_RETRY_LIMIT"}

    if attempts == 0 and not manual:
        logger.warning(
            "[PRINT_FIRST_EXECUTION] order_id=%s attempts=%s reason=%s manual=%s",
            order.id,
            attempts + 1,
            reason,
            manual,
        )
    now_iso = datetime.now(timezone.utc).isoformat()
    meta.update({
        "status": "printing",
        "attempts": attempts + 1,
        "last_reason": reason,
        "last_attempt_at": now_iso,
        "manual_reprint": bool(meta.get("manual_reprint")) or manual,
    })
    if manual:
        meta["manual_reprint_by"] = operator if operator else "owner"
        meta["manual_reprint_at"] = now_iso
        if operator_role:
            meta["manual_reprint_role"] = operator_role
    _mark_order_print_state(order, "PENDING")
    _set_print_meta(order, meta)
    await db.flush()

    try:
        from app.models.tenant import Tenant
        from app.models.tenant_config import TenantConfig
        from app.models.order import OrderItem
        from app.services.feieyun_service import build_order_ticket, print_order

        tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
        tenant_obj = tenant_result.scalar_one_or_none()
        config_result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == str(order.tenant_id)))
        config_obj = config_result.scalar_one_or_none()
        business_info: dict[str, Any] = (config_obj.business_info or {}) if config_obj else {}
        provider = business_info.get("printer_provider") or "feieyun"
        provider_task_id = None

        if provider == "kuaimai":
            from app.services.kuaimai_service import (
                KUAIMAI_ORDER_TEMPLATE_ID,
                build_order_template_render_data,
                print_template_order,
                validate_order_template_render_data,
            )

            kuaimai = business_info.get("kuaimai_printer") or {}
            configured_template_id = str(kuaimai.get("order_template_id") or "").strip()
            kuaimai_template_id = configured_template_id or KUAIMAI_ORDER_TEMPLATE_ID
            logger.warning(
                "[ORDER_PRINT_TEMPLATE_ID_CHECK] order_id=%s tenant_id=%s configured_order_template_id=%s effective_template_id=%s default_order_template_id=%s manual=%s reason=%s",
                order.id,
                order.tenant_id,
                configured_template_id or "",
                kuaimai_template_id,
                KUAIMAI_ORDER_TEMPLATE_ID,
                manual,
                reason,
            )

            items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            order_items = list(items_result.scalars().all())
            render_data = build_order_template_render_data(
                order,
                order_items,
                shop_name=getattr(tenant_obj, "name", "") if tenant_obj else "",
            )
            item_names = [item.get("goods_name") for item in render_data.get("items", [])]
            logger.warning(
                "[PRINT_ORDER_PAYLOAD] event=print_order_payload order_id=%s order_no=%s merchant_id=%s printer_id=%s template_id=%s items_count=%s item_names=%s total_amount=%s pay_amount=%s data_sources=%s manual=%s reason=%s",
                order.id,
                render_data.get("order_no"),
                order.tenant_id,
                kuaimai.get("sn") or "",
                kuaimai_template_id,
                len(render_data.get("items", [])),
                item_names,
                render_data.get("total_amount"),
                render_data.get("pay_amount"),
                ["items", "goods"],
                manual,
                reason,
            )

            valid, error_code = validate_order_template_render_data(render_data, order)
            if not valid:
                logger.warning(
                    "[PRINT_ORDER_VALIDATE_FAILED] order_id=%s order_no=%s merchant_id=%s printer_id=%s template_id=%s items_type=%s items_count=%s error_code=%s",
                    order.id,
                    render_data.get("order_no"),
                    order.tenant_id,
                    kuaimai.get("sn") or "",
                    kuaimai_template_id,
                    type(render_data.get("items")).__name__,
                    len(render_data.get("items", [])) if isinstance(render_data.get("items"), list) else "n/a",
                    error_code,
                )
                raise RuntimeError(error_code)

            result = await print_template_order(
                kuaimai.get("app_id") or "",
                kuaimai.get("app_secret") or "",
                kuaimai.get("sn") or "",
                kuaimai_template_id,
                render_data,
            )
            if not result or result.get("success") is not True:
                err = (
                    (result.get("code") or result.get("error") or "PRINT_PROVIDER_FAILED")
                    if result
                    else "PRINT_PROVIDER_FAILED"
                )
                if str(err) in _KUAIMAI_UNKNOWN_CODES:
                    raise PrintResultUnknownError(str(err))
                raise RuntimeError(str(err))
            provider_task_id = result.get("provider_task_id")
        elif tenant_obj and tenant_obj.feieyun_sn and tenant_obj.feieyun_key:
            items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            order_items = list(items_result.scalars().all())
            ticket = build_order_ticket(order, order_items)
            feie_result = await print_order(tenant_obj.feieyun_sn, tenant_obj.feieyun_key, ticket)
            if feie_result == "unknown":
                raise PrintResultUnknownError("FEIEYUN_PRINT_RESULT_UNKNOWN")
            if feie_result != "success":
                raise RuntimeError("FEIEYUN_PRINT_FAILED")
        else:
            raise RuntimeError("PRINTER_CONFIG_INCOMPLETE")

        meta.update({
            "status": "printed",
            "last_error_code": None,
            "last_error": None,
            "provider_task_id": provider_task_id,
            "printed_at": datetime.now(timezone.utc).isoformat(),
            "manual_reprint": bool(meta.get("manual_reprint")) or manual,
        })
        _mark_order_print_state(order, "SUCCESS")
        _set_print_meta(order, meta)
        logger.warning(
            "[PRINT_ORDER_SUCCESS] order_id=%s attempts=%s provider_task_id=%s manual=%s reason=%s",
            order.id,
            meta.get("attempts"),
            provider_task_id,
            manual,
            reason,
        )
        return {"success": True, "status": "printed", "attempts": meta.get("attempts"), "provider_task_id": provider_task_id}
    except Exception as exc:
        # 结果不明（网络超时/异常，没拿到打印服务商的响应）和明确失败（服务商回了响应说没
        # 打印成功）分开处理："失败"允许后续自动重试（merchant_list_recovery 那条路），
        # "未知"绝不能自动重试——如果这次其实已经打印成功了，自动重试会造成重复出票，
        # 必须交给能实际看到打印机的人来判断要不要手动补打。
        is_unknown = _is_unknown_print_exception(exc)
        if is_unknown and not isinstance(exc, PrintResultUnknownError):
            # Normalize kuaimai unknown codes onto PrintResultUnknownError for callers/logs.
            exc = PrintResultUnknownError(getattr(exc, "code", None) or str(exc))
            is_unknown = True
        status_label = "unknown" if is_unknown else "failed"
        db_status = "UNKNOWN" if is_unknown else "FAILED"
        error_code = getattr(exc, "code", None) or str(exc) or type(exc).__name__
        meta.update({
            "status": status_label,
            "last_error_code": error_code,
            "last_error": str(exc),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "manual_reprint": bool(meta.get("manual_reprint")) or manual,
        })
        _mark_order_print_state(order, db_status)
        _set_print_meta(order, meta)
        logger.warning(
            "[PRINT_ORDER_%s_RECOVERABLE] order_id=%s attempts=%s error_code=%s manual=%s reason=%s",
            db_status,
            order.id,
            meta.get("attempts"),
            error_code,
            manual,
            reason,
        )
        return {"success": False, "status": status_label, "attempts": meta.get("attempts"), "code": error_code}


async def reconcile_print_orders(
    db: AsyncSession,
    orders,
    *,
    trigger: str = "reconcile",
    pickup_settings: dict | None = None,
) -> int:
    """Best-effort print recovery for a bounded batch of orders. Returns print call count."""
    from app.services.pickup_no_service import load_pickup_settings, should_defer_kitchen_print

    if not orders:
        return 0

    batch = list(orders)[:PRINT_RECONCILE_BATCH_LIMIT]
    now = datetime.now(timezone.utc)
    settings_by_tenant: dict[str, dict] = {}
    attempted = 0

    for order in batch:
        if getattr(order, "status", None) not in _AUTO_RECONCILE_STATUSES:
            continue

        tenant_id = str(getattr(order, "tenant_id", "") or "")
        if pickup_settings is not None:
            settings = pickup_settings
        else:
            if tenant_id not in settings_by_tenant:
                settings_by_tenant[tenant_id] = await load_pickup_settings(db, tenant_id)
            settings = settings_by_tenant[tenant_id]

        defer = should_defer_kitchen_print(order, settings)
        eligibility = evaluate_print_eligibility(order, defer_kitchen_print=defer, manual=False)
        if eligibility.get("code") in (
            "ALREADY_SUCCESS",
            "WAITING_PICKUP_NO",
            "NOT_YET_PAYABLE",
            "NOT_PRINTABLE",
        ):
            continue

        meta = _get_print_meta(order)
        db_print_status = str(getattr(order, "print_status", "") or "").upper()
        meta_status = meta.get("status")

        # Result-unknown must never auto-retry (risk of duplicate tickets).
        if db_print_status == "UNKNOWN" or meta_status == "unknown":
            continue

        attempts = int(meta.get("attempts") or 0)
        is_failed = db_print_status == "FAILED" or meta_status == "failed"

        if is_failed:
            if attempts >= MAX_PRINT_RETRY_ATTEMPTS:
                continue
            last_at = _parse_dt(meta.get("last_attempt_at")) or _parse_dt(meta.get("failed_at"))
            if last_at and (now - last_at).total_seconds() < PRINT_RETRY_COOLDOWN_SECONDS:
                continue
            await _print_paid_order_ticket(order, db, reason=trigger)
            attempted += 1
            continue

        # Never successfully printed: first attempt after grace window.
        if attempts == 0 and not is_failed:
            eligible_at = _eligible_at_for_reconcile(order)
            if eligible_at and (now - eligible_at).total_seconds() < PRINT_RECONCILE_GRACE_SECONDS:
                continue
            await _print_paid_order_ticket(order, db, reason=trigger)
            attempted += 1

    return attempted


# asyncio.create_task() 返回的 Task 如果没有任何地方存着强引用，理论上可能在下一次
# 事件循环切换时被垃圾回收掉、任务莫名其妙就没跑完——这是 asyncio 官方文档专门强调过的
# 坑（"Save a reference to the result of this function"）。对于打印这种失败了也不会有人
# 立刻发现的后台任务，这个坑一旦踩中会很难查，所以这里维护一个模块级的引用集合，任务
# 跑完自动从集合里摘掉。
_background_print_tasks: set[asyncio.Task[None]] = set()


def _spawn_background_print_task(coro: Coroutine[Any, Any, Any]) -> None:
    task = asyncio.create_task(coro)
    _background_print_tasks.add(task)
    task.add_done_callback(_background_print_tasks.discard)


async def _print_paid_order_ticket_background(order_id: int, tenant_id: str, *, reason: str) -> None:
    """给顾客下单请求用的"不等打印机"版本。第三方云打印 API（飞鹅云/快麦）慢一点，
    顾客提交订单这个动作就跟着慢——打印本来就是"尽力而为、失败可恢复"的旁路副作用
    （见 _print_paid_order_ticket 里已有的说明和失败重试机制），没道理让它卡在顾客
    的请求-响应周期里。

    必须用独立的 DB session，不能复用调用方传进来的那个：调用方的请求早就返回了，
    它的 session 这时候可能已经关闭；而且这个函数是在调用方 commit 之后才被调度的
    （见 create_order 里的调用位置），这里重新按 order_id 查一次，保证读到的是已经
    落库的最新状态，不会因为事务可见性问题误判成"订单还不存在/还没付款"。

    session 工厂放函数体内 import（而不是模块顶部）：这个模块的打印失败恢复测试
    （test_print_failure_recovery_contracts.py）用一个手搭的 sys.modules 假环境加载
    这个文件，只桩了 app.core.database.get_db，模块顶部多 import 一个新符号会让那些
    测试在 import 这一步就直接炸掉——跟文件里其它服务依赖（Tenant/TenantConfig 等）
    延迟到函数体内 import 是同一个理由，不是我随手加的风格不一致。
    """
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as bg_db:
        try:
            TenantContext.set_tenant_id(tenant_id)
            order_result = await bg_db.execute(
                select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
            )
            order = order_result.scalar_one_or_none()
            if not order:
                return
            await _print_paid_order_ticket(order, bg_db, reason=reason)
            await bg_db.commit()
        except Exception as exc:
            logger.warning(
                "[PRINT_BACKGROUND_TASK_FAILED] order_id=%s reason=%s error=%s",
                order_id, reason, exc,
            )
