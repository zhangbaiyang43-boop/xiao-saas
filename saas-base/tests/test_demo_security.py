from datetime import timedelta
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from app.core.security import (
    create_demo_launch_code,
    create_demo_session_token,
    decode_demo_launch_code,
    decode_demo_session_token,
)


class DemoSecurityTest(unittest.TestCase):
    @patch("app.core.security.settings.DEMO_TENANT_ID", "demo-tenant")
    def test_launch_code_has_launch_type_only(self):
        token = create_demo_launch_code(expires_delta=timedelta(minutes=5))

        payload = decode_demo_launch_code(token)

        self.assertEqual(payload["type"], "demo_launch")
        self.assertNotIn("tenant_id", payload)

    @patch("app.core.security.settings.DEMO_TENANT_ID", "demo-tenant")
    def test_session_token_is_scoped_to_one_dining_session(self):
        token = create_demo_session_token(
            tenant_id="demo-tenant",
            dining_session_id="123",
            table_no="DEMO-01",
            expires_delta=timedelta(minutes=5),
        )

        payload = decode_demo_session_token(token)

        self.assertEqual(payload["type"], "demo_merchant")
        self.assertEqual(payload["scope"], "demo_order_fulfillment")
        self.assertEqual(payload["tenant_id"], "demo-tenant")
        self.assertEqual(payload["dining_session_id"], "123")
        self.assertEqual(payload["table_no"], "DEMO-01")

    def test_wrong_token_type_is_rejected(self):
        self.assertIsNone(decode_demo_session_token(create_demo_launch_code()))

    def test_launch_code_cli_refuses_when_demo_tenant_is_disabled(self):
        result = self.run_launch_code_cli(demo_tenant_id="")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DEMO_TENANT_ID 未配置", result.stderr)

    def test_launch_code_cli_prints_a_valid_launch_token(self):
        result = self.run_launch_code_cli(demo_tenant_id="demo-tenant")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = decode_demo_launch_code(result.stdout.strip())
        self.assertEqual(payload["type"], "demo_launch")

    @staticmethod
    def run_launch_code_cli(*, demo_tenant_id: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["DEMO_TENANT_ID"] = demo_tenant_id
        env["PYTHONIOENCODING"] = "utf-8"
        script = Path(__file__).resolve().parents[1] / "scripts" / "generate_demo_launch_code.py"
        return subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
