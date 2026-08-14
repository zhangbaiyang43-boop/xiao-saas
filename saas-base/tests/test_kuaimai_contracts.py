import asyncio
import unittest

from app.services.kuaimai_service import (
    KUAIMAI_API_BASE,
    KUAIMAI_ESC_WRITE_PATH,
    KuaimaiPrintError,
    _parse_kuaimai_response,
)


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class FakeResponse:
    def __init__(self, status_code=200, body='{"status": true}', content_type="application/json"):
        self.status_code = status_code
        self.text = body
        self.headers = {"content-type": content_type}
        self.history = []
        self.is_success = 200 <= status_code < 300

    def json(self):
        import json

        return json.loads(self.text)


class KuaimaiContractsTest(unittest.TestCase):
    def test_parse_kuaimai_response_supports_httpx_response_shape(self):
        body = _parse_kuaimai_response(FakeResponse())

        self.assertTrue(body["status"])

    def test_kuaimai_base_url_uses_cloud_gateway(self):
        self.assertEqual(KUAIMAI_API_BASE, "https://cloud.kuaimai.com")
        self.assertEqual(KUAIMAI_ESC_WRITE_PATH, "/api/cloud/print/escWrite")

    def test_http_5xx_is_result_unknown(self):
        with self.assertRaises(KuaimaiPrintError) as caught:
            _parse_kuaimai_response(FakeResponse(status_code=500, body="upstream error"))
        self.assertEqual(caught.exception.code, "KUAIMAI_HTTP_5XX")

    def test_http_4xx_is_definitive_request_failure(self):
        with self.assertRaises(KuaimaiPrintError) as caught:
            _parse_kuaimai_response(FakeResponse(status_code=400, body="bad request"))
        self.assertEqual(caught.exception.code, "KUAIMAI_HTTP_4XX")

    def test_empty_2xx_response_is_result_unknown(self):
        with self.assertRaises(KuaimaiPrintError) as caught:
            _parse_kuaimai_response(FakeResponse(status_code=200, body=""))
        self.assertEqual(caught.exception.code, "KUAIMAI_EMPTY_RESPONSE")

    def test_invalid_json_2xx_response_is_result_unknown(self):
        with self.assertRaises(KuaimaiPrintError) as caught:
            _parse_kuaimai_response(FakeResponse(status_code=200, body="not-json"))
        self.assertEqual(caught.exception.code, "KUAIMAI_INVALID_RESPONSE")


if __name__ == "__main__":
    unittest.main()
