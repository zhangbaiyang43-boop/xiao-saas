import os
import tempfile
import unittest

from app.config import Settings


class SettingsContractsTest(unittest.TestCase):
    def test_settings_accept_lowercase_wework_env_and_ignore_extra_keys(self):
        content = "\n".join(
            [
                "wework_corp_id=ww-test",
                "wework_agent_id=1000004",
                "wework_secret=secret-test",
                "wework_token=token-test",
                "wework_encoding_aes_key=encoding-key-test",
                "wework_callback_url=https://example.com",
                "wework_staff_userid=ZhangBaiYang",
                "unknown_future_key=ignored",
            ]
        )
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as file:
            file.write(content)
            env_file = file.name

        try:
            settings = Settings(_env_file=env_file)
        finally:
            os.unlink(env_file)

        self.assertEqual(settings.WEWORK_CORP_ID, "ww-test")
        self.assertEqual(settings.WEWORK_AGENT_ID, "1000004")
        self.assertEqual(settings.WEWORK_STAFF_USERID, "ZhangBaiYang")


if __name__ == "__main__":
    unittest.main()
