from typing import Optional, Union

from pydantic import BaseModel, Field


class MemberLoginOrCreateRequest(BaseModel):
    tenant_id: Union[str, int] = Field(..., description="商家租户 ")
    phone: Optional[str] = Field(None, description="手机号，仅作为新建客户的展示信息，不用于身份匹配")
    name: Optional[str] = Field(None, description="姓名或昵称")
    code: Optional[str] = Field(None, description="微信 wx.login() 返回的 code，用于换取经校验的 openid")
    entrance_scene: Optional[str] = Field(None, description="入口码 scene")
