from app.api.v1.coupon_templates import router as coupon_template_router
from app.api.v1.coupons import router as coupon_router
from app.api.v1.verify import router as verify_router
from app.plugins.base_plugin import BasePlugin


class CouponPlugin(BasePlugin):
    plugin_code = "coupon"

    @property
    def plugin_name(self) -> str:
        return "优惠券"

    @property
    def description(self) -> str:
        return "提供优惠券模、发放和核销能力"

    async def install(self, tenant_id: str):
        pass

    async def uninstall(self, tenant_id: str):
        pass

    def get_routers(self):
        return [coupon_template_router, coupon_router, verify_router]

    def get_frontend_pages(self):
        return [
            {
                "path": "subpkg-member/pages/coupons",
                "title": "我的优惠券"
            },
            {
                "path": "subpkg-member/pages/coupon-detail",
                "title": "优惠券详情"
            }
        ]
