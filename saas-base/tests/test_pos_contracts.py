import unittest

from app.api.v1.pos import (
    POS_VERIFY_PATH,
    build_pos_config_payload,
    mask_api_key,
)


class PosContractsTest(unittest.TestCase):
    def test_pos_config_payload_keeps_verify_contract_stable(self):
        payload = build_pos_config_payload(
            tenant_id="tenant-001",
            api_key="abcdefghijklmnopqrstuvwxyz123456",
            base_url="https://api.example.com",
        )

        self.assertEqual(payload["verify_url"], "https://api.example.com/api/v1/open/pos/verify")
        self.assertEqual(payload["tenant_id"], "tenant-001")
        self.assertEqual(payload["api_key"], "abcdefghijklmnopqrstuvwxyz123456")
        self.assertEqual(payload["masked_api_key"], "abcd************************3456")
        self.assertEqual(payload["example"]["tenant_id"], "tenant-001")
        self.assertEqual(payload["example"]["api_key"], "abcdefghijklmnopqrstuvwxyz123456")
        self.assertEqual(payload["example"]["code"], "顾客优惠券核销码")

    def test_mask_api_key_handles_short_values(self):
        self.assertEqual(mask_api_key("123456"), "******")
        self.assertEqual(mask_api_key(""), "")

    def test_open_pos_verify_path_is_public_contract(self):
        self.assertEqual(POS_VERIFY_PATH, "/api/v1/open/pos/verify")


if __name__ == "__main__":
    unittest.main()
