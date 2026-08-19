"""F1G-CM-PD0-GF Phase 22: read-only tenant/subscription count query.

For a future PD0 operator to run against PRODUCTION *before* deploying the
20260819_0002 migration, to know in advance how many tenants will be
grandfathered. Read-only: SELECT statements only, no INSERT/UPDATE/DELETE,
no schema change. Safe to run repeatedly and safe to run against a database
still on any pre-20260819_0002 revision.

Usage (operator sets DATABASE_URL to the real production connection string
themselves -- this script never contains or assumes any real credential):

    DATABASE_URL="mysql+asyncmy://<user>:<pass>@<host>/<db>?charset=utf8mb4" \\
        python scripts/pd0gf_tenant_grandfather_readonly_count.py
"""
from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        tenant_count = (await conn.execute(sa.text("SELECT COUNT(*) FROM tenant"))).scalar_one()

        zero_subscription_count = (
            await conn.execute(
                sa.text(
                    """
                    SELECT COUNT(*)
                    FROM tenant t
                    WHERE NOT EXISTS (
                        SELECT 1 FROM subscriptions s WHERE s.tenant_id = t.tenant_id
                    )
                    """
                )
            )
        ).scalar_one()

        existing_subscription_count = tenant_count - zero_subscription_count

        # Safe identifying info only -- tenant_id (business identifier) and
        # name, never phone/wx credentials/private keys.
        sample_rows = (
            await conn.execute(
                sa.text(
                    """
                    SELECT t.tenant_id, t.name
                    FROM tenant t
                    WHERE NOT EXISTS (
                        SELECT 1 FROM subscriptions s WHERE s.tenant_id = t.tenant_id
                    )
                    ORDER BY t.tenant_id
                    LIMIT 50
                    """
                )
            )
        ).fetchall()

        print(f"TENANT_COUNT={tenant_count}")
        print(f"ZERO_SUBSCRIPTION_TENANT_COUNT={zero_subscription_count}")
        print(f"EXISTING_SUBSCRIPTION_TENANT_COUNT={existing_subscription_count}")
        print(f"WILL_BE_GRANDFATHERED_ON_UPGRADE={zero_subscription_count}")
        print("ZERO_SUBSCRIPTION_TENANT_SAMPLE (tenant_id, name; capped at 50):")
        for tenant_id, name in sample_rows:
            print(f"  {tenant_id}  {name}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
