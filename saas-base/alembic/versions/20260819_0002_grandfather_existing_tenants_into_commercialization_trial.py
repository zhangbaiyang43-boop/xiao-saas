"""Grandfather existing tenants into commercialization trial (F1G-CM-PD0-GF).

Revision ID: 20260819_0002
Revises: 20260819_0001
Create Date: 2026-08-19

PD0 preflight found a P0 deployment regression: SubscriptionService.
get_effective_subscription_view() resolves any tenant with zero Subscription
rows to the FREE plan, and this release's merged F1F entitlement-gating
commits now require STANDARD/PRO for KITCHEN_PRINT, and PRO for MEMBERSHIP/
COUPONS/DISTRIBUTION_REFERRAL. Every pre-existing production tenant predates
the whole Subscription system and has zero rows -- deploying as-is would
silently disable those already-live features for every existing merchant the
instant this code goes live.

Frozen product decision (EXISTING_TENANT_TRANSITION_POLICY=
ONE_TIME_PRO_TRIAL_30_DAYS): grant a normal PRO TRIAL, using the exact same
plan/duration/status shape create_trial_for_tenant() already grants every new
tenant at registration (30 days, PLAN_CODE_PRO, STATUS_TRIAL) -- not a new
business rule, not ACTIVE (this is a transition grant, not a payment fact),
and never a resolver special-case: after this migration, every entitlement
check still goes through the same, unmodified SubscriptionService ->
EntitlementService chain.

Eligibility is deliberately the narrowest predicate that satisfies the
policy: only tenants with ZERO historical subscriptions rows (not "no ACTIVE
row", not "currently resolves to FREE") qualify. A tenant with an expired
trial, a cancelled subscription, or a lapsed paid plan already has
commercialization history and must not be re-granted a free 30 days.

No BillingInvoice, no BillingPayment, no paid_at/success_processed_at is
created -- this is a data migration, not a purchase.

The actual backfill SQL lives in
app/services/tenant_commercialization_grandfather.py, shared with this
migration's targeted tests (tests/test_existing_tenant_commercialization_trial.py)
so there is one source of truth, not a copy that can drift.
"""
from alembic import op

from app.services.tenant_commercialization_grandfather import backfill_zero_history_tenants

revision = "20260819_0002"
down_revision = "20260819_0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    backfill_zero_history_tenants(bind)


def downgrade():
    # NO-OP, deliberately data-safe (DOWNGRADE_STRATEGY=NO_OP_DATA_SAFE): a
    # transition-trial Subscription row created by this migration is
    # indistinguishable, after the fact, from a tenant's real subsequent
    # business state (they may have already renewed, cancelled, or purchased
    # against it) -- there is no reliable "created by this migration" marker
    # to filter on, and guessing would risk deleting real business history.
    pass
