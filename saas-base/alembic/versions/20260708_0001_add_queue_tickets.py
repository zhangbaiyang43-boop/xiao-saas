"""add queue tickets

Revision ID: 20260708_0001
Revises: 20260614_0006
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260708_0001"
down_revision = "20260614_0006"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    if table_exists("queue_tickets"):
        return
    op.create_table(
        "queue_tickets",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("queue_no", sa.String(length=16), nullable=False),
        sa.Column("queue_type", sa.String(length=1), nullable=False),
        sa.Column("queue_date", sa.Date(), nullable=False),
        sa.Column("daily_sequence", sa.Integer(), nullable=False),
        sa.Column("party_size", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("called_at", sa.DateTime(), nullable=True),
        sa.Column("seated_at", sa.DateTime(), nullable=True),
        sa.Column("skipped_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "queue_date",
            "queue_type",
            "daily_sequence",
            name="uq_queue_ticket_daily_type_sequence",
        ),
    )
    op.create_index(op.f("ix_queue_tickets_id"), "queue_tickets", ["id"], unique=False)
    op.create_index(op.f("ix_queue_tickets_queue_no"), "queue_tickets", ["queue_no"], unique=False)
    op.create_index(op.f("ix_queue_tickets_tenant_id"), "queue_tickets", ["tenant_id"], unique=False)
    op.create_index(
        "idx_queue_ticket_tenant_status_created",
        "queue_tickets",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_queue_ticket_tenant_date_type",
        "queue_tickets",
        ["tenant_id", "queue_date", "queue_type"],
        unique=False,
    )


def downgrade():
    op.drop_index("idx_queue_ticket_tenant_date_type", table_name="queue_tickets")
    op.drop_index("idx_queue_ticket_tenant_status_created", table_name="queue_tickets")
    op.drop_index(op.f("ix_queue_tickets_tenant_id"), table_name="queue_tickets")
    op.drop_index(op.f("ix_queue_tickets_queue_no"), table_name="queue_tickets")
    op.drop_index(op.f("ix_queue_tickets_id"), table_name="queue_tickets")
    op.drop_table("queue_tickets")