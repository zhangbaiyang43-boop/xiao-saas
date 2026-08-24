from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.tencent_sms_service import SmsPurpose
from scripts.admin_performance_dataset import (
    DATASET_VERSION,
    PERF_OWNER_PHONE,
    PERF_TENANT_ID,
    PERF_TENANT_NAME,
    DatasetSafetyError,
)
from scripts.admin_performance_owner_code import (
    OwnerCodeSafetyError,
    _run_cli,
    main,
    mask_owner_phone,
    seed_owner_login_code,
    validate_owner_code,
)


@pytest.mark.parametrize("value", ["123456", " 123456 ", "\n654321\t"])
def test_validate_owner_code_accepts_exactly_six_ascii_digits(value: str) -> None:
    assert validate_owner_code(value) == value.strip()


@pytest.mark.parametrize(
    "value",
    [None, "", " ", "12345", "1234567", "12a456", "１２３４５６", "123 456"],
)
def test_validate_owner_code_rejects_unsafe_values(value: object) -> None:
    with pytest.raises(OwnerCodeSafetyError, match="exactly 6 digits"):
        validate_owner_code(value)


def test_mask_owner_phone_hides_middle_digits() -> None:
    assert mask_owner_phone("19900000000") == "199****0000"


async def _owner_database(
    *,
    include_tenant: bool = True,
    include_config: bool = True,
    tenant_name: str = PERF_TENANT_NAME,
    phone: str = PERF_OWNER_PHONE,
    marker: object = ...,
):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Tenant.__table__.create(sync_connection)
        )
        await connection.run_sync(
            lambda sync_connection: TenantConfig.__table__.create(sync_connection)
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        if include_tenant:
            session.add(
                Tenant(
                    id=1001,
                    tenant_id=PERF_TENANT_ID,
                    name=tenant_name,
                    password_hash="test-only-hash",
                    phone=phone,
                )
            )
        if include_config:
            performance_marker = (
                {"datasetVersion": DATASET_VERSION, "source": "test"}
                if marker is ...
                else marker
            )
            business_info = (
                {"performanceTest": performance_marker}
                if performance_marker is not None
                else {}
            )
            session.add(
                TenantConfig(
                    id=1002,
                    tenant_id=PERF_TENANT_ID,
                    member_rules={},
                    coupon_rules={},
                    business_info=business_info,
                    plugin_settings={},
                )
            )
    return engine, factory


def test_seed_owner_login_code_stores_code_and_returns_only_safe_report() -> None:
    async def scenario() -> None:
        engine, factory = await _owner_database()
        try:
            with patch(
                "app.services.tencent_sms_service.TencentSmsService.store_login_code",
                new_callable=AsyncMock,
            ) as store_login_code:
                report = await seed_owner_login_code(factory, " 123456 ")

            store_login_code.assert_awaited_once_with(
                PERF_OWNER_PHONE,
                "123456",
                SmsPurpose.LOGIN,
            )
            assert report == {
                "status": "PASS",
                "dataset_version": DATASET_VERSION,
                "tenant_id": PERF_TENANT_ID,
                "phone": "199****0000",
                "purpose": "login",
            }
            serialized = json.dumps(report, sort_keys=True).lower()
            for forbidden in ("123456", "code", "token", "secret", "password"):
                assert forbidden not in serialized
        finally:
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("database_options", "message"),
    [
        ({"include_tenant": False, "include_config": False}, "tenant is missing"),
        ({"include_config": False}, "config is missing"),
        ({"marker": None}, "performance marker"),
        ({"marker": "not-a-dict"}, "performance marker"),
        (
            {"marker": {"datasetVersion": "WRONG", "source": "test"}},
            "performance marker",
        ),
        (
            {"marker": {"datasetVersion": DATASET_VERSION, "source": "business"}},
            "performance marker",
        ),
        ({"tenant_name": "Lookalike tenant"}, "tenant name"),
        ({"phone": "18800000000"}, "owner phone"),
    ],
)
def test_seed_owner_login_code_fails_closed_before_service_call(
    database_options: dict[str, object],
    message: str,
) -> None:
    async def scenario() -> None:
        engine, factory = await _owner_database(**database_options)
        try:
            with patch(
                "app.services.tencent_sms_service.TencentSmsService.store_login_code",
                new_callable=AsyncMock,
            ) as store_login_code:
                with pytest.raises(OwnerCodeSafetyError, match=message):
                    await seed_owner_login_code(factory, "123456")
            store_login_code.assert_not_awaited()
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_run_cli_rejects_test_environment_before_creating_engine(monkeypatch) -> None:
    from app import config

    monkeypatch.setattr(
        config,
        "settings",
        SimpleNamespace(
            APP_ENV="test",
            DATABASE_URL="mysql+asyncmy://user:secret@db/performance_test",
        ),
    )
    monkeypatch.setenv("PERF_DATASET_ACK", DATASET_VERSION)
    monkeypatch.setenv("PERF_OWNER_LOGIN_CODE", "123456")
    with patch("scripts.admin_performance_owner_code.create_async_engine") as create_engine:
        with pytest.raises(OwnerCodeSafetyError, match="staging"):
            asyncio.run(_run_cli())
    create_engine.assert_not_called()


def test_run_cli_reads_process_code_and_disposes_own_engine(monkeypatch) -> None:
    from app import config

    monkeypatch.setattr(
        config,
        "settings",
        SimpleNamespace(
            APP_ENV=" staging ",
            DATABASE_URL="mysql+asyncmy://user:secret@db/performance_staging",
        ),
    )
    monkeypatch.setenv("PERF_DATASET_ACK", DATASET_VERSION)
    monkeypatch.setenv("PERF_OWNER_LOGIN_CODE", " 654321 ")
    engine = SimpleNamespace(dispose=AsyncMock())
    factory = object()
    report = {"status": "PASS"}
    with (
        patch(
            "scripts.admin_performance_owner_code.create_async_engine",
            return_value=engine,
        ) as create_engine,
        patch(
            "scripts.admin_performance_owner_code.async_sessionmaker",
            return_value=factory,
        ),
        patch(
            "scripts.admin_performance_owner_code.seed_owner_login_code",
            new=AsyncMock(return_value=report),
        ) as seed,
    ):
        assert asyncio.run(_run_cli()) == report

    create_engine.assert_called_once_with(
        "mysql+asyncmy://user:secret@db/performance_staging",
        pool_pre_ping=True,
    )
    seed.assert_awaited_once_with(factory, " 654321 ")
    engine.dispose.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_message"),
    [
        (DatasetSafetyError("safe dataset guard"), 2, "safe dataset guard"),
        (OwnerCodeSafetyError("safe owner guard"), 2, "safe owner guard"),
        (RuntimeError("code=123456 database_url=secret"), 1, "owner code operation failed"),
    ],
)
def test_main_emits_safe_json_for_failures(
    capsys,
    failure: Exception,
    expected_status: int,
    expected_message: str,
) -> None:
    with patch(
        "scripts.admin_performance_owner_code._run_cli",
        new=AsyncMock(side_effect=failure),
    ):
        assert main() == expected_status

    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["status"] == "FAIL"
    assert payload["message"] == expected_message
    if expected_status == 1:
        serialized = captured.err.lower()
        for forbidden in ("123456", "code=", "database_url", "secret", "runtimeerror"):
            assert forbidden not in serialized
    assert captured.out == ""


def test_main_emits_safe_json_on_success(capsys) -> None:
    report = {
        "status": "PASS",
        "dataset_version": DATASET_VERSION,
        "tenant_id": PERF_TENANT_ID,
        "phone": "199****0000",
        "purpose": "login",
    }
    with patch(
        "scripts.admin_performance_owner_code._run_cli",
        new=AsyncMock(return_value=report),
    ):
        assert main() == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == report
    assert captured.err == ""
