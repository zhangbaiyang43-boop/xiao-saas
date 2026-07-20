import asyncio
import inspect
import unittest

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.schema_compat import ensure_queue_ticket_schema, ensure_tenant_schema
from app.main import startup


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class SchemaCompatContractsTest(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_tenant_schema_repairs_legacy_sqlite_columns(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        CREATE TABLE tenant (
                            id BIGINT PRIMARY KEY,
                            tenant_id VARCHAR(32) NOT NULL,
                            name VARCHAR(64) NOT NULL,
                            password_hash VARCHAR(128) NOT NULL,
                            corp_id VARCHAR(64),
                            phone VARCHAR(20),
                            address VARCHAR(500),
                            logo_url VARCHAR(500),
                            status BOOLEAN,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL
                        )
                        """
                    )
                )
                await ensure_tenant_schema(conn)
                result = await conn.execute(text("PRAGMA table_info(tenant)"))
                columns = {row[1] for row in result.fetchall()}
        finally:
            await engine.dispose()

        self.assertIn("is_open", columns)
        self.assertIn("wx_pay_enabled", columns)
        self.assertIn("wx_mchid", columns)
        self.assertIn("wx_api_key_v3", columns)
        self.assertIn("wx_cert_serial", columns)
        self.assertIn("wx_private_key", columns)
        self.assertIn("receiver_name", columns)
        self.assertIn("receiver_type", columns)
        self.assertIn("receiver_verified", columns)
        self.assertIn("payment_locked", columns)
        self.assertIn("verified_time", columns)
        self.assertIn("feieyun_sn", columns)
        self.assertIn("feieyun_key", columns)

    async def test_ensure_queue_ticket_schema_repairs_legacy_sqlite_columns(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        CREATE TABLE queue_tickets (
                            id BIGINT PRIMARY KEY,
                            tenant_id VARCHAR(32) NOT NULL,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL,
                            queue_no VARCHAR(16) NOT NULL,
                            queue_type VARCHAR(1) NOT NULL,
                            queue_date DATE NOT NULL,
                            daily_sequence INTEGER NOT NULL,
                            party_size INTEGER NOT NULL,
                            phone VARCHAR(20),
                            note TEXT,
                            status VARCHAR(16) NOT NULL,
                            called_at DATETIME,
                            seated_at DATETIME,
                            skipped_at DATETIME
                        )
                        """
                    )
                )
                await ensure_queue_ticket_schema(conn)
                result = await conn.execute(text("PRAGMA table_info(queue_tickets)"))
                columns = {row[1] for row in result.fetchall()}
        finally:
            await engine.dispose()

        self.assertIn("query_token", columns)

    def test_startup_runs_tenant_schema_repair(self):
        source = inspect.getsource(startup)

        self.assertIn("ensure_tenant_schema", source)
        self.assertIn("ensure_queue_ticket_schema", source)


if __name__ == "__main__":
    unittest.main()
