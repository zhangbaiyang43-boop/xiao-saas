"""One-time manual repair for missing entrance_code columns.

This script is intentionally not imported by application startup code.
Run manually on production only after a full saas_base backup has been verified.
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import async_engine


EXPECTED_DATABASE = "saas_base"
TABLE_NAME = "entrance_code"
EXPECTED_COUNT = 24


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    definition: str
    expected_type: str
    expected_nullable: str
    expected_default: str | None


COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec(
        name="entry_type",
        definition="VARCHAR(16) NOT NULL DEFAULT 'table'",
        expected_type="varchar(16)",
        expected_nullable="NO",
        expected_default="table",
    ),
    ColumnSpec(
        name="order_mode",
        definition="VARCHAR(16) NOT NULL DEFAULT 'dine_in'",
        expected_type="varchar(16)",
        expected_nullable="NO",
        expected_default="dine_in",
    ),
    ColumnSpec(
        name="table_id",
        definition="BIGINT NULL DEFAULT NULL",
        expected_type="bigint",
        expected_nullable="YES",
        expected_default=None,
    ),
    ColumnSpec(
        name="target_page",
        definition="VARCHAR(128) NOT NULL DEFAULT 'pages/order/index'",
        expected_type="varchar(128)",
        expected_nullable="NO",
        expected_default="pages/order/index",
    ),
)


def log(message: str) -> None:
    print(f"[entrance_code_repair] {message}", flush=True)


async def current_database(conn) -> str:
    database = (await conn.execute(text("SELECT DATABASE()"))).scalar()
    if database != EXPECTED_DATABASE:
        raise RuntimeError(
            f"Refusing to run: connected database is {database!r}, expected {EXPECTED_DATABASE!r}"
        )
    return database


async def table_exists(conn) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
            """
        ),
        {"table_name": TABLE_NAME},
    )
    return int(result.scalar() or 0) == 1


async def entrance_code_count(conn) -> int:
    return int((await conn.execute(text("SELECT COUNT(*) FROM entrance_code"))).scalar() or 0)


async def column_info(conn, column_name: str) -> dict | None:
    result = await conn.execute(
        text(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": TABLE_NAME, "column_name": column_name},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def all_target_column_info(conn) -> list[dict]:
    result = await conn.execute(
        text(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND column_name IN ('entry_type', 'order_mode', 'table_id', 'target_page')
            ORDER BY FIELD(column_name, 'entry_type', 'order_mode', 'table_id', 'target_page')
            """
        ),
        {"table_name": TABLE_NAME},
    )
    return [dict(row) for row in result.mappings().all()]


def normalize_mysql_type(column_type: str) -> str:
    value = str(column_type).lower()
    if value.startswith("bigint"):
        return "bigint"
    return value


def validate_column(spec: ColumnSpec, info: dict | None) -> None:
    if not info:
        raise RuntimeError(f"Column {spec.name} was not found after repair")

    actual_type = normalize_mysql_type(info["COLUMN_TYPE"])
    actual_nullable = str(info["IS_NULLABLE"]).upper()
    actual_default = info["COLUMN_DEFAULT"]

    if actual_type != spec.expected_type:
        raise RuntimeError(f"{spec.name} type mismatch: {actual_type!r} != {spec.expected_type!r}")
    if actual_nullable != spec.expected_nullable:
        raise RuntimeError(
            f"{spec.name} nullable mismatch: {actual_nullable!r} != {spec.expected_nullable!r}"
        )
    if actual_default != spec.expected_default:
        raise RuntimeError(
            f"{spec.name} default mismatch: {actual_default!r} != {spec.expected_default!r}"
        )


async def add_column_if_missing(conn, spec: ColumnSpec) -> None:
    existing = await column_info(conn, spec.name)
    if existing:
        log(f"column {spec.name} exists, skip")
        validate_column(spec, existing)
        return

    log(f"column {spec.name} missing, adding")
    await conn.execute(text(f"ALTER TABLE entrance_code ADD COLUMN {spec.name} {spec.definition}"))

    repaired = await column_info(conn, spec.name)
    validate_column(spec, repaired)
    log(f"column {spec.name} added and verified")


async def verify_default_values(conn) -> None:
    result = await conn.execute(
        text(
            """
            SELECT
                COUNT(*) AS total_rows,
                SUM(CASE WHEN entry_type = 'table' THEN 1 ELSE 0 END) AS entry_type_ok,
                SUM(CASE WHEN order_mode = 'dine_in' THEN 1 ELSE 0 END) AS order_mode_ok,
                SUM(CASE WHEN target_page = 'pages/order/index' THEN 1 ELSE 0 END) AS target_page_ok
            FROM entrance_code
            """
        )
    )
    row = result.mappings().one()
    total = int(row["total_rows"] or 0)
    if total != EXPECTED_COUNT:
        raise RuntimeError(f"Unexpected entrance_code count during default check: {total}")

    for field in ("entry_type", "order_mode", "target_page"):
        ok_count = int(row[f"{field}_ok"] or 0)
        if ok_count != total:
            raise RuntimeError(f"Default value check failed for {field}: {ok_count}/{total}")

    log(
        "default value sample check ok: "
        "entry_type='table', order_mode='dine_in', target_page='pages/order/index'"
    )


async def repair() -> None:
    async with async_engine.begin() as conn:
        database = await current_database(conn)
        log(f"database={database}")

        if not await table_exists(conn):
            raise RuntimeError("Refusing to run: entrance_code table does not exist")

        before_count = await entrance_code_count(conn)
        log(f"entrance_code count before={before_count}")
        if before_count != EXPECTED_COUNT:
            raise RuntimeError(
                f"Refusing to run: entrance_code count is {before_count}, expected {EXPECTED_COUNT}"
            )

        for spec in COLUMNS:
            await add_column_if_missing(conn, spec)

        after_database = await current_database(conn)
        after_count = await entrance_code_count(conn)
        log(f"database_after={after_database}")
        log(f"entrance_code count after={after_count}")

        if after_count != before_count:
            raise RuntimeError(
                f"Record count changed unexpectedly: before={before_count}, after={after_count}"
            )

        log("target column definitions:")
        infos = await all_target_column_info(conn)
        by_name = {info["COLUMN_NAME"]: info for info in infos}
        for spec in COLUMNS:
            info = by_name.get(spec.name)
            validate_column(spec, info)
            log(
                f"  {spec.name}: {info['COLUMN_TYPE']} "
                f"nullable={info['IS_NULLABLE']} default={info['COLUMN_DEFAULT']!r}"
            )

        await verify_default_values(conn)
        log("repair completed successfully")


def main() -> int:
    try:
        asyncio.run(repair())
        return 0
    except Exception as exc:
        log(f"FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())



