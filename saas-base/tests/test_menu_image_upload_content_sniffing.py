import asyncio
import io
import os
import unittest
from unittest.mock import patch

from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from app.api.v1.menu import upload_menu_image, _sniff_image_content_type

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
HTML_MASQUERADING_AS_PNG = b"<html><body><script>alert(document.cookie)</script></body></html>"


def make_request():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/menu/upload-image",
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


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


class SniffImageContentTypeTest(unittest.TestCase):
    def test_recognizes_real_jpeg_png_gif_webp(self):
        self.assertEqual(_sniff_image_content_type(JPEG_BYTES), "image/jpeg")
        self.assertEqual(_sniff_image_content_type(PNG_BYTES), "image/png")
        self.assertEqual(_sniff_image_content_type(b"GIF89a" + b"\x00" * 10), "image/gif")
        self.assertEqual(_sniff_image_content_type(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 10), "image/webp")

    def test_rejects_non_image_content(self):
        self.assertIsNone(_sniff_image_content_type(HTML_MASQUERADING_AS_PNG))
        self.assertIsNone(_sniff_image_content_type(b""))


class UploadMenuImageEndpointTest(unittest.IsolatedAsyncioTestCase):
    # Patching app.core.cos.upload_image imports app.core.cos for the first time in the
    # test process, which runs `load_dotenv()` at module scope -- that permanently copies
    # every key from the real saas-base/.env into os.environ (dotenv only skips keys
    # already present, but nothing sets these ones earlier). Once polluted, any later test
    # in the same pytest run that builds a fresh Settings() sees those real .env values
    # instead of the ones it explicitly configured, since pydantic-settings prioritizes
    # real env vars over an explicit _env_file. Snapshot/restore os.environ around these
    # tests so this test file doesn't leak state into whatever runs after it.
    def setUp(self):
        self._environ_snapshot = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._environ_snapshot)

    @patch("app.core.cos.upload_image")
    async def test_html_disguised_as_png_is_rejected_before_upload(self, mock_upload_image):
        # Filename says .png and the client-supplied Content-Type header says image/png --
        # both are attacker-controlled. The actual bytes are HTML/JS.
        upload = make_upload("dish.png", HTML_MASQUERADING_AS_PNG, "image/png")
        result = await upload_menu_image(make_request(), file=upload)

        self.assertEqual(result.code, 400)
        mock_upload_image.assert_not_called()

    @patch("app.core.cos.upload_image")
    async def test_real_png_is_uploaded_with_sniffed_content_type_not_client_header(self, mock_upload_image):
        mock_upload_image.return_value = "https://example.cos.myqcloud.com/dish_images/abc.png"
        # Client claims a spoofed Content-Type; the real bytes are a legitimate PNG. The
        # server must derive Content-Type from the sniffed bytes, not trust this header.
        upload = make_upload("dish.png", PNG_BYTES, "text/html")
        result = await upload_menu_image(make_request(), file=upload)

        self.assertEqual(result.code, 200)
        mock_upload_image.assert_called_once()
        _, kwargs = mock_upload_image.call_args
        called_content_type = mock_upload_image.call_args.args[2] if len(mock_upload_image.call_args.args) > 2 else kwargs.get("content_type")
        self.assertEqual(called_content_type, "image/png")


if __name__ == "__main__":
    unittest.main()
