import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
import jwt
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1 import super_admin
from app.config import settings
from app.core.database import get_db
from app.main import app
from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.fulfilment_mode import (
    FULFILMENT_PRINT_FIRST,
    FULFILMENT_WORKBENCH,
    get_fulfilment_mode,
)
from app.services.merchant_provisioning_service import (
    MerchantProvisioningService,
    ProvisioningSource,
)


def make_request() -> Request:
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/super/merchants/test/fulfilment-mode",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.request_id = "request-fulfilment-001"
    return request


class SuperFulfilmentModeControlTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.db = self.SessionLocal()
        self._tenant_seq = 0

        async def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()

    @staticmethod
    def _token(token_type: str, *, expires_in: timedelta = timedelta(hours=1)) -> str:
        return jwt.encode(
            {
                "sub": f"{token_type}-actor",
                "type": token_type,
                "exp": datetime.utcnow() + expires_in,
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    async def _create_existing_tenant(self, tenant_id: str, mode: str | None) -> Tenant:
        self._tenant_seq += 1
        tenant = Tenant(
            tenant_id=tenant_id,
            name=f"Merchant {tenant_id}",
            phone=f"1360000{self._tenant_seq:04d}",
            password_hash="x",
            status=True,
        )
        business_info = {} if mode is None else {"fulfilment_mode": mode}
        self.db.add(tenant)
        self.db.add(
            TenantConfig(
                tenant_id=tenant_id,
                member_rules={},
                coupon_rules={},
                business_info=business_info,
                plugin_settings={},
            )
        )
        await self.db.commit()
        return tenant

    async def test_new_merchants_from_both_authorities_default_to_print_first(self):
        service = MerchantProvisioningService(self.db)
        for index, source in enumerate(
            (ProvisioningSource.SELF_REGISTER, ProvisioningSource.SUPER_ADMIN),
            start=1,
        ):
            result = await service.provision_merchant(
                name=f"New Merchant {index}",
                phone=f"1370000010{index}",
                source=source,
            )
            config = await self.db.scalar(
                select(TenantConfig).where(
                    TenantConfig.tenant_id == result.tenant.tenant_id
                )
            )
            self.assertEqual(
                config.business_info["fulfilment_mode"],
                FULFILMENT_PRINT_FIRST,
            )

    async def test_legacy_missing_key_stays_workbench_and_super_list_reads_it(self):
        await self._create_existing_tenant("legacy-no-mode", None)
        await self._create_existing_tenant("explicit-print-first", FULFILMENT_PRINT_FIRST)
        self.assertEqual(
            await get_fulfilment_mode(self.db, "legacy-no-mode"),
            FULFILMENT_WORKBENCH,
        )
        response = await super_admin.list_merchants(db=self.db)
        modes = {row["tenant_id"]: row["fulfilment_mode"] for row in response.data}
        self.assertEqual(modes["legacy-no-mode"], FULFILMENT_WORKBENCH)
        self.assertEqual(modes["explicit-print-first"], FULFILMENT_PRINT_FIRST)

    async def test_super_switches_both_directions_without_mutating_orders(self):
        tenant = await self._create_existing_tenant("switch-mode", FULFILMENT_WORKBENCH)
        order = Order(
            tenant_id=tenant.tenant_id,
            status="pending",
            payment_status="unpaid",
            payment_mode="table_account",
            table_no="A01",
            total=10,
        )
        self.db.add(order)
        await self.db.commit()

        for before, after in (
            (FULFILMENT_WORKBENCH, FULFILMENT_PRINT_FIRST),
            (FULFILMENT_PRINT_FIRST, FULFILMENT_WORKBENCH),
        ):
            self.assertEqual(await get_fulfilment_mode(self.db, tenant.tenant_id), before)
            with patch.object(super_admin.logger, "info") as audit_log:
                response = await super_admin.update_merchant_fulfilment_mode(
                    tenant.tenant_id,
                    super_admin.FulfilmentModeUpdateRequest(
                        mode=after,
                        reason="门店高峰期无需人工确认订单",
                    ),
                    make_request(),
                    operator="super_admin",
                    db=self.db,
                )
            self.assertEqual(response.code, 200)
            self.assertEqual(response.data["fulfilment_mode"], after)
            audit_text = str(audit_log.call_args)
            self.assertIn(f"before_mode={before}", audit_text)
            self.assertIn(f"after_mode={after}", audit_text)
            self.assertIn("reason=门店高峰期无需人工确认订单", audit_text)
            self.assertIn("operator=super_admin", audit_text)
            self.assertIn("request_id=request-fulfilment-001", audit_text)
            self.assertIn("ip=testclient", audit_text)
            persisted_order = await self.db.get(Order, order.id)
            self.assertEqual(persisted_order.status, "pending")

    async def test_invalid_mode_blank_reason_and_missing_config_are_rejected(self):
        tenant = await self._create_existing_tenant("reject-invalid", FULFILMENT_WORKBENCH)
        invalid_mode = await super_admin.update_merchant_fulfilment_mode(
            tenant.tenant_id,
            super_admin.FulfilmentModeUpdateRequest(mode="AUTO_ACCEPT", reason="invalid"),
            make_request(),
            operator="super_admin",
            db=self.db,
        )
        blank_reason = await super_admin.update_merchant_fulfilment_mode(
            tenant.tenant_id,
            super_admin.FulfilmentModeUpdateRequest(mode=FULFILMENT_PRINT_FIRST, reason="   "),
            make_request(),
            operator="super_admin",
            db=self.db,
        )
        missing_config = Tenant(
            tenant_id="missing-config",
            name="Missing Config",
            phone="13699999999",
            password_hash="x",
            status=True,
        )
        self.db.add(missing_config)
        await self.db.commit()
        no_config = await super_admin.update_merchant_fulfilment_mode(
            missing_config.tenant_id,
            super_admin.FulfilmentModeUpdateRequest(
                mode=FULFILMENT_PRINT_FIRST,
                reason="operator decision",
            ),
            make_request(),
            operator="super_admin",
            db=self.db,
        )
        self.assertEqual(invalid_mode.code, 400)
        self.assertEqual(blank_reason.code, 400)
        self.assertEqual(no_config.code, 409)
        self.assertEqual(
            await get_fulfilment_mode(self.db, tenant.tenant_id),
            FULFILMENT_WORKBENCH,
        )

    async def test_same_mode_is_idempotent(self):
        tenant = await self._create_existing_tenant("same-mode", FULFILMENT_PRINT_FIRST)
        response = await super_admin.update_merchant_fulfilment_mode(
            tenant.tenant_id,
            super_admin.FulfilmentModeUpdateRequest(
                mode=FULFILMENT_PRINT_FIRST,
                reason="confirm current mode",
            ),
            make_request(),
            operator="super_admin",
            db=self.db,
        )
        self.assertEqual(response.code, 200)
        self.assertTrue(response.data["idempotent"])

    async def test_missing_invalid_and_expired_tokens_are_unauthorized(self):
        path = "/api/super/merchants/auth-contract/fulfilment-mode"
        payload = {"mode": FULFILMENT_PRINT_FIRST, "reason": "auth boundary"}
        cases = (
            {},
            {"X-Super-Token": "not-a-jwt"},
            {
                "X-Super-Token": self._token(
                    "super_admin",
                    expires_in=timedelta(seconds=-1),
                )
            },
        )
        for headers in cases:
            with self.subTest(headers=headers):
                response = await self.client.patch(path, headers=headers, json=payload)
                self.assertEqual(response.status_code, 401)

    async def test_merchant_and_staff_tokens_are_forbidden(self):
        path = "/api/super/merchants/auth-contract/fulfilment-mode"
        payload = {"mode": FULFILMENT_PRINT_FIRST, "reason": "auth boundary"}
        for token_type in ("tenant", "staff"):
            with self.subTest(token_type=token_type):
                response = await self.client.patch(
                    path,
                    headers={"X-Super-Token": self._token(token_type)},
                    json=payload,
                )
                self.assertEqual(response.status_code, 403)

    def test_merchant_settings_strip_operator_only_key(self):
        from inspect import getsource

        from app.api.v1.tenant import update_settings

        self.assertIn(
            'merged_business_info.pop("fulfilment_mode", None)',
            getsource(update_settings),
        )


if __name__ == "__main__":
    unittest.main()
