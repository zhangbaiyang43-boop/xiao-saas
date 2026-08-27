"""桌贴码中心的门店 Logo 叠加。

`_generate_code_image` 从微信 `getwxacodeunlimit` 取回的小程序码，中心是
平台自己的头像。商家（以及顾客）更希望看到本店 Logo——既打消"这码是不是
别人贴的"的顾虑，也让商家更愿意把码贴出去。

这里只测纯图像处理的 `_overlay_center_logo`：不联网、不碰数据库。
关键不变量——**Logo 任何一步出问题都不能让整张码出不来**。
"""

import asyncio
import io
import unittest
from unittest.mock import patch

from PIL import Image

from app.services.entrance_code_service import EntranceCodeService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _png(size, color):
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=color).save(buf, format="PNG")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class OverlayCenterLogoTest(unittest.TestCase):
    def setUp(self):
        self.service = EntranceCodeService.__new__(EntranceCodeService)
        self.code_bytes = _png(430, (255, 255, 255))
        self.logo_bytes = _png(200, (7, 193, 96))

    def test_overlays_logo_and_keeps_code_dimensions(self):
        with patch("urllib.request.urlopen", return_value=_FakeResponse(self.logo_bytes)):
            out = self.service._overlay_center_logo(self.code_bytes, "https://cos.example.com/logo.webp")

        self.assertNotEqual(out, self.code_bytes)
        img = Image.open(io.BytesIO(out)).convert("RGB")
        self.assertEqual(img.size, (430, 430))
        # 中心像素应当来自绿色 Logo，而不是原本的白底
        r, g, b = img.getpixel((215, 215))
        self.assertGreater(g, r + 40)
        self.assertGreater(g, b + 40)

    def test_overlay_disc_stays_within_center_zone(self):
        # 白底盘要盖满微信头像区（~46% 码宽），但不能溢到外圈数据点：
        # 距中心 0.29*宽 处的像素必须和原图一模一样。
        base = Image.new("RGB", (430, 430), (0, 0, 0))  # 纯黑，方便判断"没被动过"
        buf = io.BytesIO()
        base.save(buf, format="PNG")
        with patch("urllib.request.urlopen", return_value=_FakeResponse(self.logo_bytes)):
            out = self.service._overlay_center_logo(buf.getvalue(), "https://cos.example.com/logo.webp")
        img = Image.open(io.BytesIO(out)).convert("RGB")
        for point in [(215 + 125, 215), (215, 215 + 125), (215 - 125, 215), (215, 215 - 125)]:
            self.assertEqual(img.getpixel(point), (0, 0, 0), f"{point} 不应被叠加区覆盖")

    def test_backing_disc_covers_wechat_avatar_zone(self):
        # 反过来：白底盘必须真的铺到 ~0.4*宽 的半径，否则盖不住"开心点单"那圈绿底。
        base = Image.new("RGB", (430, 430), (0, 0, 0))
        buf = io.BytesIO()
        base.save(buf, format="PNG")
        with patch("urllib.request.urlopen", return_value=_FakeResponse(self.logo_bytes)):
            out = self.service._overlay_center_logo(buf.getvalue(), "https://cos.example.com/logo.webp")
        img = Image.open(io.BytesIO(out)).convert("RGB")
        # 距中心 0.18*宽（77px）处仍应被盘/Logo 覆盖，不是原来的纯黑
        for point in [(215 + 77, 215), (215, 215 + 77), (215 - 77, 215), (215, 215 - 77)]:
            self.assertNotEqual(img.getpixel(point), (0, 0, 0), f"{point} 应被白底盘覆盖")

    def test_download_failure_returns_original_untouched(self):
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            out = self.service._overlay_center_logo(self.code_bytes, "https://cos.example.com/logo.webp")
        self.assertEqual(out, self.code_bytes)

    def test_non_http_url_returns_original_untouched(self):
        out = self.service._overlay_center_logo(self.code_bytes, "/static/logo_images/x.webp")
        self.assertEqual(out, self.code_bytes)

    def test_empty_logo_url_returns_original_untouched(self):
        self.assertEqual(self.service._overlay_center_logo(self.code_bytes, ""), self.code_bytes)

    def test_corrupt_logo_bytes_returns_original_untouched(self):
        with patch("urllib.request.urlopen", return_value=_FakeResponse(b"not an image")):
            out = self.service._overlay_center_logo(self.code_bytes, "https://cos.example.com/logo.webp")
        self.assertEqual(out, self.code_bytes)


if __name__ == "__main__":
    unittest.main()
