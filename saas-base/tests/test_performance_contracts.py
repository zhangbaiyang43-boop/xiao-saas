import unittest

from app.config import settings
from app.core.pagination import build_page, normalize_pagination
from app.models.consumption import Consumption
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity


def index_names(model):
    return {item.name for item in model.__table__.indexes}


class PerformanceContractsTest(unittest.TestCase):
    def test_pagination_is_clamped_to_platform_limits(self):
        self.assertEqual(normalize_pagination(skip=-10, limit=999), (0, settings.PAGE_MAX_LIMIT))
        self.assertEqual(normalize_pagination(skip=20, limit=50), (20, 50))

    def test_page_response_has_items_and_total_metadata(self):
        page = build_page(items=[{"id": 1}], total=23, skip=10, limit=10)

        self.assertEqual(page, {
            "items": [{"id": 1}],
            "total": 23,
            "skip": 10,
            "limit": 10,
            "page": 2,
            "page_size": 10,
        })

    def test_database_pool_settings_are_configurable(self):
        self.assertGreaterEqual(settings.DB_POOL_SIZE, 5)
        self.assertGreaterEqual(settings.DB_MAX_OVERFLOW, 10)
        self.assertGreater(settings.SLOW_REQUEST_MS, 0)

    def test_common_tenant_composite_indexes_exist(self):
        expected = {
            Customer: {"idx_customer_tenant_created_at", "idx_customer_tenant_phone"},
            CustomerIdentity: {"idx_customer_identity_customer", "idx_customer_identity_phone"},
            Consumption: {"idx_consumption_tenant_customer_time", "idx_consumption_tenant_created_at"},
            CouponTemplate: {"idx_coupon_template_tenant_status", "idx_coupon_template_tenant_created_at"},
            Coupon: {"idx_coupon_tenant_customer", "idx_coupon_tenant_status", "idx_coupon_tenant_created_at"},
        }

        for model, indexes in expected.items():
            with self.subTest(model=model.__name__):
                self.assertTrue(indexes.issubset(index_names(model)))


if __name__ == "__main__":
    unittest.main()
