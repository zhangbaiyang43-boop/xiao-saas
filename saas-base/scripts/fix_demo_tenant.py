"""Bring one tenant into the shape the linked Demo needs.

Sets, on exactly one tenant row:
    status          -> 1 (enabled)
    payment_mode    -> 'postpay'   (customer checkout never invokes real WeChat Pay)
    wx_pay_enabled  -> 0           (demo tenant can't take real money)

DRY-RUN BY DEFAULT -- prints the planned before/after and writes nothing.
Pass --apply to actually run the UPDATE. No other columns, rows, or side
effects are touched. Safe to run repeatedly (idempotent).

    cd /www/wwwroot/xiao/saas-base && source venv/bin/activate
    python /tmp/fix_demo_tenant.py demo            # preview
    python /tmp/fix_demo_tenant.py demo --apply    # write
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

for _cand in (Path(__file__).resolve().parents[1], Path.cwd(), Path.cwd().parent):
    if (_cand / "app" / "config.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

TARGET = {"status": 1, "payment_mode": "postpay", "wx_pay_enabled": 0}


async def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        raise SystemExit("用法: python scripts/fix_demo_tenant.py <tenant_id> [--apply]")
    tenant_id = positional[0].strip()

    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT tenant_id, name, status, payment_mode, wx_pay_enabled "
                    "FROM tenant WHERE tenant_id = :tid"
                ),
                {"tid": tenant_id},
            )
        ).mappings().first()

    if row is None:
        await engine.dispose()
        raise SystemExit(f"租户不存在: tenant_id = {tenant_id}")

    print("=" * 60)
    print(f"租户  {row['tenant_id']}  {row['name']!r}")
    print("=" * 60)
    changes = []
    for col, want in TARGET.items():
        have = row[col]
        have_norm = int(have) if isinstance(have, bool) or col != "payment_mode" else have
        same = (str(have_norm).lower() == str(want).lower())
        flag = "已符合" if same else "将修改"
        print(f"  {col:<15} 现在 = {have!r:<12} 目标 = {want!r:<10} [{flag}]")
        if not same:
            changes.append(col)

    if not changes:
        print("\n三项都已符合，无需修改。")
        await engine.dispose()
        return

    if not apply:
        print(f"\n[DRY-RUN] 需要修改 {len(changes)} 项：{', '.join(changes)}")
        print("确认无误后加 --apply 实际写入。")
        await engine.dispose()
        return

    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "UPDATE tenant SET status = :s, payment_mode = :p, wx_pay_enabled = :w "
                "WHERE tenant_id = :tid"
            ),
            {"s": TARGET["status"], "p": TARGET["payment_mode"],
             "w": TARGET["wx_pay_enabled"], "tid": tenant_id},
        )

    async with engine.connect() as conn:
        after = (
            await conn.execute(
                sa.text(
                    "SELECT status, payment_mode, wx_pay_enabled FROM tenant WHERE tenant_id = :tid"
                ),
                {"tid": tenant_id},
            )
        ).mappings().first()
    await engine.dispose()

    print(f"\n[APPLIED] 已更新 tenant_id = {tenant_id}")
    print(f"  status={after['status']}  payment_mode={after['payment_mode']!r}  "
          f"wx_pay_enabled={after['wx_pay_enabled']}")
    print("重新跑 check_demo_tenant.py 复核。")


if __name__ == "__main__":
    asyncio.run(main())
