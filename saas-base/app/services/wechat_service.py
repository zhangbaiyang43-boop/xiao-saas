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
        self.jscode2session_url = "https://api.weixin.qq.com/sns/jscode2session"
        self.access_token_url = "https://api.weixin.qq.com/cgi-bin/token"
        self.phone_number_url = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
        self._access_token = ""
        self._access_token_expire_at = 0

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
            return self._mock_session(code)

        try:
            url = f"{self.jscode2session_url}?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            if data.get("errcode"):
                raise RuntimeError(data.get("errmsg") or "wechat code2session failed")

            return {
                "openid": data.get("openid"),
                "unionid": data.get("unionid"),
                "session_key": data.get("session_key"),
            }
        except Exception as exc:
            print(f"Wechat code2session error: {exc}")
            return self._mock_session(code)

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
