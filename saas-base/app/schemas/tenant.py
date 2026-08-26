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
    # phone 同时是登录凭证：只有当 phone 真的发生变化时才会被校验，用来确认
    # 提交的人真的能收到这个新手机号的验证码，防止手滑改错把自己踢出账号。
    phone_code: Optional[str] = Field(None, description="更换联系电话时，发到新手机号的验证码")
    address: Optional[str] = Field(None, description="商家地址")
    logo_url: Optional[str] = Field(None, description="商家 logo")
    status: Optional[bool] = Field(None, description="商家状态")


class TenantPhoneCodeRequest(BaseModel):
    """给"联系电话"要改成的新手机号发一条验证码——不验证旧手机号，
    因为这一步本身已经是登录态，只需要证明新号码确实收得到短信。"""

    phone: str = Field(..., description="要改绑的新手机号")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return normalize_phone(value)


class TenantSettingsRequest(BaseModel):
    profile: Optional[Dict[str, Any]] = Field(default_factory=dict, description="基础资料")
    member_rules: Optional[Dict[str, Any]] = Field(default_factory=dict, description="会员则")
    coupon_rules: Optional[Dict[str, Any]] = Field(default_factory=dict, description="默认发券则")
    business_info: Optional[Dict[str, Any]] = Field(default_factory=dict, description="门店营业信息")
    plugin_settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="插件默认状态")


class ChangePasswordRequest(BaseModel):
    old_password: str = Field("", description="当前密码")
    new_password: str = Field("", description="新密码")
