from app.core.events import DomainEvent
from app.services.customer_service import CustomerService
from app.services.membership_service import MembershipService


async def handle_consumption_membership(event: DomainEvent):
    customer_id = event.payload.get("customer_id")
    amount = event.payload.get("amount", 0)
    consumption_id = event.payload.get("consumption_id")
    consume_time = event.payload.get("consume_time")

    customer = await CustomerService(event.db).update_last_consume_time(customer_id, consume_time)
    if not customer:
        return {"skipped": True, "reason": "customer_not_found"}

    account = await MembershipService(event.db).apply_consumption(customer, float(amount), consumption_id)
    return {
        "customer_id": str(customer.id),
        "member_id": account.member_id,
        "level_code": account.level_code,
        "points_balance": account.points_balance,
    }
