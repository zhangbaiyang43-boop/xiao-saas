from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionAdjustmentPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_type: str
    days: Any = None
    expires_at: str | None = None
    adjustment_type: str
    reason: str
    note: str | None = None


class SubscriptionAdjustmentCommitRequest(SubscriptionAdjustmentPreviewRequest):
    expected_subscription_id: str = Field(pattern=r"^\d+$")
    expected_before_expiry: str
    idempotency_key: str
