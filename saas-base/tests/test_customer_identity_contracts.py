import asyncio
import inspect
import unittest
from pydantic import ValidationError

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.models.base import BaseModel as TenantBaseModel
from app.models.benefit_template import BenefitTemplate
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity
from app.models.member_account import MemberAccount
from app.models.point_ledger import PointLedger
from app.schemas.customer import CreateCustomerRequest, MergeCustomerRequest, UpdateCustomerStatusRequest
from app.services.customer_service import CustomerService
from app.services.customer_identity_service import CustomerIdentityService
from app.services.membership_service import MembershipService


class CustomerIdentityContractsTest(unittest.TestCase):
    def test_identity_model_is_tenant_scoped(self):
        self.assertTrue(issubclass(CustomerIdentity, TenantBaseModel))
        self.assertTrue(hasattr(CustomerIdentity, "tenant_id"))
        self.assertTrue(hasattr(CustomerIdentity, "customer_id"))
        self.assertTrue(hasattr(CustomerIdentity, "channel"))
        self.assertTrue(hasattr(CustomerIdentity, "channel_user_id"))

    def test_identity_service_requires_tenant_before_binding(self):
        service = CustomerIdentityService(db=None)

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(service.bind_identity(
                customer_id=1,
                channel="phone",
                channel_user_id="13800000000",
            ))

        self.assertEqual(str(ctx.exception), "tenant_id is required for tenant-scoped operations")

    def test_customer_model_supports_status_and_soft_delete(self):
        self.assertTrue(hasattr(Customer, "status"))
        self.assertTrue(hasattr(Customer, "deleted_at"))

    def test_customer_phone_is_validated_when_present(self):
        request = CreateCustomerRequest(openid="manual-1", phone="13800000000")
        self.assertEqual(request.phone, "13800000000")

        with self.assertRaises(ValidationError):
            CreateCustomerRequest(openid="manual-1", phone="123")

    def test_customer_management_service_exposes_required_business_methods(self):
        for method_name in ["set_customer_status", "soft_delete_customer", "merge_customers", "list_customer_identities", "list_tags"]:
            with self.subTest(method=method_name):
                self.assertTrue(hasattr(CustomerService, method_name))
                self.assertTrue(inspect.iscoroutinefunction(getattr(CustomerService, method_name)))

    def test_customer_status_and_merge_request_contracts(self):
        self.assertEqual(UpdateCustomerStatusRequest(status=0).status, 0)
        self.assertEqual(MergeCustomerRequest(source_customer_id=1, target_customer_id=2).target_customer_id, 2)

        with self.assertRaises(ValidationError):
            UpdateCustomerStatusRequest(status=9)

        with self.assertRaises(ValidationError):
            MergeCustomerRequest(source_customer_id=1, target_customer_id=1)

    def test_membership_core_models_are_tenant_scoped(self):
        for model in [MemberAccount, PointLedger, BenefitTemplate]:
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, TenantBaseModel))
                self.assertTrue(hasattr(model, "tenant_id"))

    def test_membership_config_uses_three_levels_and_unified_rules(self):
        config = MembershipService(db=None).get_config()

        self.assertEqual([item["code"] for item in config["levels"]], ["LV1", "LV2", "LV3"])
        self.assertEqual(config["levels"][1]["threshold"], 299)
        self.assertEqual(config["levels"][2]["threshold"], 999)
        self.assertTrue(config["principles"]["single_points_account"])
        self.assertEqual(config["points"]["redeem"]["points_per_yuan"], 100)
        self.assertEqual(config["points"]["redeem"]["max_order_discount_rate"], 0.3)

    def test_membership_level_resolution_supports_upgrade_thresholds(self):
        service = MembershipService(db=None)

        self.assertEqual(service.resolve_level(0)["code"], "LV1")
        self.assertEqual(service.resolve_level(299)["code"], "LV2")
        self.assertEqual(service.resolve_level(999)["code"], "LV3")


if __name__ == "__main__":
    unittest.main()
