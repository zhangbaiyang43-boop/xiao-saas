import unittest

from app.models.base import BaseModel
from app.models.wework_contact_way import WeworkContactWay
from app.services.wework_service import WeworkService


class WeworkContactWayContractsTest(unittest.TestCase):
    def test_contact_way_model_is_tenant_scoped(self):
        self.assertTrue(issubclass(WeworkContactWay, BaseModel))
        self.assertTrue(hasattr(WeworkContactWay, "tenant_id"))
        self.assertTrue(hasattr(WeworkContactWay, "config_id"))
        self.assertTrue(hasattr(WeworkContactWay, "qr_code"))

    def test_build_contact_way_payload_uses_staff_qr_scene(self):
        payload = WeworkService().build_contact_way_payload(
            userid="ZhangBaiYang",
            scene="table-1",
            remark="1号桌贴",
            skip_verify=True,
        )

        self.assertEqual(payload["type"], 1)
        self.assertEqual(payload["scene"], 2)
        self.assertEqual(payload["style"], 1)
        self.assertEqual(payload["user"], ["ZhangBaiYang"])
        self.assertEqual(payload["state"], "table-1")
        self.assertEqual(payload["remark"], "1号桌贴")
        self.assertTrue(payload["skip_verify"])


if __name__ == "__main__":
    unittest.main()
