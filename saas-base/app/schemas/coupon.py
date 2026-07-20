from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class CouponTemplateSchema(BaseModel):
    id: int
    tenant_id: str
    name: str
    type: str
    value: Decimal
    min_amount: Decimal
    total_stock: int
    used_stock: int
    start_time: datetime
    end_time: datetime
    status: int
    created_at: datetime

    class Config:
        from_attributes = True


class CreateCouponTemplateRequest(BaseModel):
    name: str = Field(..., description="券名称")
    type: str = Field(..., description="类型：PERCENT/FIXED")
    value: Decimal = Field(..., gt=0, description="优惠金额或折扣")
    min_amount: Decimal = Field(0, ge=0, description="使用门槛")
    total_stock: int = Field(100, ge=1, description="发放总量")
    start_time: str = Field(..., description="有效期开始")
    end_time: str = Field(..., description="有效期结束")
    status: int = Field(1, ge=0, le=1, description="状态：1上架，0下架")

    @field_validator("type")
    @classmethod
    def validate_type(cls, value):
        if value not in {"PERCENT", "FIXED"}:
            raise ValueError("优惠券类型必须是 PERCENT 或 FIXED")
        return value

    @model_validator(mode="after")
    def validate_effective_range(self):
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        if end <= start:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class UpdateCouponTemplateRequest(BaseModel):
    name: Optional[str] = Field(None, description="券名称")
    type: Optional[str] = Field(None, description="类型")
    value: Optional[Decimal] = Field(None, gt=0, description="优惠金额或折扣")
    min_amount: Optional[Decimal] = Field(None, ge=0, description="使用门槛")
    total_stock: Optional[int] = Field(None, ge=1, description="发放总量")
    start_time: Optional[str] = Field(None, description="有效期开始")
    end_time: Optional[str] = Field(None, description="有效期结束")
    status: Optional[int] = Field(None, ge=0, le=1, description="状态：1上架，0下架")

    @field_validator("type")
    @classmethod
    def validate_type(cls, value):
        if value is not None and value not in {"PERCENT", "FIXED"}:
            raise ValueError("优惠券类型必须是 PERCENT 或 FIXED")
        return value

    @model_validator(mode="after")
    def validate_effective_range(self):
        if self.start_time and self.end_time:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
            if end <= start:
                raise ValueError("结束时间必须晚于开始时间")
        return self


class SendCouponsRequest(BaseModel):
    template_id: Union[int, str] = Field(..., description="优惠券 ")
    customer_ids: List[Union[int, str]] = Field(..., min_length=1, description="客户  列表")


class RecallCouponRequest(BaseModel):
    reason: str = Field("商家收回", min_length=1, max_length=255, description="收回原因")


class CouponSchema(BaseModel):
    id: int
    tenant_id: str
    template_id: int
    customer_id: int
    code: str
    verify_code: Optional[str] = None
    status: str
    use_time: Optional[datetime]
    expire_time: datetime
    created_at: datetime

    class Config:
        from_attributes = True
