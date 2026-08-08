"""Regression: uvicorn must be able to import app.main (route construction)."""

from __future__ import annotations

import unittest


class AppMainImportTest(unittest.TestCase):
    def test_import_app_main(self):
        from app.main import app

        self.assertIsNotNone(app)

    def test_formal_staff_auth_routes_registered(self):
        from app.main import app

        paths = set()
        for route in app.routes:
            path = getattr(route, "path", None)
            if path:
                paths.add(path)
        self.assertIn("/api/v1/login/staff", paths)
        self.assertIn("/api/v1/login/staff/device", paths)
        self.assertIn("/api/v1/login/staff/logout-device", paths)
        self.assertNotIn("/api/v1/login/staff/wechat", paths)
        self.assertNotIn("/api/v1/login/staff/handoff", paths)
        self.assertNotIn("/api/v1/staff/wechat/bind/confirm", paths)
        self.assertNotIn("/api/v1/staff/miniprogram/bind/confirm", paths)
        self.assertNotIn("/api/v1/staff/miniprogram/login", paths)


if __name__ == "__main__":
    unittest.main()
