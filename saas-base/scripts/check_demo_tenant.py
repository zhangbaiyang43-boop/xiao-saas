"""Read-only readiness check for the linked-Demo tenant (DEMO_TENANT_ID).

Verifies, against the LIVE database, whether a given tenant can safely be
used as the isolated Demo tenant:

  * tenant exists and is enabled
  * collection mode is post-pay  (so the customer checkout never invokes
    real WeChat Pay during a demo)
  * no real printer bound        (feieyun_sn / feieyun_key empty)
  * WeChat Pay not enabled on the tenant
  * has at least one available menu item
  * has 20 usable  channel=DEMO / entry_type=table / status=1  entrance
    codes, each with a table_no and an image_url (the customer QR image)
  * shows which tenant plugins (coupon / points / distribution ...) are
    currently enabled, and whether tenant_config carries coupon/member rules

READ-ONLY: opens a plain connection (never a transaction), runs SELECT
statements only -- no INSERT / UPDATE / DELETE, no DDL. Safe to run
repeatedly. It never prints secrets (only presence/absence of key fields).

Usage on the server (uses the app's own .env DATABASE_URL):

    cd /www/wwwroot/xiao/saas-base
    source venv/bin/activate
    python scripts/check_demo_tenant.py <tenant_id>

If <tenant_id> is omitted it falls back to settings.DEMO_TENANT_ID.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make `app` importable no matter where this file is dropped / how it's run:
# try the repo layout (scripts/..), then the current working dir and its
# parent. Whichever actually contains app/config.py wins.
for _cand in (
    Path(__file__).resolve().parents[1],
    Path.cwd(),
    Path.cwd().parent,
):
    if (_cand / "app" / "config.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break

try:  # this report is Chinese-heavy; don't let a non-UTF-8 console mangle it
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

REQUIRED_POOL = 20


def mark(ok: bool | None) -> str:
    if ok is True:
        return "[ OK ]"
    if ok is False:
        return "[FAIL]"
    return "[warn]"


async def find_tenants(keyword: str) -> None:
    """List tenants whose name matches, to help locate the demo tenant_id."""
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    """
                    SELECT tenant_id, name, status, payment_mode, created_at
                    FROM tenant
                    WHERE name LIKE :kw
                    ORDER BY created_at
                    LIMIT 50
                    """
                ),
                {"kw": f"%{keyword}%"},
            )
        ).all()
    await engine.dispose()
    if not rows:
        print(f"没有 name 含 '{keyword}' 的租户")
        return
    print(f"name 含 '{keyword}' 的租户 (tenant_id | name | status | payment_mode | 注册时间):")
    for tid, name, status, pm, created in rows:
        print(f"  {tid:<20} | {name!r:<24} | status={bool(status)} | {pm} | {created}")
    print("\n拿到 tenant_id 后: python scripts/check_demo_tenant.py <tenant_id>")


async def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--find":
        await find_tenants(args[1] if len(args) > 1 else "演示")
        return

    tenant_id = (args[0] if args else settings.DEMO_TENANT_ID or "").strip()
    if not tenant_id:
        raise SystemExit(
            "用法:\n"
            "  python scripts/check_demo_tenant.py <tenant_id>       # 检查某个租户\n"
            "  python scripts/check_demo_tenant.py --find [关键词]    # 按店名找 tenant_id（默认关键词 演示）\n"
            "  (不带参数时读取 .env 的 DEMO_TENANT_ID)"
        )

    configured = (settings.DEMO_TENANT_ID or "").strip()
    verdict_fail = False

    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        print("=" * 64)
        print(f"演示租户检查  tenant_id = {tenant_id}")
        if configured and configured != tenant_id:
            print(f"注意: .env 里的 DEMO_TENANT_ID 目前是 '{configured}'，与本次检查的不一致")
        elif not configured:
            print("注意: .env 尚未配置 DEMO_TENANT_ID")
        print("=" * 64)

        row = (
            await conn.execute(
                sa.text(
                    """
                    SELECT tenant_id, name, status, is_open, payment_mode,
                           wx_pay_enabled, feieyun_sn, feieyun_key,
                           receiver_name, payment_locked
                    FROM tenant WHERE tenant_id = :tid
                    """
                ),
                {"tid": tenant_id},
            )
        ).mappings().first()

        if row is None:
            print(f"{mark(False)} 租户不存在  (tenant 表里没有 tenant_id = {tenant_id})")
            print("\n结论: NOT READY —— 换一个正确的 tenant_id")
            await engine.dispose()
            raise SystemExit(1)

        status_ok = bool(row["status"])
        verdict_fail |= not status_ok
        print(f"{mark(status_ok)} 租户启用 status = {bool(row['status'])}   营业开关 is_open = {bool(row['is_open'])}")
        print(f"       店名 name = {row['name']!r}   (工作台标题会显示这个)")

        pm = (row["payment_mode"] or "").strip()
        pm_ok = pm == "postpay"
        verdict_fail |= not pm_ok
        hint = "" if pm_ok else "  <-- 需要改成 postpay，否则顾客结算会唤起真实微信支付"
        print(f"{mark(pm_ok)} 收款模式 payment_mode = {pm!r}{hint}")

        wx_on = bool(row["wx_pay_enabled"])
        print(f"{mark(not wx_on)} 微信支付 wx_pay_enabled = {wx_on}"
              + ("" if not wx_on else "  <-- 建议关掉，演示不应能真实收款"))
        verdict_fail |= wx_on

        sn = (row["feieyun_sn"] or "").strip()
        key = (row["feieyun_key"] or "").strip()
        printer_clean = not sn and not key
        verdict_fail |= not printer_clean
        print(f"{mark(printer_clean)} 打印机 feieyun_sn={'已配置' if sn else '空'}  "
              f"feieyun_key={'已配置' if key else '空'}"
              + ("" if printer_clean else "  <-- 必须清空，否则顾客下单会真实出票"))

        # ---- menu ----
        menu_available = (
            await conn.execute(
                sa.text("SELECT COUNT(*) FROM menu_items WHERE tenant_id = :tid AND available = 1"),
                {"tid": tenant_id},
            )
        ).scalar_one()
        menu_total = (
            await conn.execute(
                sa.text("SELECT COUNT(*) FROM menu_items WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        ).scalar_one()
        menu_ok = menu_available > 0
        verdict_fail |= not menu_ok
        print(f"{mark(menu_ok)} 可点菜品 {menu_available} 个上架 / {menu_total} 个总计")

        # ---- DEMO entrance-code pool ----
        pool_total = (
            await conn.execute(
                sa.text(
                    """
                    SELECT COUNT(*) FROM entrance_code
                    WHERE tenant_id = :tid AND channel = 'DEMO'
                      AND entry_type = 'table' AND status = 1
                    """
                ),
                {"tid": tenant_id},
            )
        ).scalar_one()
        pool_valid = (
            await conn.execute(
                sa.text(
                    """
                    SELECT COUNT(*) FROM entrance_code
                    WHERE tenant_id = :tid AND channel = 'DEMO'
                      AND entry_type = 'table' AND status = 1
                      AND table_no IS NOT NULL AND table_no <> ''
                      AND image_url IS NOT NULL AND image_url <> ''
                    """
                ),
                {"tid": tenant_id},
            )
        ).scalar_one()
        pool_ok = pool_valid >= REQUIRED_POOL
        verdict_fail |= not pool_ok
        print(f"{mark(pool_ok)} 演示桌码 channel=DEMO/table/status=1: "
              f"{pool_total} 张，其中可用(有 table_no+image_url) {pool_valid} 张  "
              f"(需要 >= {REQUIRED_POOL})")

        if pool_total:
            sample = (
                await conn.execute(
                    sa.text(
                        """
                        SELECT table_no, generation_status,
                               CASE WHEN image_url IS NULL OR image_url = '' THEN 0 ELSE 1 END AS has_img
                        FROM entrance_code
                        WHERE tenant_id = :tid AND channel = 'DEMO'
                          AND entry_type = 'table' AND status = 1
                        ORDER BY table_no, id LIMIT 25
                        """
                    ),
                    {"tid": tenant_id},
                )
            ).all()
            print("       桌码明细 (table_no | 生成状态 | 有图):")
            for t_no, gen, has_img in sample:
                print(f"         {str(t_no or '(空)'):<10} | {gen:<8} | {'是' if has_img else '否'}")

        # ---- enabled plugins (best-effort) ----
        try:
            plugins = (
                await conn.execute(
                    sa.text(
                        """
                        SELECT plugin_code, lifecycle_status
                        FROM tenant_plugin
                        WHERE tenant_id = :tid AND status = 1
                        ORDER BY plugin_code
                        """
                    ),
                    {"tid": tenant_id},
                )
            ).all()
            if plugins:
                joined = ", ".join(f"{code}({life})" for code, life in plugins)
                print(f"{mark(None)} 已启用插件: {joined}")
                print("       演示租户不应启用自动发券/积分/佣金/分销类插件，请人工确认上面这些是否可接受")
            else:
                print(f"{mark(True)} 已启用插件: 无")
        except Exception as exc:  # pragma: no cover - diagnostics only
            print(f"{mark(None)} 插件检查跳过 ({exc})")

        # ---- tenant_config rules (best-effort) ----
        try:
            cfg = (
                await conn.execute(
                    sa.text(
                        "SELECT coupon_rules, member_rules FROM tenant_config WHERE tenant_id = :tid"
                    ),
                    {"tid": tenant_id},
                )
            ).mappings().first()
            if cfg is None:
                print(f"{mark(True)} tenant_config: 无记录")
            else:
                cr = cfg["coupon_rules"]
                mr = cfg["member_rules"]
                cr_empty = cr in (None, "", "{}", {}, "null")
                mr_empty = mr in (None, "", "{}", {}, "null")
                print(f"{mark(None if not (cr_empty and mr_empty) else True)} "
                      f"tenant_config: coupon_rules={'空' if cr_empty else '有内容'}  "
                      f"member_rules={'空' if mr_empty else '有内容'}")
                if not (cr_empty and mr_empty):
                    print("       有营销/会员规则，人工确认不会在演示中产生真实发券或积分")
        except Exception as exc:  # pragma: no cover - diagnostics only
            print(f"{mark(None)} tenant_config 检查跳过 ({exc})")

        # ---- live OPEN dining sessions (runtime, informational) ----
        try:
            open_sessions = (
                await conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM dining_sessions WHERE tenant_id = :tid AND status = 'OPEN'"
                    ),
                    {"tid": tenant_id},
                )
            ).scalar_one()
            print(f"{mark(None)} 当前该租户 OPEN 状态的餐桌会话: {open_sessions} 个 (信息项，不影响判断)")
        except Exception as exc:  # pragma: no cover - diagnostics only
            print(f"{mark(None)} 会话检查跳过 ({exc})")

    await engine.dispose()

    print("=" * 64)
    if verdict_fail:
        print("结论: NOT READY —— 上面标 [FAIL] 的项要先处理")
        raise SystemExit(1)
    print("结论: 硬性条件通过。仍需人工确认标 [warn] 的插件/营销规则项。")
    print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())
