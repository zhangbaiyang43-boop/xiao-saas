from typing import Optional, Union

from pydantic import BaseModel, Field


class MemberLoginOrCreateRequest(BaseModel):
    tenant_id: Union[str, int] = Field(..., description="商家租户 ")
    phone: Optional[str] = Field(None, description="手机号")
    name: Optional[str] = Field(None, description="姓名或昵称")
    openid: Optional[str] = Field(None, description="微信 openid，开发阶段可为空")
    entrance_scene: Optional[str] = Field(None, description="入口码 scene")
