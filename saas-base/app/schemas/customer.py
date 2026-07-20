from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def validate_phone(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if len(value) != 11 or not value.isdigit() or not value.startswith("1"):
        raise ValueError("手机号格式不正确")
    return value


class CustomerSchema(BaseModel):
    id: int
    tenant_id: str
    openid: str
    external_userid: Optional[str]
    name: Optional[str]
    phone: Optional[str]
    tags: List[str] = []
    last_consume_time: Optional[datetime]
    status: int = 1
    created_at: datetime

    class Config:
        from_attributes = True


class CreateCustomerRequest(BaseModel):
    openid: str = Field(..., description="微信 openid 或后台手工客户标识")
    external_userid: Optional[str] = Field(None, description="企业微信外部联系人 ")
    name: Optional[str] = Field(None, description="姓名/昵称")
    phone: Optional[str] = Field(None, description="手机号")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签数组")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return validate_phone(value)


class UpdateCustomerRequest(BaseModel):
    name: Optional[str] = Field(None, description="姓名/昵称")
    phone: Optional[str] = Field(None, description="手机号")
    tags: Optional[List[str]] = Field(None, description="标签数组")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return validate_phone(value)


class UpdateCustomerStatusRequest(BaseModel):
    status: int = Field(..., ge=0, le=1, description="客户状态：1 启用，0 停用")


class MergeCustomerRequest(BaseModel):
    source_customer_id: int = Field(..., description="被合并的重复客户 ")
    target_customer_id: int = Field(..., description="保留的目标客户 ")

    @model_validator(mode="after")
    def validate_distinct_customer(self):
        if self.source_customer_id == self.target_customer_id:
            raise ValueError("来源客户和目标客户不能相同")
        return self
