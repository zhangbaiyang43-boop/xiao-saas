from sqlalchemy import text

from app.core.logger import logger


BIGINT__TABLES = (
    "tenant",
    "customer",
    "coupon_template",
    "coupon",
    "consumption",
    "customer_identity",
    "member_account",
    "point_ledger",
    "benefit_template",
    "tenant_plugin",
    "wework_event_log",
    "wework_contact_way",
    "commission_record",
)


async def ensure_bigint_ids(conn) -> None:
    """Repair old half-created MySQL tables whose snowflake id column is INT."""
    dialect = conn.dialect.name
    if dialect not in {"mysql", "mariadb"}:
        return

    for table_name in BIGINT__TABLES:
        result = await conn.execute(
            text(
                """
                SELECT DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = :table_name
                  AND COLUMN_NAME = 'id'
                """
            ),
            {"table_name": table_name},
        )
        row = result.first()
        if not row or str(row[0]).lower() == "bigint":
            continue

        logger.warning("Repairing %s.id from %s to BIGINT", table_name, row[0])
        await conn.execute(text(f"ALTER TABLE `{table_name}` MODIFY COLUMN `id` BIGINT NOT NULL"))


async def ensure_coupon_template_description(conn) -> None:
    """Add coupon_template.description for old databases created before the field existed."""
    dialect = conn.dialect.name
    if dialect not in {"mysql", "mariadb"}:
        return

    result = await conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'coupon_template'
              AND COLUMN_NAME = 'description'
            """
        )
    )
    exists = int(result.scalar() or 0) > 0
    if exists:
        return

    logger.warning("Repairing coupon_template: adding missing description column")
    await conn.execute(text("ALTER TABLE `coupon_template` ADD COLUMN `description` TEXT NULL"))


async def _mysql_column_exists(conn, table_name: str, column_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return int(result.scalar() or 0) > 0


async def _sqlite_column_exists(conn, table_name: str, column_name: str) -> bool:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    return any(str(row[1]) == column_name for row in result.fetchall())


async def ensure_tenant_schema(conn) -> None:
    """Add legacy tenant columns required by current runtime models."""
    dialect = conn.dialect.name
    tenant_columns = (
        ("is_open", "BOOLEAN NOT NULL DEFAULT 1"),
        ("wx_pay_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("wx_mchid", "VARCHAR(64) NULL"),
        ("wx_api_key_v3", "VARCHAR(256) NULL"),
        ("wx_cert_serial", "VARCHAR(128) NULL"),
        ("wx_private_key", "VARCHAR(4096) NULL"),
        ("receiver_name", "VARCHAR(128) NULL"),
        ("receiver_type", "VARCHAR(32) NULL"),
        ("receiver_verified", "BOOLEAN NOT NULL DEFAULT 0"),
        ("payment_locked", "BOOLEAN NOT NULL DEFAULT 1"),
        ("verified_time", "DATETIME NULL"),
        ("feieyun_sn", "VARCHAR(64) NULL"),
        ("feieyun_key", "VARCHAR(64) NULL"),
    )

    if dialect in {"mysql", "mariadb"}:
        for column_name, definition in tenant_columns:
            if await _mysql_column_exists(conn, "tenant", column_name):
                continue
            logger.warning("Repairing tenant: adding missing %s column", column_name)
            await conn.execute(text(f"ALTER TABLE `tenant` ADD COLUMN `{column_name}` {definition}"))
        return

    if dialect == "sqlite":
        for column_name, definition in tenant_columns:
            if await _sqlite_column_exists(conn, "tenant", column_name):
                continue
            logger.warning("Repairing tenant: adding missing %s column", column_name)
            await conn.execute(text(f"ALTER TABLE tenant ADD COLUMN {column_name} {definition}"))


async def ensure_queue_ticket_schema(conn) -> None:
    """Add legacy queue_tickets columns required by current runtime models."""
    dialect = conn.dialect.name

    if dialect in {"mysql", "mariadb"}:
        result = await conn.execute(text("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'queue_tickets'"))
        if int(result.scalar() or 0) == 0:
            return
        if not await _mysql_column_exists(conn, "queue_tickets", "query_token"):
            logger.warning("Repairing queue_tickets: adding missing query_token column")
            await conn.execute(text("ALTER TABLE `queue_tickets` ADD COLUMN `query_token` VARCHAR(64) NULL"))
        if not await _mysql_column_exists(conn, "queue_tickets", "openid"):
            logger.warning("Repairing queue_tickets: adding missing openid column")
            await conn.execute(text("ALTER TABLE `queue_tickets` ADD COLUMN `openid` VARCHAR(64) NULL"))
        if not await _mysql_column_exists(conn, "queue_tickets", "customer_id"):
            logger.warning("Repairing queue_tickets: adding missing customer_id column")
            await conn.execute(text("ALTER TABLE `queue_tickets` ADD COLUMN `customer_id` BIGINT NULL"))
        return

    if dialect == "sqlite":
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='queue_tickets'"))
        if not result.first():
            return
        if not await _sqlite_column_exists(conn, "queue_tickets", "query_token"):
            logger.warning("Repairing queue_tickets: adding missing query_token column")
            await conn.execute(text("ALTER TABLE queue_tickets ADD COLUMN query_token VARCHAR(64) NULL"))
        if not await _sqlite_column_exists(conn, "queue_tickets", "openid"):
            logger.warning("Repairing queue_tickets: adding missing openid column")
            await conn.execute(text("ALTER TABLE queue_tickets ADD COLUMN openid VARCHAR(64) NULL"))
        if not await _sqlite_column_exists(conn, "queue_tickets", "customer_id"):
            logger.warning("Repairing queue_tickets: adding missing customer_id column")
            await conn.execute(text("ALTER TABLE queue_tickets ADD COLUMN customer_id BIGINT NULL"))


async def ensure_distribution_schema(conn) -> None:
    """Add distribution MVP columns for old MySQL databases."""
    dialect = conn.dialect.name
    if dialect not in {"mysql", "mariadb"}:
        return

    if not await _mysql_column_exists(conn, "entrance_code", "table_no"):
        logger.warning("Repairing entrance_code: adding table_no column")
        await conn.execute(text("ALTER TABLE `entrance_code` ADD COLUMN `table_no` VARCHAR(32) NULL"))

    if not await _mysql_column_exists(conn, "customer", "inviter_id"):
        logger.warning("Repairing customer: adding inviter_id column")
        await conn.execute(text("ALTER TABLE `customer` ADD COLUMN `inviter_id` BIGINT NULL"))

    if not await _mysql_column_exists(conn, "customer", "inviter_parent_id"):
        logger.warning("Repairing customer: adding inviter_parent_id column")
        await conn.execute(text("ALTER TABLE `customer` ADD COLUMN `inviter_parent_id` BIGINT NULL"))

    result = await conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'customer'
              AND INDEX_NAME = 'idx_customer_tenant_inviter'
            """
        )
    )
    if int(result.scalar() or 0) == 0:
        await conn.execute(text("CREATE INDEX `idx_customer_tenant_inviter` ON `customer` (`tenant_id`, `inviter_id`)"))
