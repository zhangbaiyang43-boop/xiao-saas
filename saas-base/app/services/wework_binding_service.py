import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant_wecom_binding import MerchantWecomBinding, MerchantWecomBindingToken
from app.models.tenant import Tenant
from app.models.wework_event_log import WeworkEventLog
from app.schemas.tenant import normalize_phone
from app.services.tencent_sms_service import SmsPurpose, TencentSmsService
from app.utils.id_generator import generate_snowflake_id


BINDING_STATUS_ACTIVE = "ACTIVE"
TOKEN_STATUS_ACTIVE = "ACTIVE"
TOKEN_TTL_MINUTES = 20
CODE_PUBLIC_COOLDOWN_SECONDS = 60
CODE_PUBLIC_MAX_REQUESTS = 5
BINDING_CODE_PUBLIC_MESSAGE = "如果该手机号可用于绑定，验证码将发送"
ALLOWED_BIND_CHANGE_TYPES = {"add_external_contact"}


class WeworkBindingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class BindingTokenIssue:
    token: str
    expires_at: datetime
    source_event_id: int


class WeworkBindingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256((token or "").encode("utf-8")).hexdigest()

    @staticmethod
    def new_raw_token() -> str:
        return secrets.token_urlsafe(32)

    async def create_binding_token(self, *, source_event_id: int) -> BindingTokenIssue:
        event = await self._trusted_event(source_event_id)
        await self._reject_existing_external_binding(event.external_userid)

        raw_token = self.new_raw_token()
        expires_at = datetime.utcnow() + timedelta(minutes=TOKEN_TTL_MINUTES)
        token = MerchantWecomBindingToken(
            id=generate_snowflake_id(),
            tenant_id=event.tenant_id,
            token_hash=self.hash_token(raw_token),
            external_userid=event.external_userid,
            wecom_user_id=event.userid,
            source_event_id=event.id,
            status=TOKEN_STATUS_ACTIVE,
            expires_at=expires_at,
        )
        self.db.add(token)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise WeworkBindingError("TOKEN_CREATE_CONFLICT", "绑定入口生成失败，请重试") from exc
        return BindingTokenIssue(token=raw_token, expires_at=expires_at, source_event_id=event.id)

    async def send_binding_code(self, *, binding_token: str, phone: str) -> tuple[bool, str, dict]:
        token = await self._valid_token(binding_token, lock=True)
        now = datetime.utcnow()
        sms = TencentSmsService()
        if not self._can_request_code(token, now):
            return True, BINDING_CODE_PUBLIC_MESSAGE, {"expires_in": sms.ttl, "retry_after": CODE_PUBLIC_COOLDOWN_SECONDS}

        token.last_code_requested_at = now
        token.code_request_count = int(token.code_request_count or 0) + 1
        await self.db.commit()

        normalized_phone = normalize_phone(phone)
        tenant = await self._tenant_by_phone(normalized_phone)
        if not tenant or not tenant.status:
            return True, BINDING_CODE_PUBLIC_MESSAGE, {"expires_in": sms.ttl, "retry_after": CODE_PUBLIC_COOLDOWN_SECONDS}

        await sms.request_login_code(normalized_phone, purpose=SmsPurpose.WECOM_BINDING)
        return True, BINDING_CODE_PUBLIC_MESSAGE, {"expires_in": sms.ttl, "retry_after": CODE_PUBLIC_COOLDOWN_SECONDS}

    async def confirm_binding(self, *, binding_token: str, phone: str, otp_code: str) -> dict:
        token = await self._valid_token(binding_token, lock=True)
        normalized_phone = normalize_phone(phone)
        if not await TencentSmsService().verify_login_code(
            normalized_phone,
            otp_code,
            purpose=SmsPurpose.WECOM_BINDING,
        ):
            raise WeworkBindingError("INVALID_OTP", "验证码错误或已过期")

        tenant = await self._tenant_by_phone(normalized_phone)
        if not tenant or not tenant.status:
            raise WeworkBindingError("BINDING_FAILED", "绑定失败，请联系服务商处理")

        now = datetime.utcnow()
        external_binding = await self._active_binding_by_external(token.external_userid, lock=True)
        if external_binding:
            if external_binding.tenant_id == tenant.tenant_id:
                token.used_at = now
                await self.db.commit()
                return self.serialize_binding(external_binding, result="ALREADY_BOUND", merchant_name=tenant.name)
            raise WeworkBindingError("EXTERNAL_USERID_CONFLICT", "该企业微信客户已绑定其它商户")

        tenant_binding = await self._active_binding_by_tenant(tenant.tenant_id, lock=True)
        if tenant_binding:
            raise WeworkBindingError("TENANT_BINDING_CONFLICT", "该商户已绑定其它企业微信客户")

        binding = MerchantWecomBinding(
            id=generate_snowflake_id(),
            tenant_id=tenant.tenant_id,
            external_userid=token.external_userid,
            wecom_user_id=token.wecom_user_id,
            status=BINDING_STATUS_ACTIVE,
            bound_by="owner_phone_otp",
            bound_at=now,
            active_tenant_id_key=tenant.tenant_id,
            active_external_userid_key=token.external_userid,
        )
        token.used_at = now
        self.db.add(binding)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise WeworkBindingError("BINDING_CONFLICT", "企业微信绑定冲突，请联系服务商处理") from exc
        await self.db.refresh(binding)
        return self.serialize_binding(binding, result="BOUND", merchant_name=tenant.name)

    @staticmethod
    def serialize_binding(binding: MerchantWecomBinding, *, result: str, merchant_name: str | None = None) -> dict:
        return {
            "result": result,
            "binding_id": str(binding.id),
            "merchant_name": merchant_name,
            "status": binding.status,
            "bound_at": binding.bound_at,
        }

    async def _trusted_event(self, source_event_id: int) -> WeworkEventLog:
        result = await self.db.execute(select(WeworkEventLog).where(WeworkEventLog.id == source_event_id))
        event = result.scalar_one_or_none()
        if not event:
            raise WeworkBindingError("EVENT_NOT_FOUND", "企业微信事件不存在")
        if not event.external_userid:
            raise WeworkBindingError("EVENT_IDENTITY_MISSING", "企业微信事件缺少客户身份")
        change_type = event.change_type or event.event_type
        if change_type not in ALLOWED_BIND_CHANGE_TYPES:
            raise WeworkBindingError("EVENT_NOT_BINDABLE", "该企业微信事件不能用于商户绑定")
        return event

    async def _valid_token(self, raw_token: str, *, lock: bool = False) -> MerchantWecomBindingToken:
        query = select(MerchantWecomBindingToken).where(MerchantWecomBindingToken.token_hash == self.hash_token(raw_token))
        if lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        token = result.scalar_one_or_none()
        if not token or token.status != TOKEN_STATUS_ACTIVE:
            raise WeworkBindingError("TOKEN_INVALID", "绑定入口无效")
        if token.used_at is not None:
            raise WeworkBindingError("TOKEN_USED", "绑定入口已使用")
        if token.expires_at <= datetime.utcnow():
            raise WeworkBindingError("TOKEN_EXPIRED", "绑定入口已过期")
        return token

    @staticmethod
    def _can_request_code(token: MerchantWecomBindingToken, now: datetime) -> bool:
        if int(token.code_request_count or 0) >= CODE_PUBLIC_MAX_REQUESTS:
            return False
        if token.last_code_requested_at is None:
            return True
        elapsed = (now - token.last_code_requested_at).total_seconds()
        return elapsed >= CODE_PUBLIC_COOLDOWN_SECONDS

    async def _tenant_by_phone(self, phone: str) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.phone == phone))
        return result.scalar_one_or_none()

    async def _reject_existing_external_binding(self, external_userid: str) -> None:
        if await self._active_binding_by_external(external_userid):
            raise WeworkBindingError("EXTERNAL_USERID_CONFLICT", "该企业微信客户已绑定商户")

    async def _active_binding_by_external(self, external_userid: str, *, lock: bool = False) -> MerchantWecomBinding | None:
        query = select(MerchantWecomBinding).where(
            MerchantWecomBinding.active_external_userid_key == external_userid,
            MerchantWecomBinding.status == BINDING_STATUS_ACTIVE,
        )
        if lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _active_binding_by_tenant(self, tenant_id: str, *, lock: bool = False) -> MerchantWecomBinding | None:
        query = select(MerchantWecomBinding).where(
            MerchantWecomBinding.active_tenant_id_key == tenant_id,
            MerchantWecomBinding.status == BINDING_STATUS_ACTIVE,
        )
        if lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
