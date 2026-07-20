from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ConsumptionSchema(BaseModel):
    id: int
    tenant_id: str
    customer_id: int
    project: str
    amount: Decimal
    consume_time: datetime
    remark: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CreateConsumptionRequest(BaseModel):
    customer_id: int = Field(..., description="客户")
    project: str = Field(..., description="消费项目")
    amount: Decimal = Field(..., description="消费金额")
    consume_time: Optional[str] = Field(None, description="消费时间")
    remark: Optional[str] = Field(None, description="备注")
