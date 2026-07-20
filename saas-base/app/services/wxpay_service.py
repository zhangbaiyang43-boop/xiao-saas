"""
微信支付普通商户模式封装（每个商家用自己的 mchid + 证书）
依赖：pip install wechatpayv3
"""
import json
import secrets
import time
from typing import Optional

from app.config import settings
from app.core.logger import logger


def _get_wechat_app_id() -> str:
    return (getattr(settings, 'WECHAT_APP_ID', '') or getattr(settings, 'WECHAT_APP_', '') or '').strip()


def _build_client(mchid: str, api_key_v3: str, cert_serial: str, private_key_pem: str, public_key_id: str = None, public_key_pem: str = None):
    """用商家自己的证书初始化 SDK 客户端。支持公钥模式和平台证书模式。"""
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

    def __init__(self, tenant):
        """tenant 为 Tenant ORM 对象，从中读取支付配置。"""
        self._client = None
        if (
            getattr(tenant, "wx_pay_enabled", False)
            and getattr(tenant, "wx_mchid", None)
            and getattr(tenant, "wx_api_key_v3", None)
            and getattr(tenant, "wx_cert_serial", None)
            and getattr(tenant, "wx_private_key", None)
        ):
            self._client = _build_client(
                mchid=tenant.wx_mchid,
                api_key_v3=tenant.wx_api_key_v3,
                cert_serial=tenant.wx_cert_serial,
                private_key_pem=tenant.wx_private_key,
                public_key_id=getattr(tenant, "wx_public_key_id", None),
                public_key_pem=getattr(tenant, "wx_public_key", None),
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
            {"success": True, "status": "...", "raw": {...}}
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

        try:
            body = json.loads(message_body) if isinstance(message_body, str) else message_body
        except Exception:
            body = None

        if code not in (200, 204):
            wechat_message = (body or {}).get("message") if isinstance(body, dict) else str(message_body)[:300]
            logger.error(
                "[WXPAY_REFUND_FAIL] out_trade_no=%s out_refund_no=%s code=%s message=%s",
                out_trade_no, out_refund_no, code, wechat_message,
            )
            raise RuntimeError(f"微信退款申请失败: code={code} message={wechat_message}")

        status = (body or {}).get("status", "") if isinstance(body, dict) else ""
        logger.info(
            "[WXPAY_REFUND_SUBMITTED] out_trade_no=%s out_refund_no=%s status=%s",
            out_trade_no, out_refund_no, status,
        )
        return {"success": True, "status": status, "raw": body}

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
                result = caller(fn)
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
        if not self.enabled:
            return None
        try:
            result = self._client.callback(headers, body)
            if result and result.get("event_type") == "TRANSACTION.SUCCESS":
                return result.get("resource", {})
            return None
        except Exception as e:
            logger.error(f"微信支付回调验签失败: {e}")
            return None

