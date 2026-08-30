import unittest

from app.services.wework_callback_service import WeworkCallbackService


class WeworkCallbackIdentityContractsTest(unittest.TestCase):
    def test_standard_external_userid_and_userid_fields_are_supported(self):
        event = {
            "ExternalUserID": "wm_test",
            "UserID": "zhang_test",
        }

        self.assertEqual(
            WeworkCallbackService._first_present(event, "ExternalUserID", "ExternalUser", "ExternalUserid"),
            "wm_test",
        )
        self.assertEqual(
            WeworkCallbackService._first_present(event, "UserID", "User", "Userid"),
            "zhang_test",
        )

    def test_legacy_external_user_and_user_aliases_still_work(self):
        event = {
            "ExternalUser": "legacy_external",
            "User": "legacy_user",
        }

        self.assertEqual(
            WeworkCallbackService._first_present(event, "ExternalUserID", "ExternalUser", "ExternalUserid"),
            "legacy_external",
        )
        self.assertEqual(
            WeworkCallbackService._first_present(event, "UserID", "User", "Userid"),
            "legacy_user",
        )

    def test_standard_fields_have_priority_over_legacy_aliases(self):
        event = {
            "ExternalUserID": "wm_test",
            "ExternalUser": "legacy_external",
            "ExternalUserid": "legacy_external_lower_id",
            "UserID": "zhang_test",
            "User": "legacy_user",
            "Userid": "legacy_user_lower_id",
        }

        self.assertEqual(
            WeworkCallbackService._first_present(event, "ExternalUserID", "ExternalUser", "ExternalUserid"),
            "wm_test",
        )
        self.assertEqual(
            WeworkCallbackService._first_present(event, "UserID", "User", "Userid"),
            "zhang_test",
        )

    def test_missing_identity_fields_return_none(self):
        event = {
            "Event": "change_external_contact",
            "ChangeType": "add_external_contact",
        }

        self.assertIsNone(WeworkCallbackService._first_present(event, "ExternalUserID", "ExternalUser", "ExternalUserid"))
        self.assertIsNone(WeworkCallbackService._first_present(event, "UserID", "User", "Userid"))


if __name__ == "__main__":
    unittest.main()
