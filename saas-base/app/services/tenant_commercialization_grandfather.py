"""One-time existing-tenant commercialization grandfather backfill
(F1G-CM-PD0-GF, migration 20260819_0002).

Pure data-migration logic, deliberately NOT part of SubscriptionService: it
is invoked exactly once, from one Alembic migration, never from a request
path, never from create_trial_for_tenant()'s normal new-tenant onboarding
flow (Phase 20's frozen contract). Kept here, importable independently of an
Alembic `op` context, so it can be exercised directly by tests as well as by
the migration -- one source of truth for the backfill SQL, not two.

Eligibility is strictly "zero historical subscription rows" -- not "no
ACTIVE row", not "currently resolves to FREE". A tenant with any prior
TRIAL/ACTIVE/EXPIRED/CANCELLED row already has commercialization history and
must never be re-granted a free 30 days by this or any future run.

Grants exactly what create_trial_for_tenant() already grants every new
tenant at registration: PRO, STATUS_TRIAL, 30 days -- not a new business
rule. Never ACTIVE (a transition grant is not a payment fact), never a
BillingInvoice/BillingPayment, never a resolver special-case: the resulting
row is read back through the same, unmodified
SubscriptionService.get_effective_subscription_view() -> EntitlementService
chain as any other Subscription row.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import sqlalchemy as sa

TRIAL_DAYS = 30
PLAN_CODE_PRO = "PRO"
STATUS_TRIAL = "TRIAL"


class ProPlanMissingError(RuntimeError):
    """The PRO plan row doesn't exist in the plan catalog. Fail closed:
    never insert a Subscription referencing a nonexistent plan_id."""

    pass


def backfill_zero_history_tenants(bind: sa.engine.Connection, *, now: datetime | None = None) -> int:
    """Grant a PRO TRIAL to every tenant with zero Subscription rows.

    Idempotent by construction: re-running this against the same DB state
    finds zero remaining zero-history tenants (every one already got a row
    the first time) and inserts nothing. Uses one shared `now` for every row
    created in a single call, so a batch of grandfathered tenants all share
    the exact same trial_started_at/trial_ends_at.

    Returns the number of Subscription rows inserted.
    """
    from app.utils.id_generator import generate_snowflake_id

    pro_plan = bind.execute(sa.text("SELECT id FROM plans WHERE code = :code"), {"code": PLAN_CODE_PRO}).fetchone()
    if pro_plan is None:
        raise ProPlanMissingError(
            "PRO plan missing from plan catalog -- refusing to grandfather "
            "existing tenants against a nonexistent plan_id"
        )
    pro_plan_id = pro_plan[0]

    zero_history_tenants = bind.execute(
        sa.text(
            """
            SELECT t.tenant_id
            FROM tenant t
            WHERE NOT EXISTS (
                SELECT 1 FROM subscriptions s WHERE s.tenant_id = t.tenant_id
            )
            """
        )
    ).fetchall()

    if not zero_history_tenants:
        return 0

    now = now or datetime.utcnow()
    trial_ends_at = now + timedelta(days=TRIAL_DAYS)

    for (tenant_id,) in zero_history_tenants:
        bind.execute(
            sa.text(
                """
                INSERT INTO subscriptions
                    (id, tenant_id, plan_id, status, trial_started_at, trial_ends_at,
                     started_at, ends_at, created_at, updated_at)
                VALUES
                    (:id, :tenant_id, :plan_id, :status, :trial_started_at, :trial_ends_at,
                     NULL, NULL, :now, :now)
                """
            ),
            {
                "id": generate_snowflake_id(),
                "tenant_id": tenant_id,
                "plan_id": pro_plan_id,
                "status": STATUS_TRIAL,
                "trial_started_at": now,
                "trial_ends_at": trial_ends_at,
                "now": now,
            },
        )

    return len(zero_history_tenants)
