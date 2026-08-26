import base64
import hashlib
import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict

logger = logging.getLogger(__name__)

KUAIMAI_API_BASE = "https://cloud.kuaimai.com"
KUAIMAI_ESC_WRITE_PATH = "/api/cloud/print/escWrite"
KUAIMAI_ESC_TEMPLATE_PRINT_PATH = "/api/cloud/print/escTemplatePrint"
KUAIMAI_ORDER_TEMPLATE_ID = "1634998374"


class KuaimaiPrintError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "KUAIMAI_REQUEST_FAILED",
        status_code: int = 502,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _mask_string(value: str, keep_length: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep_length:
        return "*" * len(value)
    return value[:keep_length] + "*" * (len(value) - keep_length)


def _format_money(value: Any) -> str:
    try:
        amount = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _safe_text(value: Any) -> str:
    if value in (None, "", "无", "null", "undefined"):
        return ""
    return str(value).strip()


def _payment_method_text(value: Any) -> str:
    raw = _safe_text(value).lower()
    mapping = {
        "wxpay": "微信支付",
        "wechat": "微信支付",
        "wechat_pay": "微信支付",
        "alipay": "支付宝",
        "cash": "现金",
        "balance": "余额支付",
        "offline": "线下支付",
        "mock": "模拟支付",
        "微信支付": "微信支付",
        "余额支付": "余额支付",
        "支付宝": "支付宝",
        "现金": "现金",
        "线下支付": "线下支付",
        "模拟支付": "模拟支付",
        "unknown": "其他支付",
    }
    return mapping.get(raw, "其他支付")


def _order_time_text(order) -> str:
    created_at = getattr(order, "created_at", None)
    if hasattr(created_at, "strftime"):
        return created_at.strftime("%Y-%m-%d %H:%M")
    return _safe_text(created_at)


def _item_option_text(item) -> str:
    parts = []
    for attr in ("sku_text", "option_text", "addons"):
        text = _safe_text(getattr(item, attr, ""))
        if text:
            parts.append(text)
    return " / ".join(parts)


def _build_print_item_row(item) -> dict[str, Any]:
    goods_name = _safe_text(getattr(item, "name", ""))
    qty = int(getattr(item, "qty", 1) or 0)
    unit_price = Decimal(_format_money(getattr(item, "price", 0)))
    item_amount = unit_price * Decimal(qty)
    sku_text = _safe_text(getattr(item, "sku_text", ""))
    option_text = _safe_text(getattr(item, "option_text", ""))
    addons = _safe_text(getattr(item, "addons", ""))
    item_remark = _safe_text(getattr(item, "item_remark", ""))
    option_display = _item_option_text(item)
    display_parts = [goods_name]
    if option_display:
        display_parts.append(option_display)
    if item_remark:
        display_parts.append(f"备注：{item_remark}")

    return {
        "goods_name": goods_name,
        "display_name": "\n".join(display_parts),
        "quantity": qty,
        "quantity_text": f"×{qty}",
        "unit_price": _format_money(unit_price),
        "item_amount": _format_money(item_amount),
        "item_amount_text": _format_money(item_amount),
        "sku_text": sku_text,
        "option_text": option_text,
        "addons": addons,
    }



def _build_kuaimai_order_header_scope(render_data: dict[str, Any]) -> dict[str, Any]:
    header_fields = (
        "shop_name",
        "order_no",
        "order_no_short",
        "table_no",
        "pickup_no",
        "order_time",
        "pay_type",
        "pay_type_text",
        "total_amount",
        "discount_amount",
        "pay_amount",
        "remark",
        "order_type",
        "order_type_text",
        "parent_order_id",
    )
    header = {key: render_data.get(key, "") for key in header_fields}
    header["items"] = render_data.get("items", [])
    header["goods"] = render_data.get("goods", [])
    return header


def ensure_kuaimai_items_payload(render_data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(render_data or {})
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    payload["items"] = items
    payload["goods"] = [
        {
            "goods_name": item.get("goods_name", ""),
            "quantity_text": item.get("quantity_text", ""),
            "item_amount_text": item.get("item_amount_text", ""),
        }
        for item in items
        if isinstance(item, dict)
    ]
    pay_type_text = _payment_method_text(payload.get("pay_type_text") or payload.get("pay_type"))
    payload["pay_type"] = pay_type_text
    payload["pay_type_text"] = pay_type_text
    if "点餐订单" not in payload:
        payload["点餐订单"] = [_build_kuaimai_order_header_scope(payload)]
    return payload

def build_order_template_render_data(
    order,
    order_items: list,
    shop_name: str = "",
) -> dict:
    order_no = str(getattr(order, "id", "") or "")
    discount_amount = Decimal(_format_money(getattr(order, "discount_amount", 0) or 0))
    pay_amount = Decimal(_format_money(getattr(order, "total", 0) or 0))
    total_amount = pay_amount + discount_amount
    pay_type = _safe_text(getattr(order, "payment_method", ""))
    pay_type_text = _payment_method_text(pay_type)
    order_remark = _safe_text(getattr(order, "remark", ""))
    order_type = _safe_text(getattr(order, "order_type", ""))
    order_type_text = "加菜单" if order_type == "ADD_ON" else ("首单" if order_type == "INITIAL" else "")
    parent_order_id = _safe_text(getattr(order, "parent_order_id", ""))

    items = [_build_print_item_row(item) for item in order_items]
    items = [item for item in items if item["goods_name"] and item["quantity"] > 0]

    pickup_no = _safe_text(getattr(order, "pickup_no", ""))
    order_data = {
        "shop_name": _safe_text(shop_name),
        "order_no": order_no,
        "order_no_short": order_no[-4:] if order_no else "",
        "table_no": _safe_text(getattr(order, "table_no", "")),
        # 实体桌牌号：与固定桌号 table_no 分离，禁止互相覆盖
        "pickup_no": pickup_no,
        "order_time": _order_time_text(order),
        "pay_type": pay_type_text,
        "pay_type_text": pay_type_text,
        "total_amount": _format_money(total_amount),
        "discount_amount": _format_money(discount_amount),
        "pay_amount": _format_money(pay_amount),
        "remark": order_remark,
        "order_type": order_type,
        "order_type_text": order_type_text,
        "parent_order_id": parent_order_id,
        "items_count": len(items),
    }

    return {
        **order_data,
        "items": items,
    }


def _has_invalid_print_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"undefined", "null", "none"}


def validate_order_template_render_data(render_data: dict[str, Any], order=None) -> tuple[bool, str]:
    if not isinstance(render_data, dict):
        return False, "PRINT_ITEMS_PAYLOAD_INVALID"
    order_no = _safe_text(render_data.get("order_no"))
    table_no = _safe_text(render_data.get("table_no"))
    items = render_data.get("items")
    if not order_no:
        return False, "PRINT_ORDER_NO_EMPTY"
    if not table_no:
        return False, "PRINT_TABLE_NO_EMPTY"
    if not isinstance(items, list) or not items:
        return False, "PRINT_ITEMS_PAYLOAD_INVALID"
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return False, "PRINT_ITEMS_PAYLOAD_INVALID"
        for key in ("goods_name", "quantity", "quantity_text", "item_amount", "item_amount_text"):
            if key not in item or _has_invalid_print_text(item.get(key)) or not _safe_text(item.get(key)):
                return False, "PRINT_ITEMS_PAYLOAD_INVALID"
        try:
            if int(item.get("quantity") or 0) <= 0:
                return False, "PRINT_ITEMS_PAYLOAD_INVALID"
        except (TypeError, ValueError):
            return False, "PRINT_ITEMS_PAYLOAD_INVALID"
        _format_money(item.get("item_amount"))
    if not _safe_text(render_data.get("total_amount")):
        return False, "PRINT_TOTAL_AMOUNT_EMPTY"
    if not _safe_text(render_data.get("pay_amount")):
        return False, "PRINT_PAY_AMOUNT_EMPTY"
    return True, ""

def _current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_esc_bytes(content: str) -> bytes:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    body = text.encode("gb18030", errors="replace")
    return b"\x1b@" + body + b"\n\n\n"


def _sign_raw(params: dict[str, Any], app_secret: str) -> str:
    parts: list[str] = []
    for key in sorted(params.keys()):
        if key == "sign":
            continue
        value = params.get(key)
        if value is None or value == "":
            continue
        parts.append(f"{key}{value}")
    joined = "".join(parts)
    return f"{app_secret}{joined}{app_secret}"


def create_sign(params: dict[str, Any], app_secret: str) -> str:
    signing_params = {key: value for key, value in params.items() if key != "shareCode"}
    raw = _sign_raw(signing_params, app_secret)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()



def build_sign_variants(params: dict[str, Any], app_secret: str) -> dict[str, str]:
    without_share_code = {key: value for key, value in params.items() if key != "shareCode"}
    return {
        "compact": create_sign(params, app_secret),
        "compact_without_share_code": create_sign(without_share_code, app_secret),
    }

def build_print_payload(
    app_id: str,
    app_secret: str,
    sn: str,
    content: str,
    timestamp: str | None = None,
    copies: int = 1,
    share_code: str = "",
    device_key: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "appId": app_id,
        "timestamp": timestamp or _current_timestamp(),
        "sn": sn,
        "instructionsList": base64.b64encode(_build_esc_bytes(content)).decode("ascii"),
        "copies": max(1, min(int(copies or 1), 30)),
    }
    if share_code:
        payload["shareCode"] = share_code
    if device_key:
        payload["deviceKey"] = device_key
    payload["sign"] = create_sign(payload, app_secret)
    return payload


def build_template_print_payload(
    app_id: str,
    app_secret: str,
    sn: str,
    template_id: str,
    render_data: dict[str, Any],
    timestamp: str | None = None,
) -> dict[str, Any]:
    is_order_payload = "order_no" in (render_data or {}) or "items" in (render_data or {})
    if is_order_payload:
        render_data = ensure_kuaimai_items_payload(render_data)
        items_value = render_data.get("items")
        items_first_item = items_value[0] if isinstance(items_value, list) and items_value else {}
        items_preview = {
            "goods_name": items_first_item.get("goods_name", "") if isinstance(items_first_item, dict) else "",
            "quantity_text": items_first_item.get("quantity_text", "") if isinstance(items_first_item, dict) else "",
            "item_amount_text": items_first_item.get("item_amount_text", "") if isinstance(items_first_item, dict) else "",
        }
        goods_value = render_data.get("goods")
        goods_first_item = goods_value[0] if isinstance(goods_value, list) and goods_value else {}
        logger.warning(
            "[KUAIMAI_FINAL_PAYLOAD_CHECK] event=KUAIMAI_FINAL_PAYLOAD_CHECK order_no=%s template_id=%s payload_top_level_keys=%s items_type=%s items_count=%s items_first_item_keys=%s items_first_item_preview=%s goods_type=%s goods_count=%s goods_first_item=%s pay_type_text=%s",
            render_data.get("order_no"),
            template_id,
            list(render_data.keys()),
            type(items_value).__name__,
            len(items_value) if isinstance(items_value, list) else "n/a",
            list(items_first_item.keys()) if isinstance(items_first_item, dict) else [],
            items_preview,
            type(goods_value).__name__,
            len(goods_value) if isinstance(goods_value, list) else "n/a",
            goods_first_item,
            render_data.get("pay_type_text"),
        )
        valid, error_code = validate_order_template_render_data(render_data)
        if not valid:
            logger.warning(
                "[PRINT_ITEMS_PAYLOAD_INVALID] order_no=%s template_id=%s items_type=%s items_count=%s items_first_item_keys=%s payload_top_level_keys=%s error_code=%s",
                render_data.get("order_no"),
                template_id,
                type(items_value).__name__,
                len(items_value) if isinstance(items_value, list) else "n/a",
                list(items_first_item.keys()) if isinstance(items_first_item, dict) else [],
                list(render_data.keys()),
                error_code,
            )
            return {"success": False, "error": error_code, "code": "PRINT_ITEMS_PAYLOAD_INVALID"}

    render_data_json = json.dumps(
        render_data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    )

    payload: dict[str, Any] = {
        "appId": app_id,
        "timestamp": timestamp or _current_timestamp(),
        "sn": sn,
        "templateId": str(template_id),
        "renderData": render_data_json,
    }
    payload["sign"] = create_sign(payload, app_secret)
    return payload

def _extract_task_id(body: Dict[str, Any]) -> str | None:
    data = body.get("data")
    if isinstance(data, dict):
        for key in ("taskId", "printId", "jobId", "id"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
    for key in ("taskId", "printId", "jobId", "id"):
        value = body.get(key)
        if value not in (None, ""):
            return str(value)
    if isinstance(data, str) and data.strip():
        return data.strip()
    return None


def _is_successful_business_response(body: Dict[str, Any]) -> bool:
    if body.get("status") is True or body.get("success") is True:
        return True

    code = body.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)

    return code in {0, 200, 2000}


def _parse_kuaimai_response(resp) -> Dict[str, Any]:
    content_type = resp.headers.get("content-type", "")
    raw_text = resp.text or ""

    redirect_history = [
        {
            "status": item.status_code,
            "location": item.headers.get("location"),
        }
        for item in resp.history
    ]

    logger.warning(
        "[KUAIMAI_RESPONSE] status=%s content_type=%s body_length=%s body_preview=%r redirects=%s",
        resp.status_code,
        content_type,
        len(raw_text),
        raw_text[:500],
        redirect_history,
    )

    is_success = getattr(resp, "is_success", None)
    if is_success is None:
        is_success = 200 <= int(getattr(resp, "status_code", 0) or 0) < 300

    if not is_success:
        response_code = (
            "KUAIMAI_HTTP_5XX"
            if int(getattr(resp, "status_code", 0) or 0) >= 500
            else "KUAIMAI_HTTP_4XX"
        )
        raise KuaimaiPrintError(
            f"Kuaimai HTTP request failed: HTTP {resp.status_code}, "
            f"Content-Type={content_type}, response={raw_text[:500]}",
            code=response_code,
            status_code=resp.status_code,
        )

    if not raw_text.strip():
        raise KuaimaiPrintError(
            f"Kuaimai returned an empty response: HTTP {resp.status_code}",
            code="KUAIMAI_EMPTY_RESPONSE",
            status_code=502,
        )

    try:
        return resp.json()
    except ValueError:
        raise KuaimaiPrintError(
            f"Kuaimai returned a non-JSON response: HTTP {resp.status_code}, "
            f"Content-Type={content_type}, response={raw_text[:500]}",
            code="KUAIMAI_INVALID_RESPONSE",
            status_code=502,
        )


async def _post_kuaimai_payload(kuaimai_url: str, payload: Dict[str, Any], app_secret: str) -> Dict[str, Any]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8) as client:
            logger.warning("[KUAIMAI_REQUEST_SEND] about to send HTTP POST")
            resp = await client.post(
                kuaimai_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            logger.warning("[KUAIMAI_REQUEST_SENT] HTTP POST completed")

            body = _parse_kuaimai_response(resp)

            logger.warning(
                "[KUAIMAI_RESPONSE_PARSED] body_keys=%s status=%s code=%s",
                list(body.keys()),
                body.get("status"),
                body.get("code"),
            )

            if _is_successful_business_response(body):
                task_id = _extract_task_id(body)
                logger.warning("[KUAIMAI_SUCCESS] task_id=%s", task_id)
                return {
                    "success": True,
                    "provider": "kuaimai",
                    "provider_task_id": task_id,
                    "response": body,
                }

            if body.get("code") == 4015:
                logger.warning(
                    "[KUAIMAI_SIGN_DEBUG] sign=%s sign_keys=%s timestamp=%s",
                    payload.get("sign"),
                    [key for key in sorted(payload.keys()) if key != "sign"],
                    payload.get("timestamp"),
                )

            error_message = body.get("message") or body.get("msg") or body.get("exceptionMessage") or "unknown error"
            raise KuaimaiPrintError(
                f"Kuaimai business request failed: code={body.get('code')}, message={error_message}",
                code="KUAIMAI_BUSINESS_ERROR",
                status_code=502,
            )

    except httpx.TimeoutException as exc:
        logger.exception("[KUAIMAI_TEST_EXCEPTION] type=TimeoutException error=%s", str(exc))
        raise KuaimaiPrintError(
            "Kuaimai request timed out",
            code="KUAIMAI_TIMEOUT",
            status_code=504,
        )
    except httpx.ConnectError as exc:
        logger.exception("[KUAIMAI_TEST_EXCEPTION] type=ConnectError error=%s", str(exc))
        raise KuaimaiPrintError(
            "Kuaimai connection failed",
            code="KUAIMAI_CONNECTION_ERROR",
            status_code=502,
        )
    except httpx.HTTPStatusError as exc:
        logger.exception("[KUAIMAI_TEST_EXCEPTION] type=HTTPStatusError error=%s", str(exc))
        response_code = (
            "KUAIMAI_HTTP_5XX"
            if int(exc.response.status_code) >= 500
            else "KUAIMAI_HTTP_4XX"
        )
        raise KuaimaiPrintError(
            f"Kuaimai HTTP error: {exc.response.status_code}",
            code=response_code,
            status_code=exc.response.status_code,
        )
    except KuaimaiPrintError:
        raise
    except Exception as exc:
        logger.exception("[KUAIMAI_TEST_EXCEPTION] type=%s error=%s", type(exc).__name__, str(exc))
        raise KuaimaiPrintError(
            f"Kuaimai request exception: {str(exc)}",
            code="KUAIMAI_UNKNOWN_ERROR",
            status_code=502,
        )


async def print_order(
    app_id: str,
    app_secret: str,
    sn: str,
    content: str,
    copies: int = 1,
    share_code: str = "",
    device_key: str = "",
) -> Dict[str, Any]:
    logger.warning("[KUAIMAI_SERVICE_ENTER] app_id=%s sn=%s", app_id, _mask_string(sn))

    if not app_id or not app_secret or not sn:
        logger.warning("[KUAIMAI_SERVICE_ENTER] printer config incomplete, skip printing")
        return {"success": False, "error": "printer config incomplete"}

    logger.warning(
        "[KUAIMAI_CONFIG_CHECK] app_id=%s app_secret_present=%s app_secret_length=%s app_secret_prefix=%s app_secret_suffix=%s",
        app_id,
        bool(app_secret),
        len(app_secret),
        _mask_string(app_secret, keep_length=2),
        app_secret[-2:] if len(app_secret) >= 2 else "",
    )

    payload = build_print_payload(
        app_id,
        app_secret,
        sn,
        content,
        copies=copies,
        share_code=share_code,
        device_key=device_key,
    )
    kuaimai_url = f"{KUAIMAI_API_BASE}{KUAIMAI_ESC_WRITE_PATH}"

    logger.warning(
        "[KUAIMAI_REQUEST] url=%s method=POST printer_sn=%s payload_keys=%s timeout=8",
        kuaimai_url,
        _mask_string(sn),
        list(payload.keys()),
    )

    return await _post_kuaimai_payload(kuaimai_url, payload, app_secret)


async def print_template_order(
    app_id: str,
    app_secret: str,
    sn: str,
    template_id: str,
    render_data: dict[str, Any],
) -> Dict[str, Any]:
    logger.warning(
        "[KUAIMAI_TEMPLATE_ENTER] app_id=%s sn=%s template_id=%s",
        app_id,
        _mask_string(sn),
        template_id,
    )

    if not app_id or not app_secret or not sn or not template_id:
        logger.warning("[KUAIMAI_TEMPLATE_ENTER] printer config incomplete, skip printing")
        return {"success": False, "error": "printer config incomplete"}

    logger.warning(
        "[KUAIMAI_CONFIG_CHECK] app_id=%s app_secret_present=%s app_secret_length=%s app_secret_prefix=%s app_secret_suffix=%s template_id=%s sn=%s",
        app_id,
        bool(app_secret),
        len(app_secret),
        _mask_string(app_secret, keep_length=2),
        app_secret[-2:] if len(app_secret) >= 2 else "",
        template_id,
        _mask_string(sn),
    )

    is_order_payload = "order_no" in (render_data or {}) or "items" in (render_data or {})
    if is_order_payload:
        render_data = ensure_kuaimai_items_payload(render_data)
        items_value = render_data.get("items")
        items_first_item = items_value[0] if isinstance(items_value, list) and items_value else {}
        items_preview = {
            "goods_name": items_first_item.get("goods_name", "") if isinstance(items_first_item, dict) else "",
            "quantity_text": items_first_item.get("quantity_text", "") if isinstance(items_first_item, dict) else "",
            "item_amount_text": items_first_item.get("item_amount_text", "") if isinstance(items_first_item, dict) else "",
        }
        goods_value = render_data.get("goods")
        goods_first_item = goods_value[0] if isinstance(goods_value, list) and goods_value else {}
        logger.warning(
            "[KUAIMAI_FINAL_PAYLOAD_CHECK] event=KUAIMAI_FINAL_PAYLOAD_CHECK order_no=%s template_id=%s payload_top_level_keys=%s items_type=%s items_count=%s items_first_item_keys=%s items_first_item_preview=%s goods_type=%s goods_count=%s goods_first_item=%s pay_type_text=%s",
            render_data.get("order_no"),
            template_id,
            list(render_data.keys()),
            type(items_value).__name__,
            len(items_value) if isinstance(items_value, list) else "n/a",
            list(items_first_item.keys()) if isinstance(items_first_item, dict) else [],
            items_preview,
            type(goods_value).__name__,
            len(goods_value) if isinstance(goods_value, list) else "n/a",
            goods_first_item,
            render_data.get("pay_type_text"),
        )
        valid, error_code = validate_order_template_render_data(render_data)
        if not valid:
            logger.warning(
                "[PRINT_ITEMS_PAYLOAD_INVALID] order_no=%s template_id=%s items_type=%s items_count=%s items_first_item_keys=%s payload_top_level_keys=%s error_code=%s",
                render_data.get("order_no"),
                template_id,
                type(items_value).__name__,
                len(items_value) if isinstance(items_value, list) else "n/a",
                list(items_first_item.keys()) if isinstance(items_first_item, dict) else [],
                list(render_data.keys()),
                error_code,
            )
            return {"success": False, "error": error_code, "code": "PRINT_ITEMS_PAYLOAD_INVALID"}

    render_data_json = json.dumps(
        render_data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    )

    render_data_hash = hashlib.sha256(render_data_json.encode("utf-8")).hexdigest()
    logger.warning(
        "[KUAIMAI_RENDER_DATA] type=str length=%d sha256=%s preview=%r",
        len(render_data_json),
        render_data_hash,
        render_data_json[:300],
    )
    logger.warning(
        "[KUAIMAI_FINAL_RENDER_DATA_JSON] template_id=%s renderData=%s",
        template_id,
        render_data_json,
    )

    payload: dict[str, Any] = {
        "appId": app_id,
        "timestamp": _current_timestamp(),
        "sn": sn,
        "templateId": str(template_id),
        "renderData": render_data_json,
    }

    sign_keys = [key for key in sorted(payload.keys())]
    raw_sign_input = _sign_raw(payload, app_secret)
    generated_sign = hashlib.md5(raw_sign_input.encode("utf-8")).hexdigest()
    payload["sign"] = generated_sign

    logger.warning(
        "[KUAIMAI_SIGN_INPUT] keys=%s timestamp=%s timestamp_length=%d render_data_sha256=%s secret_length=%d generated_sign=%s",
        sign_keys,
        payload["timestamp"],
        len(payload["timestamp"]),
        render_data_hash,
        len(app_secret),
        generated_sign,
    )

    kuaimai_url = f"{KUAIMAI_API_BASE}{KUAIMAI_ESC_TEMPLATE_PRINT_PATH}"

    logger.warning(
        "[KUAIMAI_TEMPLATE_REQUEST] url=%s method=POST printer_sn=%s template_id=%s payload_keys=%s timeout=8",
        kuaimai_url,
        _mask_string(sn),
        template_id,
        list(payload.keys()),
    )

    render_data_parsed = json.loads(render_data_json)
    top_level_keys = list(render_data_parsed.keys())
    logger.warning(
        "[KUAIMAI_BROWSER_PARITY] payload_keys=%s timestamp=%s sn_masked=%s templateId=%s renderData_length=%d renderData_sha256=%s renderData_top_level_keys=%s sign=%s request_content_type=application/json",
        list(payload.keys()),
        payload["timestamp"],
        _mask_string(sn),
        template_id,
        len(render_data_json),
        render_data_hash,
        top_level_keys,
        generated_sign,
    )

    items_value = render_data_parsed.get("items")
    first_item_keys = list(items_value[0].keys()) if isinstance(items_value, list) and items_value else []
    try:
        return await _post_kuaimai_payload(kuaimai_url, payload, app_secret)
    except KuaimaiPrintError as exc:
        logger.warning(
            "[KUAIMAI_TEMPLATE_RENDER_FAILED] template_id=%s data_source=items items_type=%s items_count=%s first_item_keys=%s error_code=%s error_message=%s",
            template_id,
            type(items_value).__name__,
            len(items_value) if isinstance(items_value, list) else "n/a",
            first_item_keys,
            exc.code,
            str(exc),
        )
        raise
















