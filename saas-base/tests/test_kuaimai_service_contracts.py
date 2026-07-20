import base64
import hashlib
import unittest

from app.services.kuaimai_service import build_print_payload, create_sign


class KuaimaiServiceContractsTest(unittest.TestCase):
    def test_create_sign_uses_sorted_non_empty_params_with_secret_wrapped_md5(self):
        params = {
            "timestamp": "2020-10-10 15:29:29",
            "sn": "KM118MW",
            "appId": "123456",
            "empty": "",
            "sign": "ignored",
        }

        actual = create_sign(params, "abc")

        expected_raw = "abcappId123456snKM118MWtimestamp2020-10-10 15:29:29abc"
        self.assertEqual(actual, hashlib.md5(expected_raw.encode("utf-8")).hexdigest())

    def test_build_print_payload_encodes_receipt_text_and_signs_payload(self):
        payload = build_print_payload(
            app_id="100202",
            app_secret="secret",
            sn="KM110h45932",
            content="新订单\n桌号: A1",
            timestamp="2020-08-24 11:11:59",
            copies=2,
        )

        self.assertEqual(payload["appId"], "100202")
        self.assertEqual(payload["sn"], "KM110h45932")
        self.assertEqual(payload["timestamp"], "2020-08-24 11:11:59")
        self.assertEqual(payload["copies"], 2)
        decoded = base64.b64decode(payload["instructionsList"])
        self.assertIn("新订单".encode("gb18030"), decoded)
        self.assertEqual(payload["sign"], create_sign(payload, "secret"))


if __name__ == "__main__":
    unittest.main()
