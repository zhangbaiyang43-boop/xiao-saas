from app.schemas.tenant import TenantSchema, LoginRequest, RegisterRequest
from app.schemas.customer import CustomerSchema, CreateCustomerRequest, UpdateCustomerRequest
from app.schemas.consumption import ConsumptionSchema, CreateConsumptionRequest
from app.schemas.coupon import CouponTemplateSchema, CreateCouponTemplateRequest, SendCouponsRequest, CouponSchema

__all__ = [
    'TenantSchema', 'LoginRequest', 'RegisterRequest',
    'CustomerSchema', 'CreateCustomerRequest', 'UpdateCustomerRequest',
    'ConsumptionSchema', 'CreateConsumptionRequest',
    'CouponTemplateSchema', 'CreateCouponTemplateRequest', 'SendCouponsRequest', 'CouponSchema'
]