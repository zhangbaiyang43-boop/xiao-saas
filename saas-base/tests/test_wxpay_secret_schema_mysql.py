from __future__ import annotations

import os
import subprocess
import sys
import unittest

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


MYSQL_URL = os.getenv("WXPAY_SCHEMA_TEST_DATABASE_URL", "")


@unittest.skipUnless(MYSQL_URL.startswith("mysql+asyncmy://"), "isolated MySQL schema gate only")
class WxPaySecretSchemaMySqlTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def alembic(cls, *args: str, database_url: str, check: bool = True) -> subprocess.CompletedProcess:
        environment = dict(os.environ, DATABASE_URL=database_url, REDIS_ENABLED="false")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise AssertionError(f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
        return result

    async def asyncSetUp(self):
        self.engine = create_async_engine(MYSQL_URL)
        async with self.engine.begin() as connection:
            await connection.execute(text("DROP DATABASE IF EXISTS wxpay_schema_gate"))
            await connection.execute(
                text("CREATE DATABASE wxpay_schema_gate CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            )
        await self.engine.dispose()
        self.database_url = MYSQL_URL.rsplit("/", 1)[0] + "/wxpay_schema_gate?charset=utf8mb4"

    async def asyncTearDown(self):
        engine = create_async_engine(MYSQL_URL)
        async with engine.begin() as connection:
            await connection.execute(text("DROP DATABASE IF EXISTS wxpay_schema_gate"))
        await engine.dispose()

    async def column_type(self) -> str:
        engine = create_async_engine(self.database_url)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT DATA_TYPE FROM information_schema.columns "
                        "WHERE table_schema=DATABASE() AND table_name='tenant' "
                        "AND column_name='wx_private_key'"
                    )
                )
                return str(result.scalar_one()).lower()
        finally:
            await engine.dispose()

    async def test_varchar_and_existing_text_both_converge_idempotently_without_truncation(self):
        original = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.database_url
        try:
            self.alembic("upgrade", "20260830_0001", database_url=self.database_url)
            engine = create_async_engine(self.database_url)
            async with engine.begin() as connection:
                await connection.execute(
                    text("ALTER TABLE tenant MODIFY COLUMN wx_private_key VARCHAR(4096) NULL")
                )
            await engine.dispose()

            self.alembic("upgrade", "head", database_url=self.database_url)
            self.assertEqual(await self.column_type(), "text")

            engine = create_async_engine(self.database_url)
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO tenant "
                        "(tenant_id,name,password_hash,status,is_open,payment_mode,wx_pay_enabled,"
                        "receiver_verified,payment_locked,created_at,updated_at,wx_private_key) "
                        "VALUES ('schema-gate','Schema Gate','x',1,1,'prepay',0,0,1,NOW(),NOW(),:value)"
                    ),
                    {"value": "x" * 6000},
                )
                stored_length = await connection.scalar(
                    text("SELECT CHAR_LENGTH(wx_private_key) FROM tenant WHERE tenant_id='schema-gate'")
                )
            await engine.dispose()
            self.assertEqual(stored_length, 6000)

            self.alembic("upgrade", "head", database_url=self.database_url)
            self.assertEqual(await self.column_type(), "text")

            engine = create_async_engine(self.database_url)
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE alembic_version SET version_num='20260830_0001'")
                )
            await engine.dispose()
            self.alembic("upgrade", "head", database_url=self.database_url)
            self.assertEqual(await self.column_type(), "text")
        finally:
            if original is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original


    INSERT_TENANT = (
        "INSERT INTO tenant "
        "(tenant_id,name,password_hash,status,is_open,payment_mode,wx_pay_enabled,"
        "receiver_verified,payment_locked,created_at,updated_at,wx_api_key_v3,wx_private_key) "
        "VALUES (:tenant_id,:name,'x',1,1,'prepay',0,0,1,NOW(),NOW(),:api_key,:private_key)"
    )

    async def seed_tenants(self, rows: list[tuple[str, str | None, str | None]]) -> None:
        engine = create_async_engine(self.database_url)
        try:
            async with engine.begin() as connection:
                for tenant_id, api_key, private_key in rows:
                    await connection.execute(
                        text(self.INSERT_TENANT),
                        {"tenant_id": tenant_id, "name": tenant_id, "api_key": api_key, "private_key": private_key},
                    )
        finally:
            await engine.dispose()

    async def snapshot(self) -> dict:
        """Column type, revision and every tenant secret, read back from MySQL."""
        engine = create_async_engine(self.database_url)
        try:
            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        text("SELECT tenant_id, wx_api_key_v3, wx_private_key FROM tenant ORDER BY tenant_id")
                    )
                ).all()
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                column = (
                    await connection.execute(
                        text(
                            "SELECT DATA_TYPE, COLUMN_TYPE FROM information_schema.columns "
                            "WHERE table_schema=DATABASE() AND table_name='tenant' AND column_name='wx_private_key'"
                        )
                    )
                ).one()
        finally:
            await engine.dispose()
        return {
            "rows": [tuple(row) for row in rows],
            "revision": revision,
            "data_type": str(column[0]).lower(),
            "column_type": str(column[1]).lower(),
        }

    async def upgrade_to_head(self) -> None:
        self.alembic("upgrade", "head", database_url=self.database_url)
        self.assertEqual(await self.column_type(), "text")

    async def test_downgrade_of_short_data_is_safe_and_restores_varchar_4096(self):
        pem = "-----BEGIN PRIVATE KEY-----\nSYNTHETIC-SHORT\n-----END PRIVATE KEY-----"
        await self.upgrade_to_head()
        await self.seed_tenants([("short-1", "A" * 32, pem), ("short-2", None, "y" * 4096)])
        before = await self.snapshot()
        self.assertEqual(before["data_type"], "text")

        self.alembic("downgrade", "20260830_0001", database_url=self.database_url)

        after = await self.snapshot()
        print(f"DOWNGRADE=PASS DATA_UNCHANGED={after['rows'] == before['rows']} COLUMN_TYPE={after['column_type']}")
        self.assertEqual(after["rows"], before["rows"])
        self.assertEqual(after["data_type"], "varchar")
        self.assertEqual(after["column_type"], "varchar(4096)")
        self.assertEqual(after["revision"], "20260830_0001")

    async def test_downgrade_rejects_oversize_value_without_truncation_or_revision_change(self):
        await self.upgrade_to_head()
        await self.seed_tenants([("oversize-1", "A" * 32, "z" * 4097)])
        before = await self.snapshot()

        result = self.alembic("downgrade", "20260830_0001", database_url=self.database_url, check=False)

        after = await self.snapshot()
        print(
            f"DOWNGRADE=REJECTED DATA_UNCHANGED={after['rows'] == before['rows']} "
            f"COLUMN_TYPE={after['column_type']} ALEMBIC_REVISION_UNCHANGED={after['revision'] == before['revision']}"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to narrow tenant.wx_private_key", result.stdout + result.stderr)
        self.assertEqual(after["rows"], before["rows"])
        self.assertEqual(after["data_type"], "text")
        self.assertEqual(after["column_type"], "text")
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["revision"], "20261009_0001")

    async def test_multi_tenant_mixed_data_is_all_or_nothing_on_rejection(self):
        short_pem = "-----BEGIN PRIVATE KEY-----\nSYNTHETIC-SHORT\n-----END PRIVATE KEY-----"
        long_pem = "-----BEGIN PRIVATE KEY-----\n" + "S" * 5000 + "\n-----END PRIVATE KEY-----"
        await self.upgrade_to_head()
        await self.seed_tenants(
            [
                ("mixed-a-short-api", "A" * 32, None),
                ("mixed-b-short-pem", None, short_pem),
                ("mixed-c-long-pem", "B" * 32, long_pem),
                ("mixed-d-empty", None, None),
            ]
        )
        before = await self.snapshot()

        result = self.alembic("downgrade", "20260830_0001", database_url=self.database_url, check=False)

        after = await self.snapshot()
        print(f"MIXED_DOWNGRADE=REJECTED TENANTS={len(after['rows'])} DATA_UNCHANGED={after['rows'] == before['rows']}")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(after["rows"], before["rows"])
        self.assertEqual(after["column_type"], "text")
        self.assertEqual(after["revision"], "20261009_0001")
        self.assertEqual(len(after["rows"]), 4)


if __name__ == "__main__":
    unittest.main()
