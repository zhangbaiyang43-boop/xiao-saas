from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.customer import Customer
from app.models.dining import DiningParticipant, DiningSession  # noqa: F401 - FK metadata
from app.models.member_account import MemberAccount
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.subscription import Plan
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig

from scripts.admin_performance_dataset import (
    DATASET_VERSION,
    DEFAULT_SCALE,
    PERF_OWNER_PHONE,
    PERF_TENANT_ID,
    DatasetSafetyError,
    DatasetScale,
    DatasetVerificationError,
    build_cli_parser,
    build_manifest,
    build_semantic_dataset,
    cleanup_dataset,
    create_dataset,
    expected_order_item_count,
    semantic_checksum,
    validate_runtime_guard,
    verify_dataset,
    write_manifest,
)


SMALL_SCALE = DatasetScale(dishes=21, members=12, orders=14, categories=3)


def test_dataset_identity_is_fixed() -> None:
    assert DATASET_VERSION == "PERF_DATASET_V1"
    assert PERF_TENANT_ID == "perf_test_only_v1"
    assert PERF_OWNER_PHONE == "19900000000"
    assert len(PERF_OWNER_PHONE) == 11
    assert PERF_OWNER_PHONE[:2] in {f"1{digit}" for digit in range(3, 10)}


@pytest.mark.parametrize("app_env", ["production", "development", "local", "", "unknown"])
def test_runtime_guard_rejects_non_test_environments(app_env: str) -> None:
    with pytest.raises(DatasetSafetyError):
        validate_runtime_guard(
            app_env,
            "mysql+asyncmy://user:secret@db/performance_test",
            DATASET_VERSION,
        )


def test_runtime_guard_rejects_wrong_database_and_acknowledgement() -> None:
    with pytest.raises(DatasetSafetyError):
        validate_runtime_guard(
            "test",
            "mysql+asyncmy://user:secret@db/business",
            DATASET_VERSION,
        )
    with pytest.raises(DatasetSafetyError):
        validate_runtime_guard(
            "staging",
            "mysql+asyncmy://user:secret@db/performance_staging",
            "wrong-version",
        )


def test_runtime_guard_accepts_only_test_or_staging_database() -> None:
    assert validate_runtime_guard(
        "test",
        "mysql+asyncmy://user:secret@db/performance_test",
        DATASET_VERSION,
    ) == ("test", "performance_test")
    assert validate_runtime_guard(
        "staging",
        "mysql+asyncmy://user:secret@db/performance_staging",
        DATASET_VERSION,
    ) == ("staging", "performance_staging")


def test_semantic_dataset_is_reproducible_and_covers_required_states() -> None:
    first = build_semantic_dataset(SMALL_SCALE)
    second = build_semantic_dataset(SMALL_SCALE)

    assert first == second
    assert semantic_checksum(first) == semantic_checksum(second)
    assert len(first["dishes"]) == 21
    assert len(first["customers"]) == 12
    assert len(first["member_accounts"]) == 12
    assert len(first["orders"]) == 14
    assert {row["category"] for row in first["dishes"]} == {
        "性能分类01",
        "性能分类02",
        "性能分类03",
    }
    assert {row["availability_state"] for row in first["dishes"]} == {
        "available",
        "sold_out",
        "unavailable",
    }
    assert {row["status"] for row in first["orders"]} == {
        "pending_payment",
        "pending",
        "preparing",
        "done",
        "settled",
        "rejected",
        "cancelled",
    }
    assert all(row["print_status"] == "SUCCESS" for row in first["orders"])
    assert all(row["payment_method"] == "mock" for row in first["orders"])


def test_semantic_checksum_excludes_runtime_and_secret_fields() -> None:
    dataset = build_semantic_dataset(SMALL_SCALE)
    checksum = semantic_checksum(dataset)
    text = repr(dataset)

    assert len(checksum) == 64
    assert "password" not in text.lower()
    assert "token" not in text.lower()
    assert "cookie" not in text.lower()
    assert "database_url" not in text.lower()


async def _database_with_control_tenant(*, fixed_unmarked: bool = False):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add(
            Plan(
                id=901,
                code="PRO",
                name="Pro",
                is_active=True,
                price_month_cents=0,
                price_year_cents=0,
            )
        )
        session.add(
            Tenant(
                id=902,
                tenant_id="production-control",
                name="Production control",
                password_hash="control",
                phone="control-phone",
            )
        )
        session.add(
            TenantConfig(
                id=903,
                tenant_id="production-control",
                member_rules={},
                coupon_rules={},
                business_info={"control": True},
                plugin_settings={},
            )
        )
        session.add(
            MenuItem(
                id=904,
                tenant_id="production-control",
                name="Control dish",
                description="must survive",
                price="1.00",
                category="Control",
            )
        )
        if fixed_unmarked:
            session.add(
                Tenant(
                    id=905,
                    tenant_id=PERF_TENANT_ID,
                    name="Existing business tenant",
                    password_hash="do-not-touch",
                    phone="existing-phone",
                )
            )
            session.add(
                TenantConfig(
                    id=906,
                    tenant_id=PERF_TENANT_ID,
                    member_rules={},
                    coupon_rules={},
                    business_info={"business": True},
                    plugin_settings={},
                )
            )
    return engine, factory


def test_dataset_lifecycle_is_repeatable_isolated_and_cleanable() -> None:
    async def scenario() -> None:
        engine, factory = await _database_with_control_tenant()
        try:
            first = await create_dataset(factory, password="test-only-password", scale=SMALL_SCALE)
            verified = await verify_dataset(factory, scale=SMALL_SCALE)
            second = await create_dataset(factory, password="test-only-password", scale=SMALL_SCALE)

            assert first["status"] == "PASS"
            assert verified["status"] == "PASS"
            assert second["semantic_checksum"] == first["semantic_checksum"]
            assert verified["counts"] == {
                "dishes": 21,
                "customers": 12,
                "member_accounts": 12,
                "orders": 14,
                "order_items": expected_order_item_count(14),
            }

            async with factory() as session:
                tenant = await session.scalar(select(Tenant).where(Tenant.tenant_id == PERF_TENANT_ID))
                assert tenant is not None
                assert tenant.phone == PERF_OWNER_PHONE

            cleanup = await cleanup_dataset(factory)
            assert cleanup["status"] == "PASS"
            async with factory() as session:
                assert await session.scalar(
                    select(func.count(Tenant.id)).where(Tenant.tenant_id == "production-control")
                ) == 1
                assert await session.scalar(
                    select(func.count(MenuItem.id)).where(MenuItem.tenant_id == "production-control")
                ) == 1
                assert await session.scalar(
                    select(func.count(Tenant.id)).where(Tenant.tenant_id == PERF_TENANT_ID)
                ) == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_default_contract_scale_can_be_created_verified_recreated_and_cleaned() -> None:
    async def scenario() -> None:
        engine, factory = await _database_with_control_tenant()
        try:
            first = await create_dataset(factory, password="test-only-password")
            verified = await verify_dataset(factory)
            second = await create_dataset(factory, password="test-only-password")

            expected_counts = {
                "dishes": 500,
                "customers": 10_000,
                "member_accounts": 10_000,
                "orders": 10_000,
                "order_items": expected_order_item_count(10_000),
            }
            assert DEFAULT_SCALE.as_dict() == {
                "dishes": 500,
                "members": 10_000,
                "orders": 10_000,
                "categories": 20,
            }
            assert first["counts"] == expected_counts
            assert verified["counts"] == expected_counts
            assert verified["menu_item_spec_count"] == 125
            assert second["semantic_checksum"] == first["semantic_checksum"]

            cleanup = await cleanup_dataset(factory)
            assert cleanup["status"] == "PASS"
            async with factory() as session:
                assert await session.scalar(
                    select(func.count(Tenant.id)).where(Tenant.tenant_id == "production-control")
                ) == 1
                assert await session.scalar(
                    select(func.count(Tenant.id)).where(Tenant.tenant_id == PERF_TENANT_ID)
                ) == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_unmarked_fixed_tenant_is_never_adopted_or_deleted() -> None:
    async def scenario() -> None:
        engine, factory = await _database_with_control_tenant(fixed_unmarked=True)
        try:
            with pytest.raises(DatasetSafetyError):
                await create_dataset(factory, password="test-only-password", scale=SMALL_SCALE)
            with pytest.raises(DatasetSafetyError):
                await cleanup_dataset(factory)
            async with factory() as session:
                tenant = await session.scalar(select(Tenant).where(Tenant.tenant_id == PERF_TENANT_ID))
                assert tenant is not None
                assert tenant.name == "Existing business tenant"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_verify_detects_print_status_corruption() -> None:
    async def scenario() -> None:
        engine, factory = await _database_with_control_tenant()
        try:
            await create_dataset(factory, password="test-only-password", scale=SMALL_SCALE)
            async with factory() as session, session.begin():
                await session.execute(
                    update(Order)
                    .where(Order.tenant_id == PERF_TENANT_ID)
                    .values(print_status="FAILED")
                )
            with pytest.raises(DatasetVerificationError):
                await verify_dataset(factory, scale=SMALL_SCALE)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_verify_detects_member_relationship_and_spec_corruption() -> None:
    async def scenario() -> None:
        engine, factory = await _database_with_control_tenant()
        try:
            await create_dataset(factory, password="test-only-password", scale=SMALL_SCALE)
            async with factory() as session, session.begin():
                account_id = await session.scalar(
                    select(MemberAccount.id).where(MemberAccount.tenant_id == PERF_TENANT_ID).limit(1)
                )
                await session.execute(
                    update(MemberAccount)
                    .where(MemberAccount.id == account_id)
                    .values(customer_id=999_999_999)
                )
            with pytest.raises(DatasetVerificationError):
                await verify_dataset(factory, scale=SMALL_SCALE)

            await create_dataset(factory, password="test-only-password", scale=SMALL_SCALE)
            async with factory() as session, session.begin():
                config = await session.scalar(
                    select(TenantConfig).where(TenantConfig.tenant_id == PERF_TENANT_ID)
                )
                config.business_info = {
                    **config.business_info,
                    "menu_item_specs": {},
                }
            with pytest.raises(DatasetVerificationError):
                await verify_dataset(factory, scale=SMALL_SCALE)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_failed_recreate_rolls_back_to_previous_dataset() -> None:
    async def scenario() -> None:
        engine, factory = await _database_with_control_tenant()
        try:
            before = await create_dataset(factory, password="test-only-password", scale=SMALL_SCALE)
            with patch(
                "scripts.admin_performance_dataset._insert_orders",
                side_effect=RuntimeError("forced insert failure"),
            ):
                with pytest.raises(RuntimeError, match="forced insert failure"):
                    await create_dataset(factory, password="test-only-password", scale=SMALL_SCALE)
            after = await verify_dataset(factory, scale=SMALL_SCALE)
            assert after["semantic_checksum"] == before["semantic_checksum"]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_cli_exposes_only_create_verify_cleanup_and_requires_dataset_version() -> None:
    parser = build_cli_parser()
    create = parser.parse_args(
        [
            "create",
            "--dataset-version",
            DATASET_VERSION,
            "--manifest-out",
            "manifest.json",
        ]
    )
    verify = parser.parse_args(["verify", "--dataset-version", DATASET_VERSION])
    cleanup = parser.parse_args(["cleanup", "--dataset-version", DATASET_VERSION])

    assert create.action == "create"
    assert create.manifest_out == "manifest.json"
    assert verify.action == "verify"
    assert verify.manifest_out is None
    assert cleanup.action == "cleanup"
    with pytest.raises(SystemExit):
        parser.parse_args(["create", "--manifest-out", "manifest.json"])
    with pytest.raises(SystemExit):
        parser.parse_args(["unknown", "--dataset-version", DATASET_VERSION])


def test_manifest_is_atomic_machine_readable_and_contains_no_secrets(tmp_path) -> None:
    dataset = build_semantic_dataset(SMALL_SCALE)
    report = {
        "status": "PASS",
        "dataset_version": DATASET_VERSION,
        "tenant_id": PERF_TENANT_ID,
        "counts": {
            "dishes": 21,
            "customers": 12,
            "member_accounts": 12,
            "orders": 14,
            "order_items": expected_order_item_count(14),
        },
        "dataset_scale": SMALL_SCALE.as_dict(),
        "semantic_checksum": semantic_checksum(dataset),
    }
    manifest = build_manifest(
        report,
        environment="test",
        created_at=datetime(2026, 8, 24, 14, 0, 0),
    )
    target = tmp_path / "nested" / "PERF_DATASET_V1.json"
    write_manifest(target, manifest)
    stored = json.loads(target.read_text(encoding="utf-8"))
    serialized = json.dumps(stored, ensure_ascii=False).lower()

    assert stored["dataset_version"] == DATASET_VERSION
    assert stored["tenant_id"] == PERF_TENANT_ID
    assert stored["environment"] == "test"
    assert stored["source"] == "test"
    assert stored["created_at"] == "2026-08-24T14:00:00Z"
    assert stored["dataset_scale"] == SMALL_SCALE.as_dict()
    assert not list(target.parent.glob("*.tmp"))
    for forbidden in ("password", "password_hash", "token", "cookie", "database_url", "secret"):
        assert forbidden not in serialized
