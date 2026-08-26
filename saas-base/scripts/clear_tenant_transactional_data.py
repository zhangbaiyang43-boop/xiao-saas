"""清空一个商户名下的"经营/测试数据"，保留菜单（menu_items）和商户账号本身。

使用场景：某个商户此前用于测试/演示（下过测试订单、加过测试会员、发过测试优惠券等），
现在菜单已经是真实数据了，准备正式上线，需要把除菜单外的其他数据清空为干净状态。

清空范围（按 tenant_id 过滤）：
    订单相关   orders / order_items / order_reviews / staff_assisted_payment_handoffs /
              pickup_no_assignments / dining_sessions / dining_participants
    会员相关   customer / customer_identity / customer_operation_log / member_account /
              point_ledger / consumption / commission_record
    优惠券     coupon / coupon_template
    入口/渠道  entrance_code / entrance_scan_log / channel_entry / channel_entry_visit_log
    其他       queue_tickets / staff

明确保留：menu_items（菜单/菜品）、dish_library_item（公共菜品库，本就不挂 tenant_id）、
tenant 本身（商户账号/登录信息不动）。

用法（默认只是 dry-run，打印每张表会受影响的行数，不会真的删除任何数据）：

    cd saas-base && source venv/bin/activate
    python scripts/clear_tenant_transactional_data.py <tenant_id>

确认无误后加 --confirm 才会真正执行删除（整个过程在一个事务里，任何一步失败整体回滚）：

    python scripts/clear_tenant_transactional_data.py <tenant_id> --confirm
"""
from __future__ import annotations

import argparse
import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

# 会先把 orders.parent_order_id 置空，再按这个顺序删除，保证不违反外键约束。
# 每一项：(表名, WHERE 子句, 参数占位符沿用 :tenant_id)
DELETE_STEPS = [
    ("order_items", "order_id IN (SELECT id FROM orders WHERE tenant_id = :tenant_id)"),
    ("order_reviews", "order_id IN (SELECT id FROM orders WHERE tenant_id = :tenant_id)"),
    ("staff_assisted_payment_handoffs", "tenant_id = :tenant_id"),
    ("pickup_no_assignments", "tenant_id = :tenant_id"),
    ("orders", "tenant_id = :tenant_id"),
    ("dining_participants", "tenant_id = :tenant_id"),
    ("dining_sessions", "tenant_id = :tenant_id"),
    ("entrance_scan_log", "tenant_id = :tenant_id"),
    ("entrance_code", "tenant_id = :tenant_id"),
    ("channel_entry_visit_log", "tenant_id = :tenant_id"),
    ("channel_entry", "tenant_id = :tenant_id"),
    ("coupon", "tenant_id = :tenant_id"),
    ("consumption", "tenant_id = :tenant_id"),
    ("customer_identity", "tenant_id = :tenant_id"),
    ("customer_operation_log", "tenant_id = :tenant_id"),
    ("point_ledger", "tenant_id = :tenant_id"),
    ("member_account", "tenant_id = :tenant_id"),
    ("commission_record", "tenant_id = :tenant_id"),
    ("queue_tickets", "tenant_id = :tenant_id"),
    ("customer", "tenant_id = :tenant_id"),
    ("coupon_template", "tenant_id = :tenant_id"),
    ("staff", "tenant_id = :tenant_id"),
]

PRESERVE_TABLES = ["menu_items"]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tenant_id", help="目标商户的 tenant_id（32 位字符串）")
    parser.add_argument("--confirm", action="store_true", help="真正执行删除；不加则只 dry-run 打印行数")
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        tenant_row = (
            await conn.execute(
                sa.text("SELECT tenant_id, name, phone FROM tenant WHERE tenant_id = :tenant_id"),
                {"tenant_id": args.tenant_id},
            )
        ).first()
        if not tenant_row:
            print(f"ABORT: 找不到 tenant_id={args.tenant_id} 对应的商户")
            await engine.dispose()
            return

        print(f"目标商户: tenant_id={tenant_row.tenant_id}  name={tenant_row.name}  phone={tenant_row.phone}")
        print()

        for table in PRESERVE_TABLES:
            count = (
                await conn.execute(
                    sa.text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tenant_id"),
                    {"tenant_id": args.tenant_id},
                )
            ).scalar_one()
            print(f"[保留不动] {table}: {count} 行")
        print()

        print("[将被清空]")
        total = 0
        for table, where in DELETE_STEPS:
            count = (
                await conn.execute(
                    sa.text(f"SELECT COUNT(*) FROM {table} WHERE {where}"),
                    {"tenant_id": args.tenant_id},
                )
            ).scalar_one()
            total += count
            print(f"  {table}: {count} 行")
        print(f"  合计: {total} 行")
        print()

        if not args.confirm:
            print("DRY_RUN_ONLY：以上是将被删除的行数，未做任何修改。确认无误后加 --confirm 重新执行。")
            await engine.dispose()
            return

        if total == 0:
            print("没有需要清空的数据，无需执行删除。")
            await engine.dispose()
            return

        async with engine.begin() as trx_conn:
            await trx_conn.execute(
                sa.text("UPDATE orders SET parent_order_id = NULL WHERE tenant_id = :tenant_id"),
                {"tenant_id": args.tenant_id},
            )
            for table, where in DELETE_STEPS:
                await trx_conn.execute(
                    sa.text(f"DELETE FROM {table} WHERE {where}"),
                    {"tenant_id": args.tenant_id},
                )
        print("DELETE_DONE：已在一个事务内清空以上数据，菜单数据未受影响。")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
