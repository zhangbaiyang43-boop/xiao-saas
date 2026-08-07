from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.order import Order, OrderItem


async def _restore_order_stock(order: Order, db: AsyncSession) -> None:
    """Give back whatever stock create_order deducted (see its item loop, dish.stock -=)
    when an order ends up cancelled/rejected/timed-out without ever being fulfilled -- otherwise
    a dish that was never actually cooked/sold stays wrongly marked "sold out" forever, and
    the shortfall only grows with every abandoned order. Locks each MenuItem row first so a
    concurrent order for the same dish can't race the restore.

    Must be called with `order` already locked (with_for_update) in the current transaction,
    before the order's status is flipped away from pending_payment/pending.
    """
    from app.models.menu_item import MenuItem

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    order_items = items_result.scalars().all()
    qty_by_dish_id: dict[int, int] = {}
    for item in order_items:
        if item.dish_id is not None:
            qty_by_dish_id[item.dish_id] = qty_by_dish_id.get(item.dish_id, 0) + int(item.qty or 0)
    if not qty_by_dish_id:
        return

    dishes_result = await db.execute(
        select(MenuItem).where(MenuItem.id.in_(qty_by_dish_id.keys())).with_for_update()
    )
    for dish in dishes_result.scalars().all():
        dish_id = dish.id
        if dish_id is not None and dish.stock is not None:
            dish.stock = dish.stock + qty_by_dish_id.get(dish_id, 0)
