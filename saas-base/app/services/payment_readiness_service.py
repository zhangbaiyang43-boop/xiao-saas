"""Pure, local-only customer WeChat collection readiness evaluation.

This module deliberately does not import or initialize ``WxPayService``.  It
never calls WeChat, writes tenant state, or treats the legacy plaintext
compatibility fallback as proof that a stored secret is valid.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


READINESS_DISABLED = "DISABLED"
READINESS_INCOMPLETE = "INCOMPLETE"
READINESS_INVALID = "INVALID"
READINESS_UNKNOWN = "UNKNOWN"
READINESS_READY = "READY"  # Reserved for a later persisted LIVE_VERIFIED contract.

CHECK_CONFIGURED = "CONFIGURED"
CHECK_MISSING = "MISSING"
CHECK_INVALID = "INVALID"
CHECK_UNKNOWN = "UNKNOWN"
CHECK_NOT_APPLICABLE = "NOT_APPLICABLE"

PAYMENT_TIMING = {
    "prepay": ("先付款后出单", False),
    "postpay": ("餐后线下付款", True),
    "table_account": ("桌台累计统一结账", True),
}


def _value(source: Any, name: str, default: Any = None) -> Any:
    return getattr(source, name, default)


def _present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _item(
    code: str,
    label: str,
    status: str,
    *,
    blocking: bool,
    reason_code: str,
    remediation: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "status": status,
        "blocking": blocking,
        "reason_code": reason_code,
        "remediation": remediation,
    }


def _not_applicable_items() -> list[dict[str, Any]]:
    specs = (
        ("WX_MCHID", "微信支付商户号"),
        ("WX_API_KEY_V3", "APIv3 密钥"),
        ("WX_CERT_SERIAL", "商户证书序列号"),
        ("WX_PRIVATE_KEY", "商户 API 私钥"),
        ("WX_PUBLIC_KEY_ID", "微信支付公钥 ID"),
        ("WX_PUBLIC_KEY", "微信支付公钥"),
        ("WX_VERIFY_MODE", "验签模式"),
        ("GLOBAL_APP_ID", "小程序 AppID"),
        ("GLOBAL_APP_SECRET", "小程序 AppSecret"),
        ("GLOBAL_CALLBACK_URL", "支付回调基础域名"),
        ("GLOBAL_SECRET_ENCRYPTION", "服务端密钥加密能力"),
    )
    return [
        _item(
            code,
            label,
            CHECK_NOT_APPLICABLE,
            blocking=False,
            reason_code="ONLINE_PAYMENT_DISABLED",
            remediation="启用在线微信收款后再检查此项",
        )
        for code, label in specs
    ]


def _mask_mchid(mchid: Any) -> str:
    value = str(mchid or "").strip()
    if not value:
        return "-"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}****{value[-3:]}"


def _timing(tenant: Any) -> dict[str, Any]:
    code = str(_value(tenant, "payment_mode", "prepay") or "prepay")
    label, offline = PAYMENT_TIMING.get(code, ("付款方式未知", False))
    return {
        "code": code,
        "label": label,
        "offline_collection_available": offline,
    }


def _strict_fernet(global_config: Any) -> tuple[Fernet | None, dict[str, Any]]:
    raw_key = str(_value(global_config, "SECRET_ENCRYPTION_KEY", "") or "").strip()
    if not raw_key:
        return None, _item(
            "GLOBAL_SECRET_ENCRYPTION",
            "服务端密钥加密能力",
            CHECK_MISSING,
            blocking=True,
            reason_code="SECRET_ENCRYPTION_KEY_MISSING",
            remediation="在服务器 Secret 管理中配置有效的 Fernet 加密密钥",
        )
    try:
        return Fernet(raw_key.encode()), _item(
            "GLOBAL_SECRET_ENCRYPTION",
            "服务端密钥加密能力",
            CHECK_CONFIGURED,
            blocking=True,
            reason_code="CONFIGURED",
            remediation="无需处理",
        )
    except (TypeError, ValueError):
        return None, _item(
            "GLOBAL_SECRET_ENCRYPTION",
            "服务端密钥加密能力",
            CHECK_INVALID,
            blocking=True,
            reason_code="SECRET_ENCRYPTION_KEY_INVALID",
            remediation="由安全管理员修复服务器 Fernet 加密密钥配置",
        )


def _strict_decrypt(fernet: Fernet | None, encrypted: Any) -> tuple[str | None, str | None]:
    if not _present(encrypted):
        return None, "MISSING"
    if fernet is None:
        return None, "SECRET_VALIDATION_UNAVAILABLE"
    try:
        return fernet.decrypt(str(encrypted).encode()).decode(), None
    except (InvalidToken, UnicodeDecodeError, ValueError, TypeError):
        return None, "SECRET_DECRYPT_FAILED"


def _evaluate_secret(
    *,
    code: str,
    label: str,
    encrypted: Any,
    fernet: Fernet | None,
    validator,
    invalid_reason: str,
    remediation: str,
) -> dict[str, Any]:
    plaintext, error = _strict_decrypt(fernet, encrypted)
    if error == "MISSING":
        return _item(
            code,
            label,
            CHECK_MISSING,
            blocking=True,
            reason_code=f"{code}_MISSING",
            remediation=remediation,
        )
    if error == "SECRET_VALIDATION_UNAVAILABLE":
        return _item(
            code,
            label,
            CHECK_UNKNOWN,
            blocking=True,
            reason_code=error,
            remediation="先修复服务端密钥加密能力，再重新检查",
        )
    if error:
        return _item(
            code,
            label,
            CHECK_INVALID,
            blocking=True,
            reason_code=error,
            remediation=remediation,
        )
    try:
        valid = bool(validator(plaintext))
    except Exception:
        valid = False
    return _item(
        code,
        label,
        CHECK_CONFIGURED if valid else CHECK_INVALID,
        blocking=True,
        reason_code="CONFIGURED" if valid else invalid_reason,
        remediation="无需处理" if valid else remediation,
    )


def _pem_private_key_valid(value: str) -> bool:
    key = serialization.load_pem_private_key(
        value.replace("\\n", "\n").encode(),
        password=None,
    )
    return isinstance(key, rsa.RSAPrivateKey)


def _pem_public_key_valid(value: str) -> bool:
    key = serialization.load_pem_public_key(value.replace("\\n", "\n").encode())
    return isinstance(key, rsa.RSAPublicKey)


def _configured_or_missing(
    code: str,
    label: str,
    value: Any,
    remediation: str,
) -> dict[str, Any]:
    present = _present(value)
    return _item(
        code,
        label,
        CHECK_CONFIGURED if present else CHECK_MISSING,
        blocking=True,
        reason_code="CONFIGURED" if present else f"{code}_MISSING",
        remediation="无需处理" if present else remediation,
    )


def _evaluate_payment_readiness(tenant: Any, global_config: Any) -> dict[str, Any]:
    enabled = bool(_value(tenant, "wx_pay_enabled", False))
    timing = _timing(tenant)
    mchid = str(_value(tenant, "wx_mchid", "") or "").strip()
    base = {
        "tenant_id": str(_value(tenant, "tenant_id", "")),
        "payment_timing": timing,
    }
    enabled_item = _item(
        "WX_PAY_ENABLED",
        "在线微信收款",
        CHECK_CONFIGURED,
        blocking=False,
        reason_code="ONLINE_PAYMENT_ENABLED" if enabled else "ONLINE_PAYMENT_DISABLED",
        remediation="无需处理" if enabled else "如需线上预付，请通过受限运营流程启用在线微信收款",
    )
    if not enabled:
        return {
            **base,
            "online_payment": {
                "provider": "WECHAT_PAY_DIRECT",
                "enabled": False,
                "readiness_state": READINESS_DISABLED,
                "validation_level": "CONFIG_PRESENT",
                "validation_evidence_time": None,
                "effective_verify_mode": None,
                "masked_identifiers": {"wx_mchid": _mask_mchid(mchid)},
                "checklist": [enabled_item, *_not_applicable_items()],
                "missing_reasons": [],
                "invalid_reasons": [],
                "remediation": [enabled_item["remediation"]],
            },
        }

    checklist: list[dict[str, Any]] = [enabled_item]
    mchid_item = _configured_or_missing(
        "WX_MCHID",
        "微信支付商户号",
        mchid,
        "在微信支付商户平台核对并配置商户号",
    )
    if mchid and not re.fullmatch(r"\d{10,15}", mchid):
        mchid_item = _item(
            "WX_MCHID",
            "微信支付商户号",
            CHECK_INVALID,
            blocking=True,
            reason_code="WX_MCHID_INVALID",
            remediation="核对商户号是否为 10 至 15 位数字",
        )
    checklist.append(mchid_item)

    fernet, encryption_item = _strict_fernet(global_config)
    checklist.extend(
        (
            _evaluate_secret(
                code="WX_API_KEY_V3",
                label="APIv3 密钥",
                encrypted=_value(tenant, "wx_api_key_v3"),
                fernet=fernet,
                validator=lambda value: len(value.encode()) == 32,
                invalid_reason="WX_API_KEY_V3_INVALID",
                remediation="通过受限安全流程重新配置 32 字节 APIv3 密钥",
            ),
            _configured_or_missing(
                "WX_CERT_SERIAL",
                "商户证书序列号",
                _value(tenant, "wx_cert_serial"),
                "配置当前商户 API 证书序列号",
            ),
            _evaluate_secret(
                code="WX_PRIVATE_KEY",
                label="商户 API 私钥",
                encrypted=_value(tenant, "wx_private_key"),
                fernet=fernet,
                validator=_pem_private_key_valid,
                invalid_reason="WX_PRIVATE_KEY_INVALID",
                remediation="通过受限安全流程重新配置可解析的商户 RSA 私钥",
            ),
        )
    )
    serial_item = checklist[-2]
    serial = str(_value(tenant, "wx_cert_serial", "") or "").strip()
    if serial and not re.fullmatch(r"[A-Fa-f0-9]{40,64}", serial):
        serial_item.update(
            status=CHECK_INVALID,
            reason_code="WX_CERT_SERIAL_INVALID",
            remediation="核对证书序列号是否为 40 至 64 位十六进制字符",
        )

    public_key_id = str(_value(tenant, "wx_public_key_id", "") or "").strip()
    public_key = str(_value(tenant, "wx_public_key", "") or "").strip()
    if bool(public_key_id) != bool(public_key):
        effective_mode = "invalid"
        checklist.extend(
            (
                _item(
                    "WX_PUBLIC_KEY_ID",
                    "微信支付公钥 ID",
                    CHECK_INVALID,
                    blocking=True,
                    reason_code="PUBLIC_KEY_PAIR_INCOMPLETE",
                    remediation="微信支付公钥 ID 与公钥内容必须同时配置或同时留空",
                ),
                _item(
                    "WX_PUBLIC_KEY",
                    "微信支付公钥",
                    CHECK_INVALID,
                    blocking=True,
                    reason_code="PUBLIC_KEY_PAIR_INCOMPLETE",
                    remediation="微信支付公钥 ID 与公钥内容必须同时配置或同时留空",
                ),
            )
        )
    elif public_key_id and public_key:
        effective_mode = "public_key"
        id_valid = public_key_id.startswith("PUB_KEY_ID_")
        checklist.append(
            _item(
                "WX_PUBLIC_KEY_ID",
                "微信支付公钥 ID",
                CHECK_CONFIGURED if id_valid else CHECK_INVALID,
                blocking=True,
                reason_code="CONFIGURED" if id_valid else "WX_PUBLIC_KEY_ID_INVALID",
                remediation="无需处理" if id_valid else "从微信支付 API 安全页复制以 PUB_KEY_ID_ 开头的公钥 ID",
            )
        )
        try:
            key_valid = _pem_public_key_valid(public_key)
        except Exception:
            key_valid = False
        checklist.append(
            _item(
                "WX_PUBLIC_KEY",
                "微信支付公钥",
                CHECK_CONFIGURED if key_valid else CHECK_INVALID,
                blocking=True,
                reason_code="CONFIGURED" if key_valid else "WX_PUBLIC_KEY_INVALID",
                remediation="无需处理" if key_valid else "重新下载并配置可解析的微信支付公钥",
            )
        )
    else:
        effective_mode = "platform_certificate"
        checklist.extend(
            (
                _item(
                    "WX_PUBLIC_KEY_ID",
                    "微信支付公钥 ID",
                    CHECK_NOT_APPLICABLE,
                    blocking=False,
                    reason_code="PLATFORM_CERTIFICATE_MODE",
                    remediation="平台证书模式无需配置",
                ),
                _item(
                    "WX_PUBLIC_KEY",
                    "微信支付公钥",
                    CHECK_NOT_APPLICABLE,
                    blocking=False,
                    reason_code="PLATFORM_CERTIFICATE_MODE",
                    remediation="平台证书模式无需配置",
                ),
            )
        )

    declared_mode = str(_value(tenant, "wx_verify_mode", "") or "").strip()
    if declared_mode not in {"public_key", "platform_certificate"}:
        mode_item = _item(
            "WX_VERIFY_MODE",
            "验签模式",
            CHECK_INVALID,
            blocking=False,
            reason_code="VERIFY_MODE_DECLARATION_INVALID",
            remediation="后续安全维护阶段对齐声明值；当前运行模式仍按实际公钥字段组合判断",
        )
    elif declared_mode != effective_mode:
        mode_item = _item(
            "WX_VERIFY_MODE",
            "验签模式",
            CHECK_UNKNOWN,
            blocking=False,
            reason_code="VERIFY_MODE_NOT_RUNTIME_AUTHORITY",
            remediation="声明值与实际字段组合不同；当前不阻断，只按实际运行模式展示",
        )
    else:
        mode_item = _item(
            "WX_VERIFY_MODE",
            "验签模式",
            CHECK_CONFIGURED,
            blocking=False,
            reason_code="CONFIGURED",
            remediation="无需处理",
        )
    checklist.append(mode_item)

    # Match the existing customer-payment runtime authority.  WECHAT_APP_ is
    # the legacy compatibility field used only when WECHAT_APP_ID is absent.
    app_id = str(
        _value(global_config, "WECHAT_APP_ID", "")
        or _value(global_config, "WECHAT_APP_", "")
        or ""
    ).strip()
    app_id_item = _configured_or_missing(
        "GLOBAL_APP_ID",
        "小程序 AppID",
        app_id,
        "在服务器配置生产小程序 AppID",
    )
    if app_id and not re.fullmatch(r"wx[A-Za-z0-9]{16}", app_id):
        app_id_item.update(
            status=CHECK_INVALID,
            reason_code="GLOBAL_APP_ID_INVALID",
            remediation="核对小程序 AppID 格式",
        )
    checklist.append(app_id_item)
    checklist.append(
        _configured_or_missing(
            "GLOBAL_APP_SECRET",
            "小程序 AppSecret",
            _value(global_config, "WECHAT_APP_SECRET"),
            "在服务器 Secret 管理中配置小程序 AppSecret",
        )
    )

    callback_url = str(_value(global_config, "H5_ORDER_BASE_URL", "") or "").strip()
    callback_item = _configured_or_missing(
        "GLOBAL_CALLBACK_URL",
        "支付回调基础域名",
        callback_url,
        "配置公网可访问的 HTTPS 回调基础域名",
    )
    if callback_url:
        parsed = urlparse(callback_url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            callback_item.update(
                status=CHECK_INVALID,
                reason_code="CALLBACK_URL_INVALID",
                remediation="配置不含凭证信息的公网 HTTPS 回调基础域名",
            )
    checklist.extend((callback_item, encryption_item))

    blocking_missing = [
        item["reason_code"]
        for item in checklist
        if item["blocking"] and item["status"] == CHECK_MISSING
    ]
    blocking_invalid = [
        item["reason_code"]
        for item in checklist
        if item["blocking"] and item["status"] == CHECK_INVALID
    ]
    blocking_unknown = [
        item["reason_code"]
        for item in checklist
        if item["blocking"] and item["status"] == CHECK_UNKNOWN
    ]
    all_invalid = list(dict.fromkeys(
        item["reason_code"] for item in checklist if item["status"] == CHECK_INVALID
    ))
    if blocking_missing:
        readiness_state = READINESS_INCOMPLETE
    elif blocking_invalid:
        readiness_state = READINESS_INVALID
    else:
        readiness_state = READINESS_UNKNOWN
    static_valid = not blocking_missing and not blocking_invalid and not blocking_unknown
    remediation = list(dict.fromkeys(
        item["remediation"]
        for item in checklist
        if item["status"] not in {CHECK_CONFIGURED, CHECK_NOT_APPLICABLE}
    ))
    return {
        **base,
        "online_payment": {
            "provider": "WECHAT_PAY_DIRECT",
            "enabled": True,
            "readiness_state": readiness_state,
            "validation_level": "STATIC_VALID" if static_valid else "CONFIG_PRESENT",
            "validation_evidence_time": None,
            "effective_verify_mode": effective_mode,
            "masked_identifiers": {"wx_mchid": _mask_mchid(mchid)},
            "checklist": checklist,
            "missing_reasons": list(dict.fromkeys(blocking_missing)),
            "invalid_reasons": all_invalid,
            "remediation": remediation,
        },
    }


def evaluate_payment_readiness(tenant: Any, global_config: Any) -> dict[str, Any]:
    """Return a secret-free readiness DTO and fail closed on checker defects."""
    try:
        return _evaluate_payment_readiness(tenant, global_config)
    except Exception:
        return {
            "tenant_id": str(_value(tenant, "tenant_id", "")),
            "payment_timing": _timing(tenant),
            "online_payment": {
                "provider": "WECHAT_PAY_DIRECT",
                "enabled": bool(_value(tenant, "wx_pay_enabled", False)),
                "readiness_state": READINESS_UNKNOWN,
                "validation_level": "CONFIG_PRESENT",
                "validation_evidence_time": None,
                "effective_verify_mode": None,
                "masked_identifiers": {"wx_mchid": _mask_mchid(_value(tenant, "wx_mchid"))},
                "checklist": [],
                "missing_reasons": [],
                "invalid_reasons": ["READINESS_CHECK_FAILED"],
                "remediation": ["只读检查暂时无法完成，请稍后重试或联系技术支持"],
            },
        }
