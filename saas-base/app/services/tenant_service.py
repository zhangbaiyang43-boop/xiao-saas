from copy import deepcopy
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.security import get_password_hash, verify_password
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig


DEFAULT_MEMBER_RULES = {
    "levels": [
        {"level": "Lv1", "name": "普通会员", "threshold": 0},
        {"level": "Lv2", "name": "银卡会员", "threshold": 299},
        {"level": "Lv3", "name": "金卡会员", "threshold": 999},
    ],
    "points_per_yuan": 1,
    "points_to_yuan": 100,
    "max_points_discount_percent": 30,
    "birthday_benefit": True,
    "fast_upgrade_days": 7,
    "fast_upgrade_amount": 99,
}

# 券的面额 / 门槛 / 有效期 / 加权组合一律由 platform_rules.build_dynamic_rules()
# 按商户实际客单价 + 营销强度(保守/标准/激进)动态计算，商家不配置这些。
# 建店种子里每个「发券时机」只保留一个 enabled 开关，供商家在「智能营销」页
# 按需关闭某个时机。任何写死的金额/券名/有效期都不再存在，彻底消除两套规则打架。
COUPON_RULE_KEYS = (
    "entry_coupon",
    "new_customer_coupon",
    "consumption_coupon",
    "recall_coupon",
    "points_reward_coupon",
)

DEFAULT_COUPON_RULES = {key: {"enabled": True} for key in COUPON_RULE_KEYS}


def normalize_coupon_rules(rules: dict | None) -> dict:
    """把 tenant_config.coupon_rules 收敛成「只有 enabled 开关」的形状。

    历史上建店会写入一份带金额/门槛/有效期/weighted_coupons/locked 的胖配置，
    和 platform_rules 动态算出来的值打架（表现为顾客拿到写死的 ¥ 5满18、1天过期、
    券名叫"超过80%用户"）。这里把任何经济性字段一律丢掉，只留 enabled——
    读写 coupon_rules 的每条路径都过一遍，老商户下次访问即自愈，无需单独迁移。
    """
    out: dict = {}
    for key, rule in (rules or {}).items():
        if isinstance(rule, dict):
            out[key] = {"enabled": bool(rule.get("enabled", True))}
    return out

DEFAULT_BUSINESS_INFO = {
    "business_hours": "09:00-21:00",
    "contact_phone": "",
    "notice": "",
    "service_scope": "",
    "longitude": "",
    "latitude": "",
    # 营销：业态 + 强度。业态只作冷启动「连菜单都没有」时的兜底客单价（见
    # platform_rules 的 INDUSTRY_PRESETS）；强度是保守/标准/激进旋钮，同时决定
    # 月优惠预算总闸的比例。都留空则用 default / standard。
    "industry": "",
    "marketing_intensity": "",
    # 实体桌牌：默认关闭，避免升级影响不需要桌牌的老商户
    "pickup_no_enabled": False,
    "pickup_no_count": 30,
    "pickup_no_required_before_print": True,
}

DEFAULT_PLUGIN_SETTINGS = {
    "coupon": {"default_enabled": True},
    "points": {"default_enabled": False},
    "crm": {"default_enabled": False},
    "bargain": {"default_enabled": False},
    "distribution": {
        "enabled": True,
        "level1_amount": 2,
        "level2_amount": 1,
        "settlement_mode": "fixed_after_verify",
    },
}


def deep_merge(base: dict, patch: dict | None) -> dict:
    result = deepcopy(base or {})
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def apply_coupon_rule_locks(current_rules: dict | None, patch_rules: dict | None) -> dict | None:
    if patch_rules is None:
        return None

    current_rules = current_rules or {}
    protected_fields = {
        "amount",
        "threshold",
        "valid_days",
        "trigger_amount",
        "inactive_days",
        "weighted_enabled",
        "weighted_coupons",
        "locked",
        "locked_at",
    }
    result = deepcopy(patch_rules)

    for rule_key, patch_rule in (patch_rules or {}).items():
        if not isinstance(patch_rule, dict):
            continue
        current_rule = current_rules.get(rule_key) or {}
        if current_rule.get("locked"):
            if patch_rule.get("unlock_locked"):
                result[rule_key] = {
                    **current_rule,
                    "locked": False,
                    "unlocked_at": datetime.utcnow().isoformat(),
                }
                continue
            allowed_patch = {}
            if "enabled" in patch_rule:
                allowed_patch["enabled"] = patch_rule["enabled"]
            result[rule_key] = deep_merge(current_rule, allowed_patch)
            continue
        if patch_rule.get("locked"):
            result[rule_key] = {
                **patch_rule,
                "locked": True,
                "locked_at": patch_rule.get("locked_at") or datetime.utcnow().isoformat(),
            }
        else:
            result[rule_key] = {
                key: value
                for key, value in patch_rule.items()
                if key not in protected_fields or key == "enabled"
            } if current_rule.get("locked") else patch_rule

    return result


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def build_default_config() -> dict:
        return {
            "member_rules": deepcopy(DEFAULT_MEMBER_RULES),
            "coupon_rules": deepcopy(DEFAULT_COUPON_RULES),
            "business_info": deepcopy(DEFAULT_BUSINESS_INFO),
            "plugin_settings": deepcopy(DEFAULT_PLUGIN_SETTINGS),
        }

    async def create_tenant(
        self,
        tenant_id: str,
        name: str,
        password_hash: str = "",
        phone: str = None,
        address: str = None,
        logo_url: str = None,
        status: bool = True,
        payment_mode: str = None,
        *,
        commit: bool = True,
    ) -> Tenant:
        """commit=False lets a caller (e.g. the self-registration endpoint) fold
        this insert into a larger all-or-nothing transaction alongside other
        writes (like trial provisioning) — it flushes instead, so tenant.id is
        populated and visible to later statements on the same session, but
        nothing is durable until the caller itself commits. Every existing
        caller (super-admin merchant creation, the legacy unmounted /api/auth
        router) omits this argument and keeps committing immediately, unchanged.

        payment_mode=None (the default) lets the Tenant model's own column
        default ("prepay") apply unchanged -- only a caller that explicitly
        wants a different starting mode (Phase 02's self-registration
        Activation policy) passes one."""
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            password_hash=password_hash,
            phone=phone,
            address=address,
            logo_url=logo_url,
            status=status,
            **({"payment_mode": payment_mode} if payment_mode is not None else {}),
        )
        defaults = self.build_default_config()
        config = TenantConfig(
            tenant_id=tenant_id,
            member_rules=defaults["member_rules"],
            coupon_rules=defaults["coupon_rules"],
            business_info=defaults["business_info"],
            plugin_settings=defaults["plugin_settings"],
        )
        self.db.add(tenant)
        self.db.add(config)
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()
        await self.db.refresh(tenant)
        return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant:
        result = await self.db.execute(select(Tenant).filter(Tenant.tenant_id == tenant_id))
        return result.scalar_one_or_none()

    async def get_tenant_by_phone(self, phone: str) -> Tenant:
        if not phone:
            return None
        result = await self.db.execute(select(Tenant).filter(Tenant.phone == phone))
        return result.scalar_one_or_none()

    async def get_tenant_config(self, tenant_id: str) -> TenantConfig:
        result = await self.db.execute(select(TenantConfig).filter(TenantConfig.tenant_id == tenant_id))
        return result.scalar_one_or_none()

    async def ensure_tenant_config(self, tenant_id: str) -> TenantConfig:
        config = await self.get_tenant_config(tenant_id)
        if config:
            defaults = self.build_default_config()
            config.member_rules = deep_merge(defaults["member_rules"], config.member_rules)
            config.coupon_rules = normalize_coupon_rules(
                deep_merge(defaults["coupon_rules"], getattr(config, "coupon_rules", None))
            )
            config.business_info = deep_merge(defaults["business_info"], getattr(config, "business_info", None))
            config.plugin_settings = deep_merge(defaults["plugin_settings"], config.plugin_settings)
            return config

        defaults = self.build_default_config()
        config = TenantConfig(
            tenant_id=tenant_id,
            member_rules=defaults["member_rules"],
            coupon_rules=defaults["coupon_rules"],
            business_info=defaults["business_info"],
            plugin_settings=defaults["plugin_settings"],
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def update_tenant_profile(self, tenant: Tenant, **kwargs) -> Tenant:
        allowed_fields = {"name", "phone", "address", "logo_url", "status"}
        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(tenant, key, value)

        if self.db is not None:
            await self.db.commit()
            await self.db.refresh(tenant)

        return tenant

    async def update_tenant_settings(
        self,
        tenant: Tenant,
        config: TenantConfig,
        profile: dict | None = None,
        member_rules: dict | None = None,
        coupon_rules: dict | None = None,
        business_info: dict | None = None,
        plugin_settings: dict | None = None,
    ) -> tuple[Tenant, TenantConfig]:
        await self.update_tenant_profile(tenant, **(profile or {}))
        defaults = self.build_default_config()
        config.member_rules = deep_merge(defaults["member_rules"], deep_merge(config.member_rules, member_rules))
        # 券的经济性由 platform_rules 动态算，商户配置只认 enabled 开关——
        # normalize 兜底：不管前端传了什么金额/门槛/locked，落库只留 enabled。
        config.coupon_rules = normalize_coupon_rules(
            deep_merge(defaults["coupon_rules"], deep_merge(config.coupon_rules, coupon_rules))
        )
        config.business_info = deep_merge(defaults["business_info"], deep_merge(config.business_info, business_info))
        config.plugin_settings = deep_merge(defaults["plugin_settings"], deep_merge(config.plugin_settings, plugin_settings))

        if self.db is not None:
            flag_modified(config, "member_rules")
            flag_modified(config, "coupon_rules")
            flag_modified(config, "business_info")
            flag_modified(config, "plugin_settings")
            await self.db.commit()
            await self.db.refresh(config)

        return tenant, config

    async def change_password(self, tenant: Tenant, old_password: str, new_password: str) -> bool:
        if not verify_password(old_password, tenant.password_hash):
            return False
        tenant.password_hash = get_password_hash(new_password)
        if self.db is not None:
            await self.db.commit()
            await self.db.refresh(tenant)
        return True
