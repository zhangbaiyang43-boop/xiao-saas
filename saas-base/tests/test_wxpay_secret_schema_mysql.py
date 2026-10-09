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
    def alembic(cls, *args: str, database_url: str) -> None:
        environment = dict(os.environ, DATABASE_URL=database_url, REDIS_ENABLED="false")
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            check=True,
        )

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


if __name__ == "__main__":
    unittest.main()
