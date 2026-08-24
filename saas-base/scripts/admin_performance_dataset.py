"""Deterministic admin-h5 performance-test dataset lifecycle.

This module is test infrastructure.  It must never be used against a normal
development or production database.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.security import get_password_hash
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.menu_item import MenuItem
from app.models.merchant_account import MerchantAccount
from app.models.order import Order, OrderItem
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.utils.id_generator import generate_snowflake_id


DATASET_VERSION = "PERF_DATASET_V1"
PERF_TENANT_ID = "perf_test_only_v1"
PERF_TENANT_NAME = "[PERFORMANCE TEST ONLY] PERF_DATASET_V1"
PERF_USERNAME = "perf_operator"
FIXED_ANCHOR = datetime(2026, 1, 1, 12, 0, 0)


class DatasetSafetyError(RuntimeError):
    """Raised before a dataset operation can cross its fixed safety boundary."""


class DatasetVerificationError(RuntimeError):
    """Raised when stored data does not match the dataset contract."""


@dataclass(frozen=True)
class DatasetScale:
    dishes: int
    members: int
    orders: int
    categories: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


DEFAULT_SCALE = DatasetScale(
    dishes=500,
    members=10_000,
    orders=10_000,
    categories=20,
)


ORDER_STATUSES = (
    "pending_payment",
    "pending",
    "preparing",
    "done",
    "settled",
    "rejected",
    "cancelled",
)
MEMBER_LEVELS = (
    ("LV1", "普通会员"),
    ("LV2", "银卡会员"),
    ("LV3", "金卡会员"),
)


def validate_runtime_guard(
    app_env: str,
    database_url: str,
    acknowledgement: str,
) -> tuple[str, str]:
    """Return normalized environment/database only for an approved test target."""

    environment = str(app_env or "").strip().lower()
    if environment not in {"test", "staging"}:
        raise DatasetSafetyError("APP_ENV must be exactly test or staging")
    if acknowledgement != DATASET_VERSION:
        raise DatasetSafetyError("PERF_DATASET_ACK does not match dataset version")
    try:
        database = str(make_url(database_url).database or "")
    except Exception as exc:  # pragma: no cover - SQLAlchemy owns parser details.
        raise DatasetSafetyError("DATABASE_URL is invalid") from exc
    if not database.endswith(("_test", "_staging")):
        raise DatasetSafetyError("database name must end with _test or _staging")
    return environment, database


def _dish_name(index: int) -> str:
    variant = index % 3
    if variant == 0:
        return f"性能菜{index + 1:04d}"
    if variant == 1:
        return f"性能测试菜品-{index + 1:04d}-标准名称"
    suffix = "超长名称" * 6
    return f"性能菜品-{index + 1:04d}-{suffix}"[:64]


def _build_dishes(scale: DatasetScale) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(scale.dishes):
        category_no = index % scale.categories + 1
        state = ("available", "sold_out", "unavailable")[index % 3]
        rows.append(
            {
                "sequence": index + 1,
                "name": _dish_name(index),
                "description": f"PERF_DATASET_V1 菜品描述 {index + 1:04d}",
                "price": f"{8 + index % 193}.00",
                "original_price": f"{10 + index % 211}.00" if index % 4 == 0 else None,
                "category": f"性能分类{category_no:02d}",
                "emoji": "🍽️",
                "available": state != "unavailable",
                "stock": 0 if state == "sold_out" else (None if index % 5 else 100 + index),
                "sort_order": index,
                "image": f"https://perf-assets.invalid/PERF_DATASET_V1/dish-{index + 1:04d}.webp",
                "sales_count": (index * 37) % 5000,
                "tags": "性能测试,大数据" if index % 2 == 0 else "性能测试",
                "availability_state": state,
                "spec_groups": (
                    [
                        {
                            "name": "份量",
                            "type": "single",
                            "required": True,
                            "options": [
                                {"name": "标准", "price_delta": 0},
                                {"name": "加大", "price_delta": 5},
                            ],
                        }
                    ]
                    if index % 4 == 0
                    else []
                ),
            }
        )
    return rows


def _build_customers(scale: DatasetScale) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    customers: list[dict[str, Any]] = []
    accounts: list[dict[str, Any]] = []
    for index in range(scale.members):
        created_at = FIXED_ANCHOR - timedelta(days=index % 730, minutes=index % 1440)
        level_code, level_name = MEMBER_LEVELS[index % len(MEMBER_LEVELS)]
        phone = f"000{index + 1:08d}"
        customers.append(
            {
                "sequence": index + 1,
                "openid": f"perf_v1_customer_{index + 1:05d}",
                "name": f"性能会员{index + 1:05d}" + ("长名称" * (index % 4)),
                "phone": phone,
                "tags": ["performance_test", level_code],
                "status": 0 if index % 17 == 0 else 1,
                "store_member_no": index + 1,
                "created_at": created_at.isoformat(),
                "last_consume_time": (FIXED_ANCHOR - timedelta(days=index % 90)).isoformat(),
            }
        )
        total_consumption = (index * 37) % 200_000
        accounts.append(
            {
                "customer_sequence": index + 1,
                "member_id": f"PERFV1-{index + 1:05d}",
                "level_code": level_code,
                "level_name": level_name,
                "total_consumption": f"{total_consumption}.00",
                "yearly_consumption": f"{total_consumption % 50_000}.00",
                "points_balance": (index * 97) % 100_000,
                "balance": f"{(index * 13) % 10_000}.00",
                "last_consume_time": (FIXED_ANCHOR - timedelta(days=index % 90)).isoformat(),
            }
        )
    return customers, accounts


def _build_orders(scale: DatasetScale) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    orders: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for index in range(scale.orders):
        status = ORDER_STATUSES[index % len(ORDER_STATUSES)]
        created_at = FIXED_ANCHOR - timedelta(days=index % 730, minutes=(index * 7) % 1440)
        item_count = index % 5 + 1
        customer_sequence = index % scale.members + 1 if index % 4 else None
        orders.append(
            {
                "sequence": index + 1,
                "customer_sequence": customer_sequence,
                "table_no": f"P{index % 120 + 1:03d}",
                "total": f"{20 + index % 480}.00",
                "status": status,
                "payment_status": (
                    "unpaid"
                    if status in {"pending_payment", "pending", "rejected", "cancelled"}
                    else "paid"
                ),
                "payment_mode": ("prepay", "postpay", "table_account")[index % 3],
                "payment_method": "mock",
                "payment_time": created_at.isoformat() if status not in {"pending_payment", "pending"} else None,
                "print_status": "SUCCESS",
                "source": "h5",
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
                "item_count": item_count,
            }
        )
        for item_index in range(item_count):
            dish_sequence = (index * 3 + item_index) % scale.dishes + 1
            items.append(
                {
                    "order_sequence": index + 1,
                    "dish_sequence": dish_sequence,
                    "name": f"性能菜{dish_sequence:04d}",
                    "price": f"{8 + (dish_sequence - 1) % 193}.00",
                    "qty": item_index % 3 + 1,
                    "item_remark": "PERF_DATASET_V1" if item_index == 0 else None,
                }
            )
    return orders, items


def build_semantic_dataset(scale: DatasetScale = DEFAULT_SCALE) -> dict[str, Any]:
    if min(scale.dishes, scale.members, scale.orders, scale.categories) <= 0:
        raise ValueError("dataset scale values must be positive")
    if scale.dishes < scale.categories:
        raise ValueError("dish count must be at least category count")
    dishes = _build_dishes(scale)
    customers, member_accounts = _build_customers(scale)
    orders, order_items = _build_orders(scale)
    return {
        "dataset_version": DATASET_VERSION,
        "tenant_id": PERF_TENANT_ID,
        "scale": scale.as_dict(),
        "dishes": dishes,
        "customers": customers,
        "member_accounts": member_accounts,
        "orders": orders,
        "order_items": order_items,
    }


def semantic_checksum(dataset: dict[str, Any]) -> str:
    canonical = json.dumps(dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expected_order_item_count(order_count: int) -> int:
    complete_cycles, remainder = divmod(order_count, 5)
    return complete_cycles * 15 + sum(range(1, remainder + 1))


def _chunks(rows: list[dict[str, Any]], size: int = 1_000):
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def _performance_marker(
    scale: DatasetScale,
    checksum: str,
    environment: str,
) -> dict[str, Any]:
    return {
        "datasetVersion": DATASET_VERSION,
        "source": "test",
        "environment": environment,
        "semanticChecksum": checksum,
        "scale": scale.as_dict(),
    }


def _marker_from_config(config: TenantConfig | None) -> dict[str, Any] | None:
    if config is None or not isinstance(config.business_info, dict):
        return None
    marker = config.business_info.get("performanceTest")
    return marker if isinstance(marker, dict) else None


async def _load_fixed_identity(session: AsyncSession) -> tuple[Tenant | None, TenantConfig | None]:
    tenant = await session.scalar(select(Tenant).where(Tenant.tenant_id == PERF_TENANT_ID))
    config = await session.scalar(select(TenantConfig).where(TenantConfig.tenant_id == PERF_TENANT_ID))
    return tenant, config


def _assert_owned_identity(tenant: Tenant | None, config: TenantConfig | None) -> None:
    if tenant is None:
        if config is not None:
            raise DatasetSafetyError("orphan performance tenant config exists")
        return
    marker = _marker_from_config(config)
    if tenant.name != PERF_TENANT_NAME or marker is None:
        raise DatasetSafetyError("fixed tenant exists without the exact performance marker")
    if marker.get("datasetVersion") != DATASET_VERSION or marker.get("source") != "test":
        raise DatasetSafetyError("performance tenant marker does not match PERF_DATASET_V1")


async def _current_counts(session: AsyncSession) -> dict[str, int]:
    async def count(model, *, tenant_column=True) -> int:
        statement = select(func.count(model.id))
        if tenant_column:
            statement = statement.where(model.tenant_id == PERF_TENANT_ID)
        return int(await session.scalar(statement) or 0)

    order_items = int(
        await session.scalar(
            select(func.count(OrderItem.id)).where(
                OrderItem.order_id.in_(select(Order.id).where(Order.tenant_id == PERF_TENANT_ID))
            )
        )
        or 0
    )
    return {
        "dishes": await count(MenuItem),
        "customers": await count(Customer),
        "member_accounts": await count(MemberAccount),
        "orders": await count(Order),
        "order_items": order_items,
    }


async def _delete_dataset_rows(session: AsyncSession) -> dict[str, int]:
    tenant, config = await _load_fixed_identity(session)
    _assert_owned_identity(tenant, config)
    if tenant is None:
        return {"dishes": 0, "customers": 0, "member_accounts": 0, "orders": 0, "order_items": 0}

    counts = await _current_counts(session)
    order_ids = select(Order.id).where(Order.tenant_id == PERF_TENANT_ID)
    await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    for model in (Order, MemberAccount, Customer, MenuItem, MerchantAccount, Subscription, TenantConfig):
        await session.execute(delete(model).where(model.tenant_id == PERF_TENANT_ID))
    await session.execute(delete(Tenant).where(Tenant.tenant_id == PERF_TENANT_ID))
    await session.flush()
    return counts


async def _insert_rows(session: AsyncSession, model, rows: list[dict[str, Any]]) -> None:
    for batch in _chunks(rows):
        await session.execute(insert(model), batch)


async def _insert_orders(
    session: AsyncSession,
    dataset: dict[str, Any],
    customer_ids: dict[int, int],
    dish_ids: dict[int, int],
) -> None:
    order_ids: dict[int, int] = {}
    order_rows: list[dict[str, Any]] = []
    for row in dataset["orders"]:
        order_id = generate_snowflake_id()
        order_ids[row["sequence"]] = order_id
        customer_sequence = row["customer_sequence"]
        order_rows.append(
            {
                "id": order_id,
                "tenant_id": PERF_TENANT_ID,
                "customer_id": customer_ids.get(customer_sequence) if customer_sequence else None,
                "table_no": row["table_no"],
                "total": Decimal(row["total"]),
                "status": row["status"],
                "payment_status": row["payment_status"],
                "payment_mode": row["payment_mode"],
                "payment_method": row["payment_method"],
                "payment_time": row["payment_time"],
                "print_status": row["print_status"],
                "source": row["source"],
                "created_at": datetime.fromisoformat(row["created_at"]),
                "updated_at": datetime.fromisoformat(row["updated_at"]),
            }
        )
    await _insert_rows(session, Order, order_rows)

    item_rows: list[dict[str, Any]] = []
    for row in dataset["order_items"]:
        item_rows.append(
            {
                "id": generate_snowflake_id(),
                "order_id": order_ids[row["order_sequence"]],
                "dish_id": dish_ids[row["dish_sequence"]],
                "name": row["name"],
                "price": Decimal(row["price"]),
                "qty": row["qty"],
                "item_remark": row["item_remark"],
            }
        )
    await _insert_rows(session, OrderItem, item_rows)


async def _insert_dataset(
    session: AsyncSession,
    dataset: dict[str, Any],
    *,
    password: str,
    scale: DatasetScale,
    environment: str,
) -> None:
    plan = await session.scalar(select(Plan).where(Plan.code == "PRO", Plan.is_active.is_(True)))
    if plan is None:
        raise DatasetSafetyError("active PRO plan is required; global catalog is never created by this tool")

    checksum = semantic_checksum(dataset)
    dish_ids = {row["sequence"]: generate_snowflake_id() for row in dataset["dishes"]}
    customer_ids = {row["sequence"]: generate_snowflake_id() for row in dataset["customers"]}
    specs = {
        str(dish_ids[row["sequence"]]): row["spec_groups"]
        for row in dataset["dishes"]
        if row["spec_groups"]
    }
    session.add(
        Tenant(
            id=generate_snowflake_id(),
            tenant_id=PERF_TENANT_ID,
            name=PERF_TENANT_NAME,
            password_hash=get_password_hash(password),
            phone="00000000000",
            status=True,
            is_open=True,
            payment_mode="postpay",
            wx_pay_enabled=False,
            payment_locked=True,
        )
    )
    session.add(
        TenantConfig(
            id=generate_snowflake_id(),
            tenant_id=PERF_TENANT_ID,
            member_rules={},
            coupon_rules={},
            business_info={
                "performanceTest": _performance_marker(scale, checksum, environment),
                "menu_item_specs": specs,
            },
            plugin_settings={},
        )
    )
    session.add(
        MerchantAccount(
            id=generate_snowflake_id(),
            tenant_id=PERF_TENANT_ID,
            name="Performance Operator",
            username=PERF_USERNAME,
            password_hash=get_password_hash(password),
            role="frontdesk",
            status="active",
        )
    )
    session.add(
        Subscription(
            id=generate_snowflake_id(),
            tenant_id=PERF_TENANT_ID,
            plan_id=plan.id,
            status="TRIAL",
            trial_started_at=datetime(2025, 1, 1),
            trial_ends_at=datetime(2035, 1, 1),
        )
    )

    dish_rows = []
    for row in dataset["dishes"]:
        dish_rows.append(
            {
                "id": dish_ids[row["sequence"]],
                "tenant_id": PERF_TENANT_ID,
                "name": row["name"],
                "description": row["description"],
                "price": Decimal(row["price"]),
                "category": row["category"],
                "emoji": row["emoji"],
                "available": row["available"],
                "sort_order": row["sort_order"],
                "image": row["image"],
                "sales_count": row["sales_count"],
                "tags": row["tags"],
                "original_price": Decimal(row["original_price"]) if row["original_price"] else None,
                "stock": row["stock"],
                "created_at": FIXED_ANCHOR,
                "updated_at": FIXED_ANCHOR,
            }
        )
    await _insert_rows(session, MenuItem, dish_rows)

    customer_rows = []
    for row in dataset["customers"]:
        customer_rows.append(
            {
                "id": customer_ids[row["sequence"]],
                "tenant_id": PERF_TENANT_ID,
                "openid": row["openid"],
                "name": row["name"],
                "phone": row["phone"],
                "tags": row["tags"],
                "status": row["status"],
                "store_member_no": row["store_member_no"],
                "last_consume_time": datetime.fromisoformat(row["last_consume_time"]),
                "created_at": datetime.fromisoformat(row["created_at"]),
                "updated_at": FIXED_ANCHOR,
            }
        )
    await _insert_rows(session, Customer, customer_rows)

    account_rows = []
    for row in dataset["member_accounts"]:
        account_rows.append(
            {
                "id": generate_snowflake_id(),
                "tenant_id": PERF_TENANT_ID,
                "customer_id": customer_ids[row["customer_sequence"]],
                "member_id": row["member_id"],
                "level_code": row["level_code"],
                "level_name": row["level_name"],
                "total_consumption": Decimal(row["total_consumption"]),
                "yearly_consumption": Decimal(row["yearly_consumption"]),
                "points_balance": row["points_balance"],
                "balance": Decimal(row["balance"]),
                "last_consume_time": datetime.fromisoformat(row["last_consume_time"]),
                "level_checked_at": FIXED_ANCHOR,
                "created_at": FIXED_ANCHOR,
                "updated_at": FIXED_ANCHOR,
            }
        )
    await _insert_rows(session, MemberAccount, account_rows)
    await _insert_orders(session, dataset, customer_ids, dish_ids)
    await session.flush()


async def _verify_in_session(
    session: AsyncSession,
    *,
    scale: DatasetScale,
) -> dict[str, Any]:
    tenant, config = await _load_fixed_identity(session)
    _assert_owned_identity(tenant, config)
    if tenant is None:
        raise DatasetVerificationError("performance tenant does not exist")
    marker = _marker_from_config(config) or {}
    expected_dataset = build_semantic_dataset(scale)
    expected_checksum = semantic_checksum(expected_dataset)
    counts = await _current_counts(session)
    expected_counts = {
        "dishes": scale.dishes,
        "customers": scale.members,
        "member_accounts": scale.members,
        "orders": scale.orders,
        "order_items": expected_order_item_count(scale.orders),
    }
    if counts != expected_counts:
        raise DatasetVerificationError(f"dataset counts mismatch: {counts}")
    if marker.get("semanticChecksum") != expected_checksum or marker.get("scale") != scale.as_dict():
        raise DatasetVerificationError("dataset marker checksum or scale mismatch")

    category_count = int(
        await session.scalar(
            select(func.count(func.distinct(MenuItem.category))).where(MenuItem.tenant_id == PERF_TENANT_ID)
        )
        or 0
    )
    statuses = set(
        (
            await session.execute(select(Order.status).where(Order.tenant_id == PERF_TENANT_ID).distinct())
        ).scalars()
    )
    levels = set(
        (
            await session.execute(
                select(MemberAccount.level_code).where(MemberAccount.tenant_id == PERF_TENANT_ID).distinct()
            )
        ).scalars()
    )
    unsafe_prints = int(
        await session.scalar(
            select(func.count(Order.id)).where(
                Order.tenant_id == PERF_TENANT_ID,
                Order.print_status != "SUCCESS",
            )
        )
        or 0
    )
    account_count = int(
        await session.scalar(
            select(func.count(MerchantAccount.id)).where(
                MerchantAccount.tenant_id == PERF_TENANT_ID,
                MerchantAccount.username == PERF_USERNAME,
                MerchantAccount.status == "active",
            )
        )
        or 0
    )
    subscription_count = int(
        await session.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.tenant_id == PERF_TENANT_ID,
                Subscription.status.in_(["TRIAL", "ACTIVE"]),
            )
        )
        or 0
    )
    orphan_member_count = int(
        await session.scalar(
            select(func.count(MemberAccount.id))
            .outerjoin(
                Customer,
                (Customer.id == MemberAccount.customer_id)
                & (Customer.tenant_id == PERF_TENANT_ID),
            )
            .where(
                MemberAccount.tenant_id == PERF_TENANT_ID,
                Customer.id.is_(None),
            )
        )
        or 0
    )
    dish_ids = set(
        (
            await session.execute(
                select(MenuItem.id).where(MenuItem.tenant_id == PERF_TENANT_ID)
            )
        ).scalars()
    )
    stored_specs = (config.business_info or {}).get("menu_item_specs", {})
    expected_spec_count = sum(1 for dish in expected_dataset["dishes"] if dish["spec_groups"])
    try:
        spec_dish_ids = {int(dish_id) for dish_id in stored_specs}
    except (TypeError, ValueError):
        spec_dish_ids = set()
    if category_count != scale.categories:
        raise DatasetVerificationError("dish category coverage mismatch")
    if statuses != set(ORDER_STATUSES):
        raise DatasetVerificationError("order status coverage mismatch")
    if levels != {item[0] for item in MEMBER_LEVELS}:
        raise DatasetVerificationError("member level coverage mismatch")
    if unsafe_prints:
        raise DatasetVerificationError("non-success print status found")
    if account_count != 1 or subscription_count != 1:
        raise DatasetVerificationError("login account or active subscription missing")
    if orphan_member_count:
        raise DatasetVerificationError("member account relationship mismatch")
    if len(stored_specs) != expected_spec_count or not spec_dish_ids.issubset(dish_ids):
        raise DatasetVerificationError("menu item specification coverage mismatch")
    return {
        "status": "PASS",
        "dataset_version": DATASET_VERSION,
        "tenant_id": PERF_TENANT_ID,
        "counts": counts,
        "dataset_scale": scale.as_dict(),
        "semantic_checksum": expected_checksum,
        "category_count": category_count,
        "order_statuses": sorted(statuses),
        "member_levels": sorted(levels),
        "invalid_print_statuses": unsafe_prints,
        "orphan_member_accounts": orphan_member_count,
        "menu_item_spec_count": len(stored_specs),
    }


async def create_dataset(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    password: str,
    scale: DatasetScale = DEFAULT_SCALE,
    environment: str = "test",
) -> dict[str, Any]:
    if not str(password or "").strip():
        raise DatasetSafetyError("PERF_TEST_PASSWORD is required")
    dataset = build_semantic_dataset(scale)
    async with session_factory() as session:
        async with session.begin():
            tenant, config = await _load_fixed_identity(session)
            _assert_owned_identity(tenant, config)
            if tenant is not None:
                await _delete_dataset_rows(session)
            await _insert_dataset(
                session,
                dataset,
                password=password,
                scale=scale,
                environment=environment,
            )
            report = await _verify_in_session(session, scale=scale)
    return report


async def verify_dataset(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    scale: DatasetScale = DEFAULT_SCALE,
) -> dict[str, Any]:
    async with session_factory() as session:
        return await _verify_in_session(session, scale=scale)


async def cleanup_dataset(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    async with session_factory() as session:
        async with session.begin():
            tenant, config = await _load_fixed_identity(session)
            _assert_owned_identity(tenant, config)
            if tenant is None:
                return {
                    "status": "PASS",
                    "dataset_version": DATASET_VERSION,
                    "tenant_id": PERF_TENANT_ID,
                    "deleted": {"dishes": 0, "customers": 0, "member_accounts": 0, "orders": 0, "order_items": 0},
                }
            deleted_counts = await _delete_dataset_rows(session)
    return {
        "status": "PASS",
        "dataset_version": DATASET_VERSION,
        "tenant_id": PERF_TENANT_ID,
        "deleted": deleted_counts,
    }


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, verify, or clean the fixed admin performance-test dataset."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("create", "verify", "cleanup"):
        command = subparsers.add_parser(action)
        command.add_argument("--dataset-version", required=True)
        if action == "create":
            command.add_argument("--manifest-out", required=True)
        elif action == "verify":
            command.add_argument("--manifest-out")
    return parser


def build_manifest(
    report: dict[str, Any],
    *,
    environment: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    generated = created_at or datetime.now(timezone.utc)
    if generated.tzinfo is not None:
        generated = generated.astimezone(timezone.utc).replace(tzinfo=None)
    return {
        "dataset_version": report["dataset_version"],
        "tenant_id": report["tenant_id"],
        "created_at": generated.isoformat(timespec="seconds") + "Z",
        "source": "test",
        "environment": environment,
        "dataset_scale": dict(report.get("dataset_scale") or {}),
        "counts": dict(report.get("counts") or {}),
        "semantic_checksum": report.get("semantic_checksum"),
        "status": report.get("status"),
    }


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    if args.dataset_version != DATASET_VERSION:
        raise DatasetSafetyError("--dataset-version must be PERF_DATASET_V1")

    from app.config import settings

    environment, _database = validate_runtime_guard(
        settings.APP_ENV,
        settings.DATABASE_URL,
        os.getenv("PERF_DATASET_ACK", ""),
    )
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if args.action == "create":
            password = os.getenv("PERF_TEST_PASSWORD", "")
            report = await create_dataset(
                session_factory,
                password=password,
                environment=environment,
            )
            write_manifest(args.manifest_out, build_manifest(report, environment=environment))
        elif args.action == "verify":
            report = await verify_dataset(session_factory)
            if args.manifest_out:
                write_manifest(args.manifest_out, build_manifest(report, environment=environment))
        elif args.action == "cleanup":
            report = await cleanup_dataset(session_factory)
        else:  # argparse constrains this; keep the lifecycle fail closed.
            raise DatasetSafetyError("unsupported action")
        return report
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = build_cli_parser()
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(_run_cli(args))
    except (DatasetSafetyError, DatasetVerificationError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error_type": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error_type": type(exc).__name__, "message": "dataset operation failed"},
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
