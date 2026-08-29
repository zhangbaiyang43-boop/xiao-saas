import asyncio
import json
import unittest
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.member import login_or_create
from app.models.base import Base
from app.models.customer import Customer
from app.models.entrance_code import EntranceCode
from app.models.tenant import Tenant
from app.utils.id_generator import generate_snowflake_id


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def make_request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/member/login-or-create",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        },
        receive=receive,
    )


class DemoMemberGuardTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.db = session_factory()
        self.db.add_all(
            [
                Tenant(
                    tenant_id="demo-tenant",
                    name="开心点单体验店",
                    password_hash="x",
                    status=True,
                    is_open=True,
                ),
                Tenant(
                    tenant_id="formal-tenant",
                    name="正式门店",
                    password_hash="x",
                    status=True,
                    is_open=True,
                ),
            ]
        )
        code_id = generate_snowflake_id()
        self.db.add(
            EntranceCode(
                id=code_id,
                tenant_id="demo-tenant",
                name="DEMO-01",
                channel="DEMO",
                scene=f"D{code_id}"[:32],
                table_no="DEMO-01",
                entry_type="table",
                status=1,
            )
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def customer_count(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(Customer))
        return int(result.scalar() or 0)

    @patch("app.config.settings.DEMO_TENANT_ID", "demo-tenant")
    async def test_direct_demo_tenant_member_login_is_rejected(self):
        response = await login_or_create(
            make_request({"tenant_id": "demo-tenant", "code": "wx-code"}),
            self.db,
        )

        self.assertEqual(response.code, 403)
        self.assertEqual(response.msg, "体验模式无需登录会员")
        self.assertEqual(await self.customer_count(), 0)

    @patch("app.config.settings.DEMO_TENANT_ID", "demo-tenant")
    async def test_demo_scene_member_login_is_rejected(self):
        entrance = (
            await self.db.execute(
                select(EntranceCode).where(EntranceCode.tenant_id == "demo-tenant")
            )
        ).scalar_one()

        response = await login_or_create(
            make_request(
                {
                    "tenant_id": "demo-tenant",
                    "entrance_scene": entrance.scene,
                    "code": "wx-code",
                }
            ),
            self.db,
        )

        self.assertEqual(response.code, 403)
        self.assertEqual(await self.customer_count(), 0)

    @patch("app.config.settings.DEMO_TENANT_ID", "demo-tenant")
    async def test_formal_tenant_keeps_existing_missing_code_behavior(self):
        response = await login_or_create(
            make_request({"tenant_id": "formal-tenant"}), self.db
        )

        self.assertEqual(response.code, 400)
        self.assertEqual(response.msg, "请提供微信登录 code")
        self.assertEqual(await self.customer_count(), 0)


if __name__ == "__main__":
    unittest.main()
