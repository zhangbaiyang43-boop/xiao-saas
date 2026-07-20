from app.api.auth import router as auth_router
from app.api.customer import router as customer_router
from app.api.consumption import router as consumption_router
from app.api.coupon_template import router as coupon_template_router
from app.api.coupon import router as coupon_router

__all__ = [
    'auth_router',
    'customer_router',
    'consumption_router',
    'coupon_template_router',
    'coupon_router',
]