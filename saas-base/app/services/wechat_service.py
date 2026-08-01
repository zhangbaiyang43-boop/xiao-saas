import hashlib
import json
import time
import urllib.parse
import urllib.request

from app.config import settings


class WechatService:
    def __init__(self):
        self.app_id = settings.WECHAT_APP_
        self.app_secret = settings.WECHAT_APP_SECRET
        self.app_env = (getattr(settings, "APP_ENV", "development") or "development").lower()
        self.allow_mock_session = bool(getattr(settings, "ALLOW_MOCK_WECHAT_SESSION", False))
        self.jscode2session_url = "https://api.weixin.qq.com/sns/jscode2session"
        self.access_token_url = "https://api.weixin.qq.com/cgi-bin/token"
        self.phone_number_url = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
        self.subscribe_send_url = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"
        self._access_token = ""
        self._access_token_expire_at = 0

    def _can_use_mock_session(self) -> bool:
        return self.app_env != "production" and self.allow_mock_session

    def _mock_or_raise(self, code: str, reason: str):
        if self._can_use_mock_session():
            return self._mock_session(code)
        raise RuntimeError(reason)

    def _mock_session(self, code: str):
        digest = hashlib.sha256((code or "empty").encode("utf-8")).hexdigest()[:32]
        return {
            "openid": f"mock_{digest}",
            "unionid": None,
            "session_key": "mock_session_key",
        }

    async def code2session(self, code: str):
        params = {
            "appid": self.app_id,
            "secret": self.app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }

        if not self.app_id or not self.app_secret:
            return self._mock_or_raise(code, "wechat app credentials are not configured")

        try:
            url = f"{self.jscode2session_url}?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"Wechat code2session error: {exc}")
            return self._mock_or_raise(code, "wechat code2session request failed")

        if data.get("errcode"):
            return self._mock_or_raise(code, data.get("errmsg") or "wechat code2session failed")

        return {
            "openid": data.get("openid"),
            "unionid": data.get("unionid"),
            "session_key": data.get("session_key"),
        }
    async def get_access_token(self) -> str:
        now = int(time.time())
        if self._access_token and now < self._access_token_expire_at - 120:
            return self._access_token

        if not self.app_id or not self.app_secret:
            return ""

        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }
        url = f"{self.access_token_url}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        if data.get("errcode"):
            raise RuntimeError(data.get("errmsg") or "wechat access_token failed")

        self._access_token = data.get("access_token") or ""
        self._access_token_expire_at = now + int(data.get("expires_in") or 7200)
        return self._access_token

    async def get_phone_number(self, phone_code: str) -> str:
        if not phone_code:
            return ""
        if not self.app_id or not self.app_secret:
            return ""

        access_token = await self.get_access_token()
        if not access_token:
            return ""

        url = f"{self.phone_number_url}?access_token={urllib.parse.quote(access_token)}"
        payload = json.dumps({"code": phone_code}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        if data.get("errcode"):
            raise RuntimeError(data.get("errmsg") or "wechat phone number failed")

        phone_info = data.get("phone_info") or {}
        return phone_info.get("purePhoneNumber") or phone_info.get("phoneNumber") or ""

    async def send_subscribe_message(
        self,
        openid: str,
        template_id: str,
        data: dict,
        page: str | None = None,
    ) -> bool:
        """发一条订阅消息（一次性授权，用完这次额度就没了，跟顾客端 requestSubscribeMessage
        拿到的授权次数一一对应）。data 的 key 必须跟微信后台配置的模板字段名（比如 thing1、
        amount2、time3）完全一致，具体名字取决于商户在"订阅消息"里选的是哪个模板——这里不
        写死字段名，由调用方按模板要求组装。失败只记录日志不抛异常，不能因为一条提醒发送
        失败就影响主流程（这个函数目前只在后台提醒循环里单独调用，本身就是主流程之外的事）。"""
        if not openid or not template_id:
            return False

        access_token = await self.get_access_token()
        if not access_token:
            return False

        payload = {
            "touser": openid,
            "template_id": template_id,
            "data": data,
        }
        if page:
            payload["page"] = page

        url = f"{self.subscribe_send_url}?access_token={urllib.parse.quote(access_token)}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))

        return result.get("errcode", 0) == 0
