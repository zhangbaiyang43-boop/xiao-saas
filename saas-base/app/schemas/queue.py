from typing import Optional

from pydantic import BaseModel, Field


class QueueTicketCreate(BaseModel):
    tenant_id: int | str
    party_size: int = Field(..., ge=1, le=99)
    phone: Optional[str] = Field(default=None, max_length=20)
    note: Optional[str] = Field(default=None, max_length=200)


class QueueCallNext(BaseModel):
    tenant_id: int | str
    queue_type: str = Field(..., min_length=1, max_length=1)
