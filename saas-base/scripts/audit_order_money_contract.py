"""只读：扫真实历史订单，逐单验证"不亏钱 / 金额算对了"的硬约束。

后端把 Order.total 存成实付（= 原价 − 券折扣），Order.discount_amount 存券折扣，
所以 原价 ≈ total + discount_amount。检查：

  1. 有折扣却没挂券 (discount_amount>0 且 coupon_id 为空) —— 凭空折扣
  2. 券折扣 > 原价 × 20% —— 结算红线 cap_discount_amount 没兜住
  3. total < 0 —— 实付为负
  4. coupon_id 指向的券不属于本单租户 —— 跨租户折扣
  5. refund_amount > total —— 退款超过实付
  6. 同一个非空 client_request_id 出现多次 —— 幂等唯一约束被绕过
  7. 疑似重复下单：同租户同桌会话、金额相同、60 秒内、都不是子单 —— 幂等可能漏了
     没传 client_request_id 的调用方（提示性，不算 FAIL）

只发 SELECT，不写库。

    cd /www/wwwroot/xiao/saas-base && source venv/bin/activate
    python scripts/audit_order_money_contract.py [tenant_id] [--days 30]

不带 tenant_id 扫全部租户；--days 默认 30。
"""
from __future__ import annotations

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
from app.config import settings

CAP_RATIO = 0.20
EPS = 0.011  # 分级四舍五入容差

_fail = 0
_warn = 0


def bad(label: str, rows) -> None:
    global _fail
    rows = list(rows)
    if rows:
        _fail += len(rows)
        print(f"[ FAIL ] {label} —— {len(rows)} 单")
        for r in rows[:15]:
            print(f"         order_id={r[0]}  " + "  ".join(f"{k}={v}" for k, v in zip(r._mapping.keys(), r._mapping.values()) if k != "id"))
        if len(rows) > 15:
            print(f"         … 还有 {len(rows) - 15} 单")
    else:
        print(f"[ PASS ] {label}")


def warn(label: str, rows) -> None:
    global _warn
    rows = list(rows)
    if rows:
        _warn += len(rows)
        print(f"[ warn ] {label} —— {len(rows)} 组，人工看一眼")
        for r in rows[:10]:
            print(f"         " + "  ".join(f"{k}={v}" for k, v in r._mapping.items()))
    else:
        print(f"[ PASS ] {label}")


def sync_url() -> str:
    return settings.DATABASE_URL.replace("mysql+asyncmy://", "mysql+pymysql://").replace("mysql+aiomysql://", "mysql+pymysql://")


def main() -> None:
    args = sys.argv[1:]
    days = 30
    if "--days" in args:
        try:
            days = int(args[args.index("--days") + 1])
        except (ValueError, IndexError):
            raise SystemExit("--days 后面要跟数字")
    tenant = next((a for a in args if not a.startswith("--") and not a.isdigit()), None)

    where = "o.created_at >= (NOW() - INTERVAL :days DAY) AND o.status NOT IN ('cancelled','rejected')"
    params = {"days": days}
    if tenant:
        where += " AND o.tenant_id = :t"
        params["t"] = tenant

    eng = sa.create_engine(sync_url(), pool_pre_ping=True)
    with eng.connect() as c:
        total = c.execute(sa.text(f"SELECT COUNT(*) FROM orders o WHERE {where}"), params).scalar_one()
        print("=" * 64)
        print(f"审计范围: {'租户 ' + tenant if tenant else '全部租户'}  近 {days} 天  有效订单 {total} 单")
        print("=" * 64)

        bad("1. 有折扣却没挂券（凭空折扣）",
            c.execute(sa.text(f"""
                SELECT o.id AS id, o.tenant_id, o.discount_amount, o.total, o.created_at
                FROM orders o WHERE {where}
                  AND COALESCE(o.discount_amount,0) > 0 AND o.coupon_id IS NULL
            """), params))

        bad("2. 券折扣 > 原价 × 20%（结算红线没兜住）",
            c.execute(sa.text(f"""
                SELECT o.id AS id, o.tenant_id, o.discount_amount, o.total,
                       ROUND((o.total + COALESCE(o.discount_amount,0)) * {CAP_RATIO}, 2) AS cap, o.created_at
                FROM orders o WHERE {where}
                  AND COALESCE(o.discount_amount,0) > (o.total + COALESCE(o.discount_amount,0)) * {CAP_RATIO} + {EPS}
            """), params))

        bad("3. 实付为负",
            c.execute(sa.text(f"SELECT o.id AS id, o.tenant_id, o.total, o.created_at FROM orders o WHERE {where} AND o.total < 0"), params))

        bad("4. 券不属于本单租户（跨租户折扣）",
            c.execute(sa.text(f"""
                SELECT o.id AS id, o.tenant_id AS order_tenant, cp.tenant_id AS coupon_tenant, o.coupon_id, o.created_at
                FROM orders o JOIN coupon cp ON cp.id = o.coupon_id
                WHERE {where} AND o.coupon_id IS NOT NULL AND o.tenant_id <> cp.tenant_id
            """), params))

        bad("5. 退款金额 > 实付",
            c.execute(sa.text(f"""
                SELECT o.id AS id, o.tenant_id, o.total, o.refund_amount, o.refund_status, o.created_at
                FROM orders o WHERE {where}
                  AND o.refund_amount IS NOT NULL AND o.refund_amount > o.total + {EPS}
            """), params))

        bad("6. 同一 client_request_id 出现多次（幂等唯一约束被绕过）",
            c.execute(sa.text(f"""
                SELECT MIN(o.id) AS id, o.tenant_id, o.client_request_id, COUNT(*) AS n
                FROM orders o WHERE {where} AND o.client_request_id IS NOT NULL
                GROUP BY o.tenant_id, o.client_request_id HAVING COUNT(*) > 1
            """), params))

        warn("7. 疑似重复下单（同桌会话·同金额·60 秒内·都非子单）",
             c.execute(sa.text(f"""
                SELECT o1.tenant_id, o1.dining_session_id, o1.total,
                       o1.id AS order_a, o2.id AS order_b,
                       TIMESTAMPDIFF(SECOND, o1.created_at, o2.created_at) AS gap_sec
                FROM orders o1 JOIN orders o2
                  ON o2.tenant_id = o1.tenant_id
                 AND o2.dining_session_id = o1.dining_session_id
                 AND o2.id > o1.id
                 AND o2.total = o1.total
                 AND o2.created_at BETWEEN o1.created_at AND o1.created_at + INTERVAL 60 SECOND
                WHERE {' AND '.join(w.replace('o.', 'o1.') for w in where.split(' AND '))}
                  AND o1.dining_session_id IS NOT NULL
                  AND o1.parent_order_id IS NULL AND o2.parent_order_id IS NULL
                  AND o1.total > 0
             """), params))

    eng.dispose()
    print("=" * 64)
    if _fail:
        print(f"结论: {_fail} 单 FAIL —— 金额契约被破坏，必须逐单查清（是历史脏数据还是代码 bug）")
        raise SystemExit(1)
    print(f"结论: 金额硬约束全部通过。" + (f" 另有 {_warn} 组疑似重复下单，人工确认。" if _warn else ""))


if __name__ == "__main__":
    main()
