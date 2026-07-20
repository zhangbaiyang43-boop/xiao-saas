import asyncio
import json
import unittest

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel as PydanticBaseModel, ValidationError
from starlette.requests import Request

from app.core.exceptions import validation_exception_handler
from app.core.response import error_response, success_response
from app.core import cache_helper
from app.core import lock as lock_module
from app.main import health_check, read_root
from app.middleware.auth_middleware import AuthMiddleware
from app.models.base import BaseModel as TenantBaseModel
from app.models.consumption import Consumption
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.tenant_plugin import TenantPlugin
from app.models.tenant_config import TenantConfig
from app.models.customer_identity import CustomerIdentity
from app.services.customer_service import CustomerService
from app.services.base_service import BaseService


def make_request(path="/api/v1/customers"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class Payload(PydanticBaseModel):
    name: str


class CoreContractsTest(unittest.TestCase):
    def test_success_and_error_responses_use_respvo_shape(self):
        self.assertEqual(success_response({"ok": True}).model_dump(), {
            "code": 200,
            "msg": "ok",
            "data": {"ok": True},
        })
        self.assertEqual(error_response(401, "未登录").model_dump(), {
            "code": 401,
            "msg": "未登录",
            "data": None,
        })

    def test_root_and_health_use_respvo_shape(self):
        self.assertEqual(read_root().model_dump(), {
            "code": 200,
            "msg": "ok",
            "data": {"message": "Multi-tenant Member Management SaaS API"},
        })
        self.assertEqual(health_check().model_dump(), {
            "code": 200,
            "msg": "ok",
            "data": {"status": "healthy"},
        })

    def test_auth_middleware_returns_readable_respvo_for_missing_token(self):
        middleware = AuthMiddleware(app=None)

        async def call_next(request):
            self.fail("protected request without token should not continue")

        response = asyncio.run(middleware.dispatch(make_request("/api/v1/customers"), call_next))
        body = json.loads(response.body.decode("utf-8"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(body, {
            "code": 401,
            "msg": "未登录或登录已过期",
            "data": None,
        })

    def test_auth_middleware_allows_docs_routes(self):
        middleware = AuthMiddleware(app=None)

        async def call_next(request):
            return success_response({"path": request.url.path})

        response = asyncio.run(middleware.dispatch(make_request("/openapi.json"), call_next))

        self.assertFalse(hasattr(response, "body"))
        self.assertEqual(response.data, {"path": "/openapi.json"})

    def test_validation_handler_returns_readable_respvo(self):
        try:
            Payload(name=123)
        except ValidationError as exc:
            response = asyncio.run(validation_exception_handler(make_request(), RequestValidationError(exc.errors())))
        else:
            self.fail("validation should fail")

        self.assertEqual(response.status_code, 422)
        body = json.loads(response.body.decode("utf-8"))
        self.assertEqual(body["code"], 422)
        self.assertEqual(body["msg"], "参数校验失败")
        self.assertIsInstance(body["data"], list)

    def test_base_service_requires_tenant_before_filtering(self):
        service = BaseService(db=None)

        with self.assertRaises(ValueError) as ctx:
            service.filter_by_tenant(object(), Customer)

        self.assertEqual(str(ctx.exception), "tenant_id is required for tenant-scoped queries")

    def test_business_models_inherit_base_model(self):
        for model in [Customer, CustomerIdentity, Consumption, CouponTemplate, Coupon, TenantPlugin, TenantConfig]:
            with self.subTest(model=model.__name__):
                self.assertTrue(issubclass(model, TenantBaseModel))
                self.assertTrue(hasattr(model, "tenant_id"))

    def test_customer_service_requires_tenant_before_create(self):
        service = CustomerService(db=None)

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(service.create_customer("openid-1", name="测试客户"))

        self.assertEqual(str(ctx.exception), "tenant_id is required for tenant-scoped operations")

    def test_cache_degrades_to_underlying_function_when_redis_is_unavailable(self):
        class BrokenRedis:
            async def get(self, key):
                raise OSError("redis down")

            async def setex(self, key, ttl, value):
                raise OSError("redis down")

        original = cache_helper.redis_client
        cache_helper.redis_client = BrokenRedis()
        calls = {"count": 0}

        @cache_helper.cache_result("demo")
        async def load_value():
            calls["count"] += 1
            return success_response({"value": 1})

        try:
            result = asyncio.run(load_value())
        finally:
            cache_helper.redis_client = original

        self.assertEqual(calls["count"], 1)
        self.assertEqual(result.data, {"value": 1})

    def test_redis_lock_reports_clear_error_when_redis_is_unavailable(self):
        class BrokenRedis:
            async def set(self, *args, **kwargs):
                raise OSError("redis down")

        original = lock_module.redis_client
        lock_module.redis_client = BrokenRedis()

        async def acquire():
            async with lock_module.redis_lock("verify:code") as acquired:
                return acquired

        try:
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(acquire())
        finally:
            lock_module.redis_client = original

        self.assertEqual(str(ctx.exception), "Redis is unavailable, cannot acquire distributed lock")


if __name__ == "__main__":
    unittest.main()
