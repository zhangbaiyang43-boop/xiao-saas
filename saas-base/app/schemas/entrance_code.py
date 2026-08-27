from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateEntranceCodeRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="entrance code name")
    channel: str = Field("STORE", max_length=32, description="scene: STORE/DOUYIN/POSTER/OTHER")
    coupon_template_id: Optional[int] = Field(None, description="coupon template id")
    page: str = Field("pages/entry/index", max_length=128, description="mini program landing page")
    env_version: str = Field("release", description="develop/trial/release")
    table_no: Optional[str] = Field(None, max_length=32, description="table number")
    entry_type: str = Field("table", max_length=16, description="entry type")
    order_mode: str = Field("dine_in", max_length=16, description="order mode")
    table_id: Optional[int] = Field(None, description="table id")
    target_page: str = Field("pages/order/index", max_length=128, description="target page")
    zone_type: Optional[str] = Field(None, max_length=16, description="quick | full, only meaningful when entry_type=table")


class UpdateEntranceCodeStatusRequest(BaseModel):
    status: int = Field(..., ge=0, le=1, description="status: 1 enabled, 0 disabled")


class BatchDownloadEntranceCodeRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=200, description="entrance code ids to bundle")


class ResolveEntranceRequest(BaseModel):
    scene: str = Field(..., min_length=1, max_length=32, description="entrance scene")


class RegenerateEntranceCodeRequest(BaseModel):
    env_version: str = Field("release", description="develop/trial/release")


class EntranceCodeResponse(BaseModel):
    id: int
    tenant_id: str
    name: str
    channel: str
    scene: str
    page: str
    coupon_template_id: Optional[int] = None
    image_url: Optional[str] = None
    env_version: str
    code_type: str
    status: int
    scan_count: int
    member_count: int
    last_scan_time: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    generation_status: str
    generation_error: Optional[str] = None
    table_no: Optional[str] = None
    entry_type: str
    order_mode: str
    table_id: Optional[int] = None
    target_page: str
    zone_type: Optional[str] = None

    class Config:
        from_attributes = True