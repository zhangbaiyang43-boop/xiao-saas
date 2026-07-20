import base64
import hashlib
import json
import socket
import struct
import time
import xml.etree.ElementTree as ET

from Crypto.Cipher import AES
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tenant import Tenant
from app.models.wework_event_log import WeworkEventLog
from app.utils.id_generator import generate_snowflake_id


class WeworkCallbackService:
    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        self._validate_signature(settings.WEWORK_TOKEN, timestamp, nonce, echostr, msg_signature)
        return self.decrypt(echostr)

    async def handle_event(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        body: bytes,
    ) -> dict:
        root = ET.fromstring(body.decode("utf-8"))
        encrypt = self._find_text(root, "Encrypt")
        self._validate_signature(settings.WEWORK_TOKEN, timestamp, nonce, encrypt, msg_signature)
        plaintext = self.decrypt(encrypt)
        event = self.parse_xml(plaintext)
        event_type = event.get("ChangeType") or event.get("Event") or "UNKNOWN"
        tenant_id = await self._resolve_tenant_id()

        if self.db is not None:
            self.db.add(
                WeworkEventLog(
                    id=generate_snowflake_id(),
                    tenant_id=tenant_id,
                    external_userid=event.get("ExternalUser") or event.get("ExternalUserid"),
                    userid=event.get("User") or event.get("Userid"),
                    event_type=event_type,
                    change_type=event.get("ChangeType"),
                    state=event.get("State"),
                    config_id=event.get("ConfigId"),
                    raw_payload=event,
                )
            )
            await self.db.commit()

        return {
            "tenant_id": tenant_id,
            "event_type": event_type,
            "external_userid": event.get("ExternalUser") or event.get("ExternalUserid"),
            "userid": event.get("User") or event.get("Userid"),
            "state": event.get("State"),
            "raw_payload": event,
        }

    async def list_events(self, skip: int = 0, limit: int = 20, tenant_id: str | None = None) -> tuple[list[dict], int]:
        if self.db is None:
            return [], 0
        tenant_id = tenant_id or await self._resolve_tenant_id()
        total_result = await self.db.execute(
            select(func.count()).select_from(WeworkEventLog).filter(WeworkEventLog.tenant_id == tenant_id)
        )
        result = await self.db.execute(
            select(WeworkEventLog)
            .filter(WeworkEventLog.tenant_id == tenant_id)
            .order_by(WeworkEventLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = [self.serialize_event(item) for item in result.scalars().all()]
        return items, int(total_result.scalar() or 0)

    @staticmethod
    def serialize_event(item: WeworkEventLog) -> dict:
        return {
            "id": str(item.id),
            "tenant_id": item.tenant_id,
            "external_userid": item.external_userid,
            "userid": item.userid,
            "event_type": item.event_type,
            "change_type": item.change_type,
            "state": item.state,
            "config_id": item.config_id,
            "raw_payload": item.raw_payload,
            "created_at": item.created_at,
        }

    def decrypt(self, encrypted_text: str) -> str:
        aes_key = self._aes_key()
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_key[:16])
        decrypted = cipher.decrypt(base64.b64decode(encrypted_text))
        plaintext = self._pkcs7_unpad(decrypted)
        content_length = socket.ntohl(struct.unpack("I", plaintext[16:20])[0])
        content = plaintext[20 : 20 + content_length]
        corp_id = plaintext[20 + content_length :].decode("utf-8")
        if corp_id != settings.WEWORK_CORP_:
            raise RuntimeError("企业微信回调 Corp 不匹配")
        return content.decode("utf-8")

    def encrypt_for_test(self, plaintext: str, nonce: str = "testnonce", timestamp: str | None = None) -> dict:
        timestamp = timestamp or str(int(time.time()))
        aes_key = self._aes_key()
        random_bytes = b"1234567890123456"
        msg = plaintext.encode("utf-8")
        payload = random_bytes + struct.pack("!I", len(msg)) + msg + settings.WEWORK_CORP_.encode("utf-8")
        payload = self._pkcs7_pad(payload)
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_key[:16])
        encrypted = base64.b64encode(cipher.encrypt(payload)).decode("utf-8")
        signature = self.signature(settings.WEWORK_TOKEN, timestamp, nonce, encrypted)
        return {
            "encrypt": encrypted,
            "msg_signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
        }

    @staticmethod
    def parse_xml(xml_text: str) -> dict:
        root = ET.fromstring(xml_text)
        return {child.tag: child.text for child in root}

    @staticmethod
    def signature(token: str, timestamp: str, nonce: str, encrypted_text: str) -> str:
        values = [token, timestamp, nonce, encrypted_text]
        values.sort()
        return hashlib.sha1("".join(values).encode("utf-8")).hexdigest()

    def _validate_signature(self, token: str, timestamp: str, nonce: str, encrypted_text: str, msg_signature: str) -> None:
        expected = self.signature(token, timestamp, nonce, encrypted_text)
        if expected != msg_signature:
            raise RuntimeError("企业微信回调签名校验失败")

    def _aes_key(self) -> bytes:
        if not settings.WEWORK_ENCODING_AES_KEY:
            raise RuntimeError("企业微信 EncodingAESKey 未配置")
        return base64.b64decode(settings.WEWORK_ENCODING_AES_KEY + "=")

    @staticmethod
    def _pkcs7_unpad(payload: bytes) -> bytes:
        pad = payload[-1]
        if pad < 1 or pad > 32:
            raise RuntimeError("企业微信回调解密失败")
        return payload[:-pad]

    @staticmethod
    def _pkcs7_pad(payload: bytes) -> bytes:
        block_size = 32
        pad = block_size - len(payload) % block_size
        return payload + bytes([pad]) * pad

    @staticmethod
    def _find_text(root: ET.Element, tag: str) -> str:
        value = root.findtext(tag)
        if not value:
            raise RuntimeError(f"企业微信回调缺少 {tag}")
        return value

    async def _resolve_tenant_id(self) -> str:
        if settings.WEWORK_TENANT_:
            return settings.WEWORK_TENANT_
        if self.db is not None and settings.WEWORK_CORP_:
            result = await self.db.execute(select(Tenant).filter(Tenant.corp_id == settings.WEWORK_CORP_))
            tenant = result.scalar_one_or_none()
            if tenant:
                return tenant.tenant_id
        if self.db is not None:
            result = await self.db.execute(select(Tenant).filter(Tenant.status == True).order_by(Tenant.created_at.asc()).limit(1))
            tenant = result.scalar_one_or_none()
            if tenant:
                return tenant.tenant_id
        return "GLOBAL"
