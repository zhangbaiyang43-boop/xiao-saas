import asyncio
import unittest

from app.api.v1.marketing_templates import get_marketing_template_detail, get_merchant_templates

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class MarketingTemplatesMerchantOnlyTest(unittest.IsolatedAsyncioTestCase):
    """These two GET endpoints used to only require Depends(get_current_user), which
    accepts any authenticated token type (including a customer/member token), while the
    mutating endpoints in the same file (enable/disable) already required type=="merchant".
    A logged-in mini-program customer could read a merchant's enabled marketing-template
    config (get_merchant_templates) or a template's rule detail (get_marketing_template_detail)
    that's otherwise only meant for the merchant admin console. db=None is safe here because
    the fix must reject before either function ever touches the database.
    """

    async def test_get_merchant_templates_rejects_non_merchant_token(self):
        result = await get_merchant_templates(db=None, user={"type": "member", "tenant_id": "tenant-a"})
        self.assertEqual(result.code, 401)

    async def test_get_marketing_template_detail_rejects_non_merchant_token(self):
        result = await get_marketing_template_detail(
            template_id=1, db=None, user={"type": "member", "tenant_id": "tenant-a"}
        )
        self.assertEqual(result.code, 401)

    async def test_get_merchant_templates_rejects_missing_type(self):
        result = await get_merchant_templates(db=None, user={"tenant_id": "tenant-a"})
        self.assertEqual(result.code, 401)


if __name__ == "__main__":
    unittest.main()
