import unittest

from app.plugins.plugin_manager import (
    PLUGIN_STATUS_ENABLED,
    PLUGIN_STATUS_INSTALLED_DISABLED,
    PLUGIN_STATUS_NOT_INSTALLED,
    PluginManager,
)


class PluginFrameworkContractsTest(unittest.TestCase):
    def test_standard_plugins_are_discovered_from_plugin_json(self):
        manager = PluginManager()

        metadata = manager.discover_plugin_metadata("app/plugins")
        codes = {item["code"] for item in metadata}

        self.assertTrue({"coupon", "crm", "bargain", "points"}.issubset(codes))
        for item in metadata:
            with self.subTest(plugin=item["code"]):
                self.assertIn("name", item)
                self.assertIn("version", item)
                self.assertEqual(item["entry"], "plugin.py")
                self.assertTrue(item["plugin_dir"].endswith(item["code"]))

    def test_plugin_metadata_uses_stable_admin_shape(self):
        manager = PluginManager()
        metadata = manager.discover_plugin_metadata("app/plugins")
        coupon = next(item for item in metadata if item["code"] == "coupon")

        self.assertEqual(coupon["plugin_code"], "coupon")
        self.assertEqual(coupon["plugin_name"], "优惠券")
        self.assertEqual(coupon["category"], "member")
        self.assertFalse(coupon["enabled_by_default"])
        self.assertEqual(coupon["dependencies"], [])
        self.assertIn("admin_menu", coupon)
        self.assertIn("config_schema", coupon)

    def test_lifecycle_item_reports_status_version_dependencies_and_config(self):
        manager = PluginManager()
        metadata = {
            "code": "points",
            "plugin_code": "points",
            "name": "积分体系",
            "version": "0.1.0",
            "dependencies": ["coupon"],
            "admin_menu": {"title": "积分体系", "path": "/plugin/points"},
            "config_schema": [{"key": "rate", "label": "积分倍率", "default": 1}],
        }

        item = manager.build_lifecycle_item(
            metadata=metadata,
            tenant_record=None,
            enabled_codes=set(),
        )

        self.assertEqual(item["plugin_code"], "points")
        self.assertEqual(item["lifecycle_status"], PLUGIN_STATUS_NOT_INSTALLED)
        self.assertEqual(item["version"], "0.1.0")
        self.assertFalse(item["dependencies_met"])
        self.assertEqual(item["missing_dependencies"], ["coupon"])
        self.assertEqual(item["config"], {"rate": 1})

    def test_enabled_plugin_menu_only_returns_enabled_records(self):
        manager = PluginManager()
        metadata = {
            "code": "points",
            "plugin_code": "points",
            "name": "积分体系",
            "version": "0.1.0",
            "admin_menu": {"title": "积分体系", "path": "/plugin/points", "icon": "Medal"},
        }

        class Record:
            plugin_code = "points"
            lifecycle_status = PLUGIN_STATUS_ENABLED
            status = 1
            config_json = "{}"
            version = "0.1.0"
            last_error = None
            installed_at = None
            enabled_at = None
            disabled_at = None

        menus = manager.build_enabled_menus([metadata], {"points": Record()})

        self.assertEqual(menus, [{"plugin_code": "points", "title": "积分体系", "path": "/plugin/points", "icon": "Medal"}])

    def test_disabled_plugin_menu_is_hidden(self):
        manager = PluginManager()
        metadata = {
            "code": "points",
            "plugin_code": "points",
            "name": "积分体系",
            "version": "0.1.0",
            "admin_menu": {"title": "积分体系", "path": "/plugin/points"},
        }

        class Record:
            plugin_code = "points"
            lifecycle_status = PLUGIN_STATUS_INSTALLED_DISABLED
            status = 0
            config_json = "{}"
            version = "0.1.0"
            last_error = None
            installed_at = None
            enabled_at = None
            disabled_at = None

        self.assertEqual(manager.build_enabled_menus([metadata], {"points": Record()}), [])


if __name__ == "__main__":
    unittest.main()
