import asyncio
import unittest

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.security import create_access_token, get_password_hash, verify_password, verify_token
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.tenant_service import (
    DEFAULT_BUSINESS_INFO,
    DEFAULT_COUPON_RULES,
    DEFAULT_MEMBER_RULES,
    DEFAULT_PLUGIN_SETTINGS,
    TenantService,
)


class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.refreshed = []

    def add(self, entity):
        self.added.append(entity)

    async def commit(self):
        self.commits += 1

    async def refresh(self, entity):
        self.refreshed.append(entity)


class TenantAccountContractsTest(unittest.TestCase):
    def test_access_token_contains_tenant_id(self):
        token = create_access_token("tenant-001")
        payload = verify_token(token)

        self.assertEqual(payload["tenant_id"], "tenant-001")
        self.assertEqual(payload["sub"], "tenant-001")

    def test_create_tenant_initializes_profile_and_default_config(self):
        session = FakeSession()
        service = TenantService(session)

        tenant = asyncio.run(service.create_tenant(
            tenant_id="tenant-001",
            name="小城美发店",
            password_hash="hashed",
            phone="13800000000",
            address="人民路 1 号",
            logo_url="https://example.com/logo.png",
        ))

        self.assertIsInstance(tenant, Tenant)
        self.assertEqual(tenant.name, "小城美发店")
        self.assertEqual(tenant.address, "人民路 1 号")
        self.assertEqual(tenant.logo_url, "https://example.com/logo.png")
        self.assertTrue(tenant.status)

        configs = [item for item in session.added if isinstance(item, TenantConfig)]
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].tenant_id, "tenant-001")
        self.assertEqual(configs[0].member_rules["levels"][1]["threshold"], 299)
        self.assertEqual(configs[0].coupon_rules["new_customer_coupon"]["enabled"], True)
        self.assertEqual(configs[0].business_info["business_hours"], "09:00-21:00")
        self.assertEqual(configs[0].plugin_settings["coupon"], {"default_enabled": True})

    def test_default_settings_are_deep_copied(self):
        first = TenantService.build_default_config()
        second = TenantService.build_default_config()

        first["member_rules"]["levels"][0]["name"] = "changed"

        self.assertEqual(second["member_rules"]["levels"][0]["name"], DEFAULT_MEMBER_RULES["levels"][0]["name"])
        self.assertEqual(second["coupon_rules"], DEFAULT_COUPON_RULES)
        self.assertEqual(second["business_info"], DEFAULT_BUSINESS_INFO)
        self.assertEqual(second["plugin_settings"], DEFAULT_PLUGIN_SETTINGS)

    def test_update_profile_only_allows_safe_profile_fields(self):
        tenant = Tenant(
            tenant_id="tenant-001",
            name="旧店名",
            password_hash="hashed",
            phone="13800000000",
            status=True,
        )
        service = TenantService(FakeSession())

        updated = asyncio.run(service.update_tenant_profile(
            tenant,
            name="新店名",
            phone="13900000000",
            address="新地址",
            logo_url="https://example.com/new.png",
            status=False,
            password_hash="should-not-change",
        ))

        self.assertEqual(updated.name, "新店名")
        self.assertEqual(updated.phone, "13900000000")
        self.assertEqual(updated.address, "新地址")
        self.assertEqual(updated.logo_url, "https://example.com/new.png")
        self.assertFalse(updated.status)
        self.assertEqual(updated.password_hash, "hashed")

    def test_update_tenant_settings_merges_profile_and_config(self):
        session = FakeSession()
        service = TenantService(session)
        tenant = Tenant(tenant_id="tenant-001", name="旧店名", password_hash="hashed", status=True)
        config = TenantConfig(
            tenant_id="tenant-001",
            member_rules=TenantService.build_default_config()["member_rules"],
            coupon_rules=TenantService.build_default_config()["coupon_rules"],
            business_info=TenantService.build_default_config()["business_info"],
            plugin_settings=TenantService.build_default_config()["plugin_settings"],
        )

        asyncio.run(service.update_tenant_settings(
            tenant,
            config,
            profile={"name": "新店名", "password_hash": "ignore"},
            member_rules={"points_per_yuan": 2},
            coupon_rules={"consume_coupon": {"enabled": True, "amount": 8}},  # amount 会被 normalize 丢弃，只留 enabled
            business_info={"notice": "周末正常营业"},
            plugin_settings={"points": {"default_enabled": True}},
        ))

        self.assertEqual(tenant.name, "新店名")
        self.assertEqual(tenant.password_hash, "hashed")
        self.assertEqual(config.member_rules["points_per_yuan"], 2)
        self.assertEqual(config.coupon_rules["consume_coupon"], {"enabled": True})
        self.assertEqual(config.business_info["notice"], "周末正常营业")
        self.assertEqual(config.plugin_settings["points"]["default_enabled"], True)

    def test_change_password_requires_old_password_and_updates_hash(self):
        tenant = Tenant(
            tenant_id="tenant-001",
            name="测试门店",
            password_hash=get_password_hash("old-password"),
            phone="13800000000",
            status=True,
        )
        service = TenantService(FakeSession())

        changed = asyncio.run(service.change_password(tenant, "old-password", "new-password"))

        self.assertTrue(changed)
        self.assertTrue(verify_password("new-password", tenant.password_hash))
        self.assertFalse(verify_password("old-password", tenant.password_hash))

    def test_change_password_rejects_wrong_old_password(self):
        tenant = Tenant(
            tenant_id="tenant-001",
            name="测试门店",
            password_hash=get_password_hash("old-password"),
            phone="13800000000",
            status=True,
        )
        service = TenantService(FakeSession())

        changed = asyncio.run(service.change_password(tenant, "bad-password", "new-password"))

        self.assertFalse(changed)
        self.assertTrue(verify_password("old-password", tenant.password_hash))


if __name__ == "__main__":
    unittest.main()
