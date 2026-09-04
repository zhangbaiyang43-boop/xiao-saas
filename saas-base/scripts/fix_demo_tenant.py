"""Bring one tenant into the shape the linked Demo needs.

Sets, on the `tenant` row:
    status          -> 1 (enabled)
    payment_mode    -> 'postpay'   (customer checkout never invokes real WeChat Pay)
    wx_pay_enabled  -> 0           (demo tenant can't take real money)

And, on the matching `tenant_config` row, turns OFF every auto-coupon switch:
    coupon_rules.new_customer_coupon.enabled -> false   (kills the菜单页
        "新客立减¥3，授权手机号立得" banner -- a dead end on the demo, since
        member login is blocked for the demo tenant)
    coupon_rules.entry_coupon.enabled        -> false   (silent进店券)
    coupon_rules.consumption_coupon.enabled  -> false   (复购券)
Other keys inside coupon_rules are left byte-for-byte untouched. If the tenant
has no tenant_config row, a minimal one is inserted.

DRY-RUN BY DEFAULT -- prints the planned before/after and writes nothing.
Pass --apply to actually write. Both the tenant UPDATE and the tenant_config
write happen in one transaction. Safe to run repeatedly (idempotent).

    cd /www/wwwroot/xiao/saas-base && source venv/bin/activate
    python scripts/fix_demo_tenant.py demo            # preview
    python scripts/fix_demo_tenant.py demo --apply    # write
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
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
from app.utils.id_generator import generate_snowflake_id

TARGET = {"status": 1, "payment_mode": "postpay", "wx_pay_enabled": 0}
COUPON_OFF_KEYS = ("new_customer_coupon", "entry_coupon", "consumption_coupon")


def _as_dict(raw) -> dict:
    """tenant_config.coupon_rules read via raw SQL -- may be dict / str / bytes / None."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _coupon_rules_after(current: dict) -> dict:
    out = json.loads(json.dumps(current))  # deep copy, keep every unrelated key
    for key in COUPON_OFF_KEYS:
        rule = out.get(key)
        if not isinstance(rule, dict):
            rule = {}
        rule["enabled"] = False
        out[key] = rule
    return out


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
        cfg = (
            await conn.execute(
                sa.text("SELECT id, coupon_rules FROM tenant_config WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        ).mappings().first()

    if row is None:
        await engine.dispose()
        raise SystemExit(f"租户不存在: tenant_id = {tenant_id}")

    print("=" * 60)
    print(f"租户  {row['tenant_id']}  {row['name']!r}")
    print("=" * 60)

    # ---- tenant table ----
    tenant_changes = []
    for col, want in TARGET.items():
        have = row[col]
        have_norm = int(have) if isinstance(have, bool) or col != "payment_mode" else have
        same = (str(have_norm).lower() == str(want).lower())
        print(f"  {col:<15} 现在 = {have!r:<12} 目标 = {want!r:<10} [{'已符合' if same else '将修改'}]")
        if not same:
            tenant_changes.append(col)

    # ---- tenant_config.coupon_rules ----
    current_rules = _as_dict(cfg["coupon_rules"]) if cfg else {}
    desired_rules = _coupon_rules_after(current_rules)
    coupon_changes = []
    print("  coupon_rules (自动发券开关):")
    for key in COUPON_OFF_KEYS:
        have = current_rules.get(key, {})
        have_enabled = bool(have.get("enabled", True)) if isinstance(have, dict) else True
        same = have_enabled is False
        print(f"    {key:<22} enabled 现在 = {have_enabled!s:<6} 目标 = False   [{'已符合' if same else '将关闭'}]")
        if not same:
            coupon_changes.append(key)
    if cfg is None:
        print("    (该租户没有 tenant_config 记录，--apply 时会插入一条最小记录)")

    if not tenant_changes and not coupon_changes and cfg is not None:
        print("\n全部已符合，无需修改。")
        await engine.dispose()
        return

    if not apply:
        todo = []
        if tenant_changes:
            todo.append(f"tenant 表 {len(tenant_changes)} 项：{', '.join(tenant_changes)}")
        if coupon_changes or cfg is None:
            todo.append("关闭自动发券开关：" + (", ".join(coupon_changes) or "(插入 tenant_config)"))
        print(f"\n[DRY-RUN] {' ; '.join(todo)}")
        print("确认无误后加 --apply 实际写入。")
        await engine.dispose()
        return

    now = datetime.utcnow()
    rules_json = json.dumps(desired_rules, ensure_ascii=False)
    async with engine.begin() as conn:
        if tenant_changes:
            await conn.execute(
                sa.text(
                    "UPDATE tenant SET status = :s, payment_mode = :p, wx_pay_enabled = :w "
                    "WHERE tenant_id = :tid"
                ),
                {"s": TARGET["status"], "p": TARGET["payment_mode"],
                 "w": TARGET["wx_pay_enabled"], "tid": tenant_id},
            )
        if cfg is None:
            await conn.execute(
                sa.text(
                    "INSERT INTO tenant_config "
                    "(id, tenant_id, member_rules, coupon_rules, business_info, plugin_settings, created_at, updated_at) "
                    "VALUES (:id, :tid, :empty, :cr, :empty, :empty, :now, :now)"
                ),
                {"id": generate_snowflake_id(), "tid": tenant_id, "empty": "{}",
                 "cr": rules_json, "now": now},
            )
        elif coupon_changes:
            await conn.execute(
                sa.text(
                    "UPDATE tenant_config SET coupon_rules = :cr, updated_at = :now "
                    "WHERE tenant_id = :tid"
                ),
                {"cr": rules_json, "now": now, "tid": tenant_id},
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
        after_cfg = (
            await conn.execute(
                sa.text("SELECT coupon_rules FROM tenant_config WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        ).mappings().first()
    await engine.dispose()

    after_rules = _as_dict(after_cfg["coupon_rules"]) if after_cfg else {}
    print(f"\n[APPLIED] 已更新 tenant_id = {tenant_id}")
    print(f"  status={after['status']}  payment_mode={after['payment_mode']!r}  "
          f"wx_pay_enabled={after['wx_pay_enabled']}")
    print("  自动发券开关: " + ", ".join(
        f"{k}={after_rules.get(k, {}).get('enabled')}" for k in COUPON_OFF_KEYS
    ))
    print("重新跑 check_demo_tenant.py 复核。")


if __name__ == "__main__":
    asyncio.run(main())
