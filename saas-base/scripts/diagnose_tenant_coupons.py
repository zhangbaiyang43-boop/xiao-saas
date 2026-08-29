"""Read-only: show exactly what the auto-coupon engine computes for a tenant.

Why: a full-service restaurant (火锅/烧烤/羊肉馆) with a wide menu and few
orders can get classified into the micro band (AOV <= 20), which by design
(AUTO_MARKETING_STRATEGY_SPEC P0-3) issues **无门槛 (threshold 0)** coupons.
This dumps every input and output of that decision so we can see whether
that is what happened, and why.

READ-ONLY: SELECT queries + pure in-memory calls into CouponService /
platform_rules. No coupon is issued, nothing is written, no transaction is
committed.

    cd /www/wwwroot/xiao/saas-base && source venv/bin/activate
    python scripts/diagnose_tenant_coupons.py <tenant_id> [顾客手机号]
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

from app.core.database import AsyncSessionLocal
from app.core import platform_rules as PR
from app.services.coupon_service import CouponService


def fmt_coupons(rule):
    out = []
    for c in (rule.get("weighted_coupons") or []):
        out.append(
            f"      {c.get('name','?'):<12} 面额¥{c.get('amount',0):<5} "
            f"门槛¥{c.get('threshold',0):<6} {c.get('valid_days','?')}天 "
            f"weight={c.get('weight','?')}"
            + ("   <-- 无门槛" if float(c.get('threshold', 0) or 0) == 0 else "")
        )
    return "\n".join(out)


async def main() -> None:
    args = [a for a in sys.argv[1:]]
    if not args:
        raise SystemExit("用法: python scripts/diagnose_tenant_coupons.py <tenant_id> [顾客手机号]")
    tenant_id = args[0].strip()
    phone = args[1].strip() if len(args) > 1 else None

    async with AsyncSessionLocal() as db:
        trow = (
            await db.execute(
                sa.text("SELECT name, status FROM tenant WHERE tenant_id = :t"), {"t": tenant_id}
            )
        ).first()
        if trow is None:
            raise SystemExit(f"租户不存在: {tenant_id}")
        print("=" * 70)
        print(f"租户 {tenant_id}  {trow[0]!r}  status={bool(trow[1])}")
        print("=" * 70)

        svc = CouponService(db)
        svc.set_tenant_id(tenant_id)

        avg_val, order_count = await svc._recent_order_stats()
        menu_est = await svc._menu_price_estimate()
        industry = await svc.get_industry()
        intensity = await svc.get_marketing_intensity()
        aov = await svc.get_merchant_aov()

        # menu price distribution
        prices = [
            float(p) for (p,) in (
                await db.execute(
                    sa.text(
                        "SELECT price FROM menu_items "
                        "WHERE tenant_id = :t AND available = 1 AND price > 0 ORDER BY price"
                    ),
                    {"t": tenant_id},
                )
            ).all() if p
        ]
        if prices:
            n = len(prices)
            def pct(q):
                i = min(n - 1, int(q * n))
                return prices[i]
            print(f"菜单在售 {n} 道:  最低¥{prices[0]}  p25¥{pct(.25)}  "
                  f"中位¥{pct(.5)}  p75¥{pct(.75)}  最高¥{prices[-1]}  "
                  f"均值¥{round(sum(prices)/n,1)}")
        else:
            print("菜单在售 0 道（价格>0）")

        print(f"\n近30天有效订单: {order_count} 单   实付+折扣口径均值 AOV: ¥{round(avg_val,1)}")
        print(f"冷启动菜单估价 (中位×1.2): ¥{menu_est}")
        print(f"业态 industry = {industry!r}  ({PR.INDUSTRY_PRESETS[industry]['label']}, "
              f"fallback_aov ¥{PR.INDUSTRY_PRESETS[industry]['fallback_aov']})")
        print(f"营销强度 intensity = {intensity!r}")
        print(f"\n>>> 引擎实际采用的 AOV = ¥{round(aov,2)}   "
              f"(≥{PR.AOV_MIN_ORDERS}单用真实均值，否则用菜单估价，无菜单用业态兜底)")
        micro = (aov or 0) <= PR.MICRO_BAND_MAX
        print(f">>> 落入 {'micro 带 (≤¥%.0f) —— 进店券/新客券/召回券会发【无门槛】' % PR.MICRO_BAND_MAX if micro else '正常带 (>¥%.0f) —— 全部带门槛' % PR.MICRO_BAND_MAX}")

        rules = await svc.get_coupon_rules()
        print("\n--- 引擎当前会发的券 (get_coupon_rules 实时结果) ---")
        for key in ("entry_coupon", "new_customer_coupon", "consumption_coupon", "recall_coupon"):
            r = rules.get(key, {})
            print(f"  {key}  enabled={r.get('enabled')}")
            body = fmt_coupons(r)
            if body:
                print(body)

        # merchant override layer
        from app.services.tenant_service import TenantService
        cfg = await TenantService(db).get_tenant_config(tenant_id)
        ci = (cfg.coupon_rules if cfg else None) or {}
        locked = [k for k, v in ci.items() if isinstance(v, dict) and v.get("locked")]
        print(f"\n商户 coupon_rules 覆盖层: keys={list(ci.keys()) or '空'}  locked={locked or '无'}")
        tuning = (cfg.business_info or {}).get("coupon_tuning") if cfg else None
        print(f"核销率闭环调参 coupon_tuning: {tuning or '无'}")

        if phone:
            crow = (
                await db.execute(
                    sa.text("SELECT id FROM customer WHERE tenant_id = :t AND phone = :p"),
                    {"t": tenant_id, "p": phone},
                )
            ).first()
            if crow is None:
                print(f"\n顾客 {phone}: 该租户下没有这个手机号")
            else:
                cid = crow[0]
                held = (
                    await db.execute(
                        sa.text(
                            """
                            SELECT c.status, c.source, c.expire_time,
                                   t.name, t.value, t.min_amount, t.coupon_type, t.description
                            FROM coupon c JOIN coupon_template t ON t.id = c.template_id
                            WHERE c.tenant_id = :t AND c.customer_id = :cid
                            ORDER BY c.created_at DESC LIMIT 30
                            """
                        ),
                        {"t": tenant_id, "cid": cid},
                    )
                ).all()
                print(f"\n顾客 {phone} (id={cid}) 名下的券 (最近30张):")
                for st, src, exp, tn, val, minamt, ctype, desc in held:
                    flag = "  <-- 无门槛" if float(minamt or 0) == 0 and ctype != "PERCENT" else ""
                    print(f"  [{st}] {tn!r}  {ctype} 面额{val} 门槛¥{minamt}  "
                          f"source={src!r} desc={desc!r} 到期={exp}{flag}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
