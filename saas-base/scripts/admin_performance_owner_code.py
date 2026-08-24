"""Safely seed the fixed staging performance tenant's owner login code."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from scripts.admin_performance_dataset import (
    DATASET_VERSION,
    PERF_OWNER_PHONE,
    PERF_TENANT_ID,
    PERF_TENANT_NAME,
    DatasetSafetyError,
    validate_runtime_guard,
)


class OwnerCodeSafetyError(RuntimeError):
    """Raised before an owner-code operation can cross its safety boundary."""


def validate_owner_code(value: object) -> str:
    """Return a normalized owner code only when it is six ASCII digits."""

    normalized = str(value or "").strip()
    if re.fullmatch(r"[0-9]{6}", normalized) is None:
        raise OwnerCodeSafetyError("PERF_OWNER_LOGIN_CODE must be exactly 6 digits")
    return normalized


def mask_owner_phone(phone: str) -> str:
    """Mask the fixed owner's phone for safe reports."""

    value = str(phone or "")
    if len(value) == 11:
        return f"{value[:3]}****{value[-4:]}"
    return "****"


async def seed_owner_login_code(session_factory, code: object) -> dict[str, Any]:
    """Store a login code only for the exact marked performance identity."""

    normalized_code = validate_owner_code(code)
    async with session_factory() as session:
        tenant = await session.scalar(
            select(Tenant).where(Tenant.tenant_id == PERF_TENANT_ID)
        )
        config = await session.scalar(
            select(TenantConfig).where(TenantConfig.tenant_id == PERF_TENANT_ID)
        )

    if tenant is None:
        raise OwnerCodeSafetyError("fixed performance tenant is missing")
    if config is None:
        raise OwnerCodeSafetyError("fixed performance tenant config is missing")
    if tenant.name != PERF_TENANT_NAME:
        raise OwnerCodeSafetyError("fixed performance tenant name does not match")
    if tenant.phone != PERF_OWNER_PHONE:
        raise OwnerCodeSafetyError("fixed performance owner phone does not match")

    business_info = config.business_info
    marker = business_info.get("performanceTest") if isinstance(business_info, dict) else None
    if not isinstance(marker, dict):
        raise OwnerCodeSafetyError("fixed performance marker is missing")
    if (
        marker.get("datasetVersion") != DATASET_VERSION
        or marker.get("source") != "test"
    ):
        raise OwnerCodeSafetyError("fixed performance marker does not match")

    from app.services.tencent_sms_service import SmsPurpose, TencentSmsService

    await TencentSmsService().store_login_code(
        PERF_OWNER_PHONE,
        normalized_code,
        SmsPurpose.LOGIN,
    )
    return {
        "status": "PASS",
        "dataset_version": DATASET_VERSION,
        "tenant_id": PERF_TENANT_ID,
        "phone": mask_owner_phone(PERF_OWNER_PHONE),
        "purpose": SmsPurpose.LOGIN,
    }


async def _run_cli() -> dict[str, Any]:
    from app.config import settings

    environment, _database = validate_runtime_guard(
        settings.APP_ENV,
        settings.DATABASE_URL,
        os.getenv("PERF_DATASET_ACK", ""),
    )
    if environment != "staging":
        raise OwnerCodeSafetyError("APP_ENV must be exactly staging")

    code = os.getenv("PERF_OWNER_LOGIN_CODE", "")
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        return await seed_owner_login_code(session_factory, code)
    finally:
        await engine.dispose()


def main() -> int:
    try:
        report = asyncio.run(_run_cli())
    except (DatasetSafetyError, OwnerCodeSafetyError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception:
        print(
            json.dumps(
                {"status": "FAIL", "message": "owner code operation failed"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
