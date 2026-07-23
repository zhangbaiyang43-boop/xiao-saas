"""add queue ticket query tokens

Revision ID: 20260711_0001
Revises: 20260708_0001
Create Date: 2026-07-11
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = "20260711_0001"
down_revision = "20260708_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if column_exists("queue_tickets", "query_token"):
        return
    op.add_column("queue_tickets", sa.Column("query_token", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM queue_tickets WHERE query_token IS NULL")).fetchall()
    used = set()
    for row in rows:
        token = secrets.token_urlsafe(24)
        while token in used:
            token = secrets.token_urlsafe(24)
        used.add(token)
        bind.execute(
            sa.text("UPDATE queue_tickets SET query_token = :query_token WHERE id = :id"),
            {"query_token": token, "id": row[0]},
        )

    op.alter_column("queue_tickets", "query_token", existing_type=sa.String(length=64), nullable=False)
    op.create_index("idx_queue_ticket_query_token", "queue_tickets", ["query_token"], unique=True)


def downgrade():
    op.drop_index("idx_queue_ticket_query_token", table_name="queue_tickets")
    op.drop_column("queue_tickets", "query_token")
