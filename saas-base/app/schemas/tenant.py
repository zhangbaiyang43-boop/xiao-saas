from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


def normalize_phone(value: str) -> str:
    phone = (value or "").strip()
    if len(phone) != 11 or not phone.isdigit() or not phone.startswith("1"):
        raise ValueError("手机号格式不正确")
    return phone


class TenantSchema(BaseModel):
    id: int
    tenant_id: str
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None
    status: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    phone: str = Field(..., description="手机号")
    code: str = Field(..., description="验证码")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return normalize_phone(value)


class RegisterCodeRequest(BaseModel):
    phone: str = Field(..., description="手机号")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return normalize_phone(value)


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, description="店名")
    phone: str = Field(..., description="手机号")
    code: str = Field(..., description="手机验证码（先调用 /register/code 获取）")
    address: Optional[str] = Field(None, description="商家地址")
    logo_url: Optional[str] = Field(None, description="商家 logo")
    initial_password: Optional[str] = Field(None, description="初始登录码（默认 123456）")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return normalize_phone(value)


class UpdateTenantProfileRequest(BaseModel):
    name: Optional[str] = Field(None, description="商家名称")
    phone: Optional[str] = Field(None, description="手机号")
    address: Optional[str] = Field(None, description="商家地址")
    logo_url: Optional[str] = Field(None, description="商家 logo")
    status: Optional[bool] = Field(None, description="商家状态")


class TenantSettingsRequest(BaseModel):
    profile: Optional[Dict[str, Any]] = Field(default_factory=dict, description="基础资料")
    member_rules: Optional[Dict[str, Any]] = Field(default_factory=dict, description="会员则")
    coupon_rules: Optional[Dict[str, Any]] = Field(default_factory=dict, description="默认发券则")
    business_info: Optional[Dict[str, Any]] = Field(default_factory=dict, description="门店营业信息")
    plugin_settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="插件默认状态")


class ChangePasswordRequest(BaseModel):
    old_password: str = Field("", description="当前密码")
    new_password: str = Field("", description="新密码")
