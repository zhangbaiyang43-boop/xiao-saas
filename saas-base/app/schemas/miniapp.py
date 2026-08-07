from typing import Optional

from pydantic import BaseModel, Field


class EntryJoinRequest(BaseModel):
    scene: Optional[str] = Field(None, description="entrance scene")
    tenant_id: Optional[str] = Field(None, description="tenant id fallback")
    code: str = Field(..., description="wechat login code")
    phone: Optional[str] = Field(None, description="manual phone")
    phone_code: Optional[str] = Field(None, description="wechat getPhoneNumber code")
    nickname: Optional[str] = Field(None, description="nickname")
    invite_code: Optional[str] = Field(None, description="inviter customer id")
    agreement_accepted: bool = Field(False, description="registration agreement accepted")
