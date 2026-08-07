import asyncio
import io
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from app.api.v1.tenant import update_profile, upload_shop_logo
from app.core.cos import is_allowed_cos_url, process_image, sniff_image_content_type
from app.schemas.tenant import UpdateTenantProfileRequest

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

HTML_MASQUERADING_AS_PNG = b"<html><body><script>alert(1)</script></body></html>"
PNG_HEADER_ONLY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _real_png_bytes(size=40):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color=(0, 128, 255)).save(buf, format="PNG")
    return buf.getvalue()


def make_request(path="/api/v1/tenant/upload-logo"):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = "tenant-a"
    request.state.token_type = "merchant"
    return request


def make_upload(filename: str, content: bytes, content_type: str = "image/png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


class CosUrlAllowlistTest(unittest.TestCase):
    def setUp(self):
        self._environ_snapshot = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._environ_snapshot)

    def test_empty_url_is_allowed(self):
        self.assertTrue(is_allowed_cos_url(""))
        self.assertTrue(is_allowed_cos_url(None))
        self.assertTrue(is_allowed_cos_url("   "))

    @patch("app.core.cos.COS_BUCKET", "poster-system-1253573799")
    @patch("app.core.cos.COS_REGION", "ap-guangzhou")
    @patch("app.core.cos.COS_BASE_URL", "")
    def test_project_cos_host_is_allowed(self):
        url = "https://poster-system-1253573799.cos.ap-guangzhou.myqcloud.com/logo_images/abc.webp"
        self.assertTrue(is_allowed_cos_url(url))

    @patch("app.core.cos.COS_BUCKET", "poster-system-1253573799")
    @patch("app.core.cos.COS_REGION", "ap-guangzhou")
    @patch("app.core.cos.COS_BASE_URL", "")
    def test_external_url_is_rejected(self):
        self.assertFalse(is_allowed_cos_url("https://evil.example.com/x.png"))
        self.assertFalse(is_allowed_cos_url("javascript:alert(1)"))


class ProcessLogoDimensionTest(unittest.TestCase):
    def test_logo_max_dimension_512(self):
        raw = _real_png_bytes(800)
        out = process_image(raw, max_dimension=512)
        from PIL import Image
        img = Image.open(io.BytesIO(out))
        self.assertLessEqual(max(img.width, img.height), 512)
        self.assertEqual(img.format, "WEBP")


class UploadShopLogoEndpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._environ_snapshot = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._environ_snapshot)

    @patch("app.core.cos.upload_image")
    async def test_html_disguised_as_png_is_rejected(self, mock_upload_image):
        upload = make_upload("logo.png", HTML_MASQUERADING_AS_PNG)
        result = await upload_shop_logo(make_request(), file=upload)
        self.assertEqual(result.code, 400)
        mock_upload_image.assert_not_called()

    @patch("app.core.cos.upload_image")
    async def test_undecodable_png_header_is_rejected(self, mock_upload_image):
        upload = make_upload("logo.png", PNG_HEADER_ONLY)
        result = await upload_shop_logo(make_request(), file=upload)
        self.assertEqual(result.code, 400)
        mock_upload_image.assert_not_called()

    @patch("app.core.cos.upload_image")
    async def test_real_image_uploads_to_logo_images_as_webp(self, mock_upload_image):
        mock_upload_image.return_value = "https://example.cos.myqcloud.com/logo_images/abc.webp"
        upload = make_upload("logo.png", _real_png_bytes())
        result = await upload_shop_logo(make_request(), file=upload)
        self.assertEqual(result.code, 200)
        mock_upload_image.assert_called_once()
        args, kwargs = mock_upload_image.call_args
        self.assertEqual(kwargs.get("folder") or (args[3] if len(args) > 3 else None), "logo_images")
        filename = args[1] if len(args) > 1 else kwargs.get("filename")
        self.assertTrue(str(filename).endswith(".webp"))


class UpdateProfileLogoValidationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._environ_snapshot = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._environ_snapshot)

    @patch("app.api.v1.tenant.get_current_tenant")
    @patch("app.api.v1.tenant.TenantService")
    async def test_rejects_non_cos_logo_url(self, mock_service_cls, mock_get_tenant):
        tenant = MagicMock()
        mock_get_tenant.return_value = ("tenant-a", tenant, None)
        mock_service_cls.return_value = MagicMock()
        data = UpdateTenantProfileRequest(name="店", logo_url="https://evil.example.com/a.png")
        result = await update_profile(data, db=AsyncMock())
        self.assertEqual(result.code, 400)
        self.assertIn("COS", result.msg)

    @patch("app.core.cos.COS_BUCKET", "poster-system-1253573799")
    @patch("app.core.cos.COS_REGION", "ap-guangzhou")
    @patch("app.core.cos.COS_BASE_URL", "")
    @patch("app.api.v1.tenant.get_current_tenant")
    @patch("app.api.v1.tenant.TenantService")
    async def test_accepts_cos_logo_url(self, mock_service_cls, mock_get_tenant):
        tenant = MagicMock()
        updated = MagicMock(
            tenant_id="tenant-a",
            name="店",
            phone="13800138000",
            address="",
            logo_url="https://poster-system-1253573799.cos.ap-guangzhou.myqcloud.com/logo_images/a.webp",
            status=True,
        )
        mock_get_tenant.return_value = ("tenant-a", tenant, None)
        service = MagicMock()
        service.update_tenant_profile = AsyncMock(return_value=updated)
        mock_service_cls.return_value = service
        data = UpdateTenantProfileRequest(
            name="店",
            logo_url="https://poster-system-1253573799.cos.ap-guangzhou.myqcloud.com/logo_images/a.webp",
        )
        result = await update_profile(data, db=AsyncMock())
        self.assertEqual(result.code, 200)
        service.update_tenant_profile.assert_awaited()


class SniffStillImportedFromMenu(unittest.TestCase):
    def test_menu_sniff_wrapper(self):
        from app.api.v1.menu import _sniff_image_content_type
        self.assertEqual(_sniff_image_content_type(b"\xff\xd8\xff" + b"\x00" * 8), "image/jpeg")
        self.assertIsNone(_sniff_image_content_type(HTML_MASQUERADING_AS_PNG))
        self.assertEqual(sniff_image_content_type(b"\x89PNG\r\n\x1a\n"), "image/png")
