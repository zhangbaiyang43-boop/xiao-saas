import json
import time
import urllib.parse
import urllib.request

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.wework_contact_way import WeworkContactWay
from app.utils.id_generator import generate_snowflake_id


class WeworkService:
    _token_cache: dict = {}

    def config_status(self) -> dict:
        fields = {
            "corp_id": bool(settings.WEWORK_CORP_ID),
            "agent_id": bool(settings.WEWORK_AGENT_ID),
            "secret": bool(settings.WEWORK_SECRET),
            "token": bool(settings.WEWORK_TOKEN),
            "encoding_aes_key": bool(settings.WEWORK_ENCODING_AES_KEY),
            "callback_url": bool(settings.WEWORK_CALLBACK_URL),
            "staff_userid": bool(settings.WEWORK_STAFF_USERID),
        }
        missing = [key for key, value in fields.items() if not value]
        return {
            "configured": not missing,
            "missing": missing,
            "corp_id": settings.WEWORK_CORP_ID,
            "agent_id": settings.WEWORK_AGENT_ID,
            "callback_url": settings.WEWORK_CALLBACK_URL,
            "staff_userid": settings.WEWORK_STAFF_USERID,
            "token_cached": self._cached_token_valid(),
            "expires_at": self._token_cache.get("expires_at"),
        }

    def get_access_token(self, force_refresh: bool = False) -> dict:
        self._validate_config()
        if not force_refresh and self._cached_token_valid():
            return {
                "access_token": self._token_cache["access_token"],
                "expires_in": max(int(self._token_cache["expires_at"] - time.time()), 0),
                "expires_at": self._token_cache["expires_at"],
                "cached": True,
            }

        params = urllib.parse.urlencode(
            {
                "corpid": settings.WEWORK_CORP_ID,
                "corpsecret": settings.WEWORK_SECRET,
            }
        )
        payload = self._get_wework_json(f"/cgi-bin/gettoken?{params}")

        errcode = int(payload.get("errcode", -1))
        if errcode != 0:
            raise RuntimeError(self._format_wework_error(errcode, payload.get("errmsg") or "企业微信返回错误"))

        expires_in = int(payload.get("expires_in") or 7200)
        expires_at = int(time.time() + expires_in - 300)
        self._token_cache = {
            "access_token": payload["access_token"],
            "expires_at": expires_at,
        }
        return {
            "access_token": payload["access_token"],
            "expires_in": expires_in,
            "expires_at": expires_at,
            "cached": False,
        }

    def test_connection(self) -> dict:
        token_info = self.get_access_token(force_refresh=True)
        return {
            "connected": True,
            "message": "企业微信连接成功",
            "expires_in": token_info["expires_in"],
            "expires_at": token_info["expires_at"],
            "corp_id": settings.WEWORK_CORP_ID,
            "agent_id": settings.WEWORK_AGENT_ID,
        }

    def build_contact_way_payload(
        self,
        userid: str | None = None,
        scene: str | None = None,
        remark: str | None = None,
        skip_verify: bool = True,
    ) -> dict:
        staff_userid = userid or settings.WEWORK_STAFF_USERID
        if not staff_userid:
            raise RuntimeError("企业微信员工 userid 未配置")

        return {
            "type": 1,
            "scene": 2,
            "style": 1,
            "remark": remark or "会员运营二维码",
            "skip_verify": skip_verify,
            "state": scene or "member_entry",
            "user": [staff_userid],
        }

    async def create_contact_way(
        self,
        db: AsyncSession,
        tenant_id: str,
        userid: str | None = None,
        scene: str | None = None,
        remark: str | None = None,
        skip_verify: bool = True,
    ) -> dict:
        token_info = self.get_access_token()
        payload = self.build_contact_way_payload(userid, scene, remark, skip_verify)
        response = self._post_wework_json(
            "/cgi-bin/externalcontact/add_contact_way",
            payload,
            access_token=token_info["access_token"],
        )
        errcode = int(response.get("errcode", -1))
        if errcode != 0:
            raise RuntimeError(self._format_wework_error(errcode, response.get("errmsg") or "生成联系我二维码失败"))

        record = WeworkContactWay(
            id=generate_snowflake_id(),
            tenant_id=tenant_id,
            config_id=response["config_id"],
            qr_code=response["qr_code"],
            userid=payload["user"][0],
            scene=payload.get("state"),
            remark=payload.get("remark"),
            skip_verify=payload.get("skip_verify", True),
            raw_payload={"request": payload, "response": response},
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return self.serialize_contact_way(record)

    async def list_contact_ways(self, db: AsyncSession, tenant_id: str, skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        total_result = await db.execute(
            select(func.count()).select_from(WeworkContactWay).filter(WeworkContactWay.tenant_id == tenant_id)
        )
        result = await db.execute(
            select(WeworkContactWay)
            .filter(WeworkContactWay.tenant_id == tenant_id)
            .order_by(WeworkContactWay.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return [self.serialize_contact_way(item) for item in result.scalars().all()], int(total_result.scalar() or 0)

    @staticmethod
    def serialize_contact_way(item: WeworkContactWay) -> dict:
        return {
            "id": str(item.id),
            "tenant_id": item.tenant_id,
            "config_id": item.config_id,
            "qr_code": item.qr_code,
            "userid": item.userid,
            "scene": item.scene,
            "remark": item.remark,
            "skip_verify": item.skip_verify,
            "created_at": item.created_at,
        }

    def _cached_token_valid(self) -> bool:
        return bool(self._token_cache.get("access_token") and self._token_cache.get("expires_at", 0) > time.time())

    def _validate_config(self) -> None:
        status = self.config_status()
        required_missing = [item for item in status["missing"] if item in {"corp_id", "secret"}]
        if required_missing:
            raise RuntimeError(f"企业微信配置不完整：{', '.join(required_missing)}")

    def _get_wework_json(self, path: str) -> dict:
        url = f"https://qyapi.weixin.qq.com{path}"
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"无法连接企业微信接口：{exc}") from exc

    def _post_wework_json(self, path: str, payload: dict, access_token: str) -> dict:
        params = urllib.parse.urlencode({"access_token": access_token})
        url = f"https://qyapi.weixin.qq.com{path}?{params}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"无法连接企业微信接口：{exc}") from exc

    @staticmethod
    def _format_wework_error(errcode: int, errmsg: str) -> str:
        if errcode in {40013, 40014, 48002}:
            return f"Corp 配置错误或无权限：{errmsg}"
        if errcode in {40001, 40003, 40004}:
            return f"Secret 配置错误：{errmsg}"
        if errcode in {60020, 60011}:
            return f"服务器 IP 未加入企业微信可信 IP：{errmsg}"
        if errcode in {84074, 85002, 85005}:
            return f"员工未开通客户联系或无权限：{errmsg}"
        return f"企业微信接口失败（{errcode}）：{errmsg}"
