"""
微信支付普通商户模式封装（每个商家用自己的 mchid + 证书）
依赖：pip install wechatpayv3
"""
import asyncio
import json
import secrets
import time
from typing import Optional

from app.config import settings
from app.core.crypto import decrypt_secret
from app.core.logger import logger

PROVIDER_REFUND_SUCCESS = "SUCCESS"
PROVIDER_REFUND_PROCESSING = "PROCESSING"
PROVIDER_REFUND_FAILED = {"CLOSED", "ABNORMAL"}
INTERNAL_REFUND_SUCCESS = "success"
INTERNAL_REFUND_PROCESSING = "processing"
INTERNAL_REFUND_FAILED = "failed"


def map_provider_refund_status(status: Optional[str]) -> str:
    value = str(status or "").strip().upper()
    if value == PROVIDER_REFUND_SUCCESS:
        return INTERNAL_REFUND_SUCCESS
    if value == PROVIDER_REFUND_PROCESSING or not value:
        return INTERNAL_REFUND_PROCESSING
    if value in PROVIDER_REFUND_FAILED:
        return INTERNAL_REFUND_FAILED
    return INTERNAL_REFUND_FAILED


def _parse_response_body(message_body):
    try:
        return json.loads(message_body) if isinstance(message_body, str) else message_body
    except Exception:
        return None


def _get_wechat_app_id() -> str:
    return (getattr(settings, 'WECHAT_APP_ID', '') or getattr(settings, 'WECHAT_APP_', '') or '').strip()


def _build_client(
    mchid: str,
    api_key_v3: str,
    cert_serial: str,
    private_key_pem: str,
    public_key_id: str = None,
    public_key_pem: str = None,
    timeout=None,
):
    """用商家自己的证书初始化 SDK 客户端。支持公钥模式和平台证书模式。

    timeout: optional (connect, read) tuple forwarded to wechatpayv3's requests calls.
    Defaults to None (unbounded, today's existing behavior for every caller that doesn't
    explicitly opt in) -- see P1-WXPAY-RECOVERY-GATE: only the recovery-query path passes
    a real value; create_jsapi_order/refund/notify verification are untouched.
    """
    try:
        from wechatpayv3 import WeChatPay, WeChatPayType
        private_key = private_key_pem.replace("\\n", "\n")
        kwargs = {
            "wechatpay_type": WeChatPayType.MINIPROG,
            "mchid": mchid,
            "private_key": private_key,
            "cert_serial_no": cert_serial,
            "appid": _get_wechat_app_id(),
            "apiv3_key": api_key_v3,
            "timeout": timeout,
        }
        if public_key_id and public_key_pem:
            kwargs["public_key"] = public_key_pem.replace("\\n", "\n")
            kwargs["public_key_id"] = public_key_id
            logger.info(f"微信支付初始化: 使用公钥模式, public_key_id={public_key_id[:8]}...")
        else:
            logger.info("微信支付初始化: 使用平台证书模式")
        return WeChatPay(**kwargs)
    except ImportError:
        logger.warning("wechatpayv3 未安装，请执行: pip install wechatpayv3")
        return None
    except Exception as e:
        logger.error(f"微信支付 SDK 初始化失败: {e}")
        return None


class WxPayService:
    """
    普通商户模式：每个商家用自己的微信支付账号。
    传入商家的四个凭证，按单笔构建 SDK 客户端。

    使用方式：
        svc = WxPayService(tenant)
        if not svc.enabled:
            # 商家未配置支付，降级 mock
        params = await svc.create_jsapi_order(...)
    """

    def __init__(self, tenant, *, timeout=None):
        """tenant 为 Tenant ORM 对象，从中读取支付配置。

        timeout: optional (connect, read) tuple, forwarded to the SDK client. Defaults to
        None (unbounded -- unchanged behavior for every existing caller). Only the P1
        recovery-query path (_recover_wxpay_order_if_paid) passes a real value; every other
        WxPayService(tenant) construction in the codebase (create_jsapi_order, wxpay_notify
        verification, refund) is untouched by this parameter.
        """
        self._client = None
        self.last_verify_reason = "UNKNOWN_VERIFY_FAILURE"
        if (
            getattr(tenant, "wx_pay_enabled", False)
            and getattr(tenant, "wx_mchid", None)
            and getattr(tenant, "wx_api_key_v3", None)
            and getattr(tenant, "wx_cert_serial", None)
            and getattr(tenant, "wx_private_key", None)
        ):
            self._client = _build_client(
                mchid=tenant.wx_mchid,
                api_key_v3=decrypt_secret(tenant.wx_api_key_v3),
                cert_serial=tenant.wx_cert_serial,
                private_key_pem=decrypt_secret(tenant.wx_private_key),
                public_key_id=getattr(tenant, "wx_public_key_id", None),
                public_key_pem=getattr(tenant, "wx_public_key", None),
                timeout=timeout,
            )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def create_jsapi_order(
        self,
        openid: str,
        out_trade_no: str,
        amount_fen: int,
        description: str,
        notify_url: str,
    ) -> dict:
        """
        发起 JSAPI 下单，返回小程序调起支付所需的参数包。

        Returns:
            {
                "timeStamp": "...",
                "nonceStr": "...",
                "package": "prepay_id=wx...",
                "signType": "RSA",
                "paySign": "...",
            }
        Raises:
            RuntimeError: 下单失败
        """
        if not self.enabled:
            raise RuntimeError("商家未配置微信支付")

        code, message_body = self._client.pay(
            description=description,
            out_trade_no=out_trade_no,
            amount={"total": amount_fen, "currency": "CNY"},
            payer={"openid": openid},
            notify_url=notify_url,
        )

        if code != 200:
            try:
                body_obj = json.loads(message_body) if isinstance(message_body, str) else message_body
                wechat_code = body_obj.get("code", "") if isinstance(body_obj, dict) else ""
                wechat_message = body_obj.get("message", "") if isinstance(body_obj, dict) else ""
                wechat_detail = body_obj.get("detail", "") if isinstance(body_obj, dict) else ""
            except:
                wechat_code = ""
                wechat_message = str(message_body)[:500] if message_body else ""
                wechat_detail = ""
            
            logger.error(
                "[WXPAY_JSAPI_FAIL] code=%s wechat_code=%s wechat_message=%s wechat_detail=%s raw_type=%s",
                code, wechat_code, wechat_message, wechat_detail, type(message_body).__name__,
            )
            raise RuntimeError(f"微信下单失败: code={code} message={wechat_message}")

        body = json.loads(message_body) if isinstance(message_body, str) else message_body
        prepay_id = body.get("prepay_id", "")
        if not prepay_id:
            raise RuntimeError("微信下单成功但未返回 prepay_id")

        logger.info("[WXPAY_PREPAY_SUCCESS] has_prepay_id=true")

        app_id = _get_wechat_app_id()
        time_stamp = str(int(time.time()))
        nonce_str = secrets.token_hex(16)
        package = f"prepay_id={prepay_id}"
        pay_sign = self._client.sign([
            app_id,
            time_stamp,
            nonce_str,
            package,
        ])
        logger.info("[WXPAY_PARAMS_READY] fields=timeStamp,nonceStr,package,signType,paySign")

        return {
            "timeStamp": time_stamp,
            "nonceStr": nonce_str,
            "package": package,
            "signType": "RSA",
            "paySign": pay_sign,
        }


    async def refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_fen: int,
        total_fen: int,
        reason: Optional[str] = None,
    ) -> dict:
        """
        申请微信退款。out_refund_no 应使用确定性的值（如 f"RF{order.id}"），
        这样即使这个方法被意外重复调用，微信也会把它当作同一笔退款请求的重复查询，
        不会重复扣款/重复退款。

        Returns:
            {"success": True, "status": "...", "refund_status": "success|processing|failed", "raw": {...}}
        Raises:
            RuntimeError: 退款请求失败（网络错误、微信返回非 200/204）
        """
        if not self.enabled:
            raise RuntimeError("商家未配置微信支付")

        code, message_body = self._client.refund(
            out_refund_no=out_refund_no,
            amount={"refund": refund_fen, "total": total_fen, "currency": "CNY"},
            out_trade_no=out_trade_no,
            reason=reason,
        )

        body = _parse_response_body(message_body)

        if code not in (200, 204):
            wechat_message = (body or {}).get("message") if isinstance(body, dict) else str(message_body)[:300]
            logger.error(
                "[WXPAY_REFUND_FAIL] out_trade_no=%s out_refund_no=%s code=%s message=%s",
                out_trade_no, out_refund_no, code, wechat_message,
            )
            raise RuntimeError(f"微信退款申请失败: code={code} message={wechat_message}")

        status = (body or {}).get("status", "") if isinstance(body, dict) else ""
        refund_status = map_provider_refund_status(status)
        logger.info(
            "[WXPAY_REFUND_SUBMITTED] out_trade_no=%s out_refund_no=%s status=%s refund_status=%s",
            out_trade_no, out_refund_no, status, refund_status,
        )
        return {"success": True, "status": status, "refund_status": refund_status, "raw": body}

    async def query_refund_by_out_refund_no(self, out_refund_no: str) -> Optional[dict]:
        """Query a WeChat Pay refund by merchant out_refund_no using the SDK signer."""
        if not self.enabled:
            return None

        fn = getattr(self._client, "query_refund", None)
        if not callable(fn):
            logger.warning("[WXPAY_QUERY_REFUND_UNSUPPORTED] out_refund_no=%s", out_refund_no)
            return None
        try:
            result = await asyncio.to_thread(fn, out_refund_no)
            if isinstance(result, tuple) and len(result) >= 2:
                code, body = result[0], result[1]
                if code not in (200, 204):
                    logger.warning("[WXPAY_QUERY_REFUND_FAIL] out_refund_no=%s code=%s", out_refund_no, code)
                    return None
                body_obj = _parse_response_body(body)
            else:
                body_obj = _parse_response_body(result)
            if not isinstance(body_obj, dict):
                return None
            status = body_obj.get("status", "")
            return {
                **body_obj,
                "refund_status": map_provider_refund_status(status),
            }
        except Exception as exc:
            logger.warning("[WXPAY_QUERY_REFUND_FAIL] out_refund_no=%s error=%s", out_refund_no, exc)
            return None

    async def query_order_by_out_trade_no(self, out_trade_no: str) -> Optional[dict]:
        """Query a WeChat Pay order by merchant out_trade_no for callback-loss recovery."""
        if not self.enabled:
            return None

        candidates = [
            ("query", lambda fn: fn(out_trade_no=out_trade_no)),
            ("query", lambda fn: fn(out_trade_no)),
            ("query_order", lambda fn: fn(out_trade_no=out_trade_no)),
            ("query_order", lambda fn: fn(out_trade_no)),
            ("query_order_by_out_trade_no", lambda fn: fn(out_trade_no)),
        ]
        last_error = None
        for method_name, caller in candidates:
            fn = getattr(self._client, method_name, None)
            if not callable(fn):
                continue
            try:
                # P1-WXPAY-RECOVERY-GATE: this is a synchronous, blocking SDK call
                # (wechatpayv3's Core.request uses module-level requests.get/post, not a
                # persisted Session -- safe to run off-thread; a fresh WeChatPay/Core
                # instance is already built per WxPayService(tenant) construction, so
                # there is no shared mutable client state across threads). Without this,
                # the call blocks the entire asyncio event loop -- every other coroutine
                # on this process, not just this request -- for its full duration.
                result = await asyncio.to_thread(caller, fn)
                if isinstance(result, tuple) and len(result) >= 2:
                    code, body = result[0], result[1]
                    if code not in (200, 204):
                        continue
                    return json.loads(body) if isinstance(body, str) else body
                return json.loads(result) if isinstance(result, str) else result
            except TypeError as exc:
                last_error = exc
                continue
            except Exception as exc:
                logger.warning("[WXPAY_QUERY_ORDER_FAIL] out_trade_no=%s method=%s error=%s", out_trade_no, method_name, exc)
                return None
        if last_error:
            logger.warning("[WXPAY_QUERY_ORDER_UNSUPPORTED] out_trade_no=%s error=%s", out_trade_no, last_error)
        return None
    def verify_notify(self, headers: dict, body: bytes) -> Optional[dict]:
        """
        验证微信回调签名，返回解密后的通知数据，验签失败返回 None。
        注意：回调中只有 out_trade_no，需要先查订单拿到商家信息再构建本实例。
        """
        resource, reason = self.verify_notify_classified(headers, body)
        self.last_verify_reason = reason
        return resource

    def verify_notify_classified(self, headers: dict, body: bytes) -> tuple[Optional[dict], str]:
        """Same security path as verify_notify, with a stable failure reason.

        Reasons are diagnostic only. Callers must not change accept/reject
        behavior based on these strings.
        """
        if not self.enabled:
            return None, "CERTIFICATE_MISMATCH"
        try:
            result = self._client.callback(headers, body)
        except Exception:
            return None, "SIGNATURE_VERIFY_FAILED"
        if not result:
            return None, "INVALID_CALLBACK"
        if result.get("event_type") == "TRANSACTION.SUCCESS":
            return result.get("resource", {}) or {}, "OK"
        return None, "UNSUPPORTED_EVENT_TYPE"

