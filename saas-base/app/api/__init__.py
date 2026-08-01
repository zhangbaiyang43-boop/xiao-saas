from app.api.auth import router as auth_router
from app.api.customer import router as customer_router
from app.api.consumption import router as consumption_router

__all__ = [
    'auth_router',
    'customer_router',
    'consumption_router',
]