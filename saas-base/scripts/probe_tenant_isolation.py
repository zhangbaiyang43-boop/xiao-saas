"""跨租户隔离探针 —— 只读。

用租户 A 的 merchant 令牌，尝试读租户 B 的订单 / 客户 / 入口码 / 优惠券，
断言全部拿不到（403 / 404 / 不出现在列表里）；再验证令牌类型边界
（demo_merchant 打正式接口、伪造 / 过期 / 无令牌）全部 fail-closed；
最后扫一遍库里子表的 tenant_id 有没有跟父表对不上。

只发 GET，不写库、不改状态、不建单。saas-base 服务不用停 —— 用 fastapi
TestClient 在进程内跑同一套中间件；数据库读用独立的同步连接，不碰应用的
async engine。

    cd /www/wwwroot/xiao/saas-base && source venv/bin/activate
    python scripts/probe_tenant_isolation.py <tenant_a> <tenant_b>

租户 id 用 `python scripts/check_demo_tenant.py --find <关键词>` 找。
"""
from __future__ import annotations

import sys
from datetime import timedelta
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
from app.core.security import create_access_token, create_demo_session_token

PASS, FAIL = "[ PASS ]", "[ FAIL ]"
_failures = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global _failures
    print(f"{PASS if ok else FAIL} {label}" + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        _failures += 1


def sync_url() -> str:
    u = settings.DATABASE_URL
    return u.replace("mysql+asyncmy://", "mysql+pymysql://").replace("mysql+aiomysql://", "mysql+pymysql://")


def sample_ids(conn, tenant_id: str) -> dict:
    def col(qtext):
        return [r[0] for r in conn.execute(sa.text(qtext), {"t": tenant_id}).all()]

    return {
        "orders": col("SELECT id FROM orders WHERE tenant_id=:t ORDER BY id DESC LIMIT 5"),
        "customers": col("SELECT id FROM customer WHERE tenant_id=:t ORDER BY id DESC LIMIT 5"),
        "customer_phones": col(
            "SELECT phone FROM customer WHERE tenant_id=:t AND phone IS NOT NULL ORDER BY id DESC LIMIT 5"
        ),
        "entrance_codes": col("SELECT id FROM entrance_code WHERE tenant_id=:t ORDER BY id DESC LIMIT 5"),
        "coupon_codes": col(
            "SELECT code FROM coupon WHERE tenant_id=:t AND code IS NOT NULL ORDER BY id DESC LIMIT 10"
        ),
    }


def blob_has_any(text: str, needles: list) -> list:
    return [str(n) for n in needles if n is not None and str(n) and str(n) in text]


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        raise SystemExit("用法: python scripts/probe_tenant_isolation.py <tenant_a> <tenant_b>")
    tenant_a, tenant_b = args[0].strip(), args[1].strip()

    engine = sa.create_engine(sync_url(), pool_pre_ping=True)
    with engine.connect() as conn:
        for tid in (tenant_a, tenant_b):
            if conn.execute(sa.text("SELECT 1 FROM tenant WHERE tenant_id=:t"), {"t": tid}).first() is None:
                raise SystemExit(f"租户不存在: {tid}")
        b = sample_ids(conn, tenant_b)

        print("\n--- 数据库子表 tenant_id 一致性 ---")
        # 只保留父/子表都确实有 tenant_id 列的组合；某张表没有该列时跳过（非 FAIL）。
        cols = {
            t: {r[0] for r in conn.execute(sa.text(f"SHOW COLUMNS FROM {t}")).all()}
            for t in ("orders", "order_items", "coupon", "coupon_template", "dining_sessions")
        }
        mismatches = {
            "order_items vs orders": ("order_items", "SELECT COUNT(*) FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE oi.tenant_id<>o.tenant_id"),
            "coupon vs coupon_template": ("coupon", "SELECT COUNT(*) FROM coupon c JOIN coupon_template t ON t.id=c.template_id WHERE c.tenant_id<>t.tenant_id"),
            "orders.coupon_id 跨租户": ("coupon", "SELECT COUNT(*) FROM orders o JOIN coupon c ON c.id=o.coupon_id WHERE o.coupon_id IS NOT NULL AND o.tenant_id<>c.tenant_id"),
            "orders vs dining_sessions": ("dining_sessions", "SELECT COUNT(*) FROM orders o JOIN dining_sessions d ON d.id=o.dining_session_id WHERE o.dining_session_id IS NOT NULL AND o.tenant_id<>d.tenant_id"),
        }
        for label, (needs_col_table, q) in mismatches.items():
            if "tenant_id" not in cols.get(needs_col_table, set()):
                print(f"[ skip ] {label}（{needs_col_table} 无 tenant_id 列，按订单归属隔离，无需比对）")
                continue
            try:
                n = conn.execute(sa.text(q)).scalar_one()
                check(n == 0, f"{label} 无错配", f"发现 {n} 行")
            except Exception as exc:
                check(False, f"{label} 查询失败", str(exc)[:120])
    engine.dispose()

    from fastapi.testclient import TestClient
    from app.main import app

    tok_a = create_access_token(tenant_a)
    tok_demo = create_demo_session_token(
        tenant_id=tenant_a, dining_session_id="1", table_no="X",
        expires_delta=timedelta(minutes=5),
    )
    tok_expired = create_access_token(tenant_a, expires_delta=timedelta(seconds=-60))
    H = lambda tok: {"Authorization": f"Bearer {tok}"}

    with TestClient(app, raise_server_exceptions=False) as c:
        print("\n--- 用 A 的令牌读 B 的数据（应全部拿不到）---")
        r = c.get("/api/v1/orders", headers=H(tok_a))
        leaked = blob_has_any(r.text, b["orders"]) if r.status_code == 200 else []
        check(r.status_code == 200 and not leaked, "GET /orders 不含 B 的订单 id", f"http={r.status_code} 泄漏={leaked}")

        r = c.get("/api/v1/customers/", headers=H(tok_a))
        leaked = blob_has_any(r.text, b["customers"] + b["customer_phones"]) if r.status_code == 200 else []
        check(r.status_code == 200 and not leaked, "GET /customers 不含 B 的客户/手机号", f"http={r.status_code} 泄漏={leaked}")

        for cid in b["customers"][:3]:
            r = c.get(f"/api/v1/customers/{cid}", headers=H(tok_a))
            check(r.status_code in (403, 404), f"GET /customers/{cid} (B) 被拒", f"http={r.status_code}")
            r = c.get(f"/api/v1/customers/{cid}/timeline", headers=H(tok_a))
            check(r.status_code in (403, 404), f"GET /customers/{cid}/timeline (B) 被拒", f"http={r.status_code}")

        for eid in b["entrance_codes"][:3]:
            r = c.get(f"/api/v1/entrance-codes/{eid}", headers=H(tok_a))
            check(r.status_code in (403, 404), f"GET /entrance-codes/{eid} (B) 被拒", f"http={r.status_code}")

        r = c.get("/api/v1/coupons/issued", headers=H(tok_a))
        leaked = blob_has_any(r.text, b["coupon_codes"]) if r.status_code == 200 else []
        check(r.status_code in (200, 404) and not leaked, "GET /coupons/issued 不含 B 的券码", f"http={r.status_code} 泄漏={leaked}")

        # 认证边界用 /api/v1/customers/ —— 这是明确需要 merchant 令牌的接口
        # （/api/v1/orders 在 OPTIONAL_AUTH_PATHS 里，允许匿名，不能拿来验鉴权）。
        print("\n--- 令牌类型 / 认证边界（应全部 fail-closed）---")
        r = c.get("/api/v1/customers/", headers=H(tok_demo))
        check(r.status_code == 403, "demo_merchant 令牌打 /customers → 403", f"http={r.status_code}")
        r = c.get("/api/v1/demo/session", headers=H(tok_a))
        check(r.status_code in (401, 403), "merchant 令牌打 /demo/session → 401/403（不是 500）", f"http={r.status_code}")
        r = c.get("/api/v1/customers/", headers={"Authorization": "Bearer garbage.token.value"})
        check(r.status_code == 401, "伪造令牌 → 401", f"http={r.status_code}")
        r = c.get("/api/v1/customers/", headers=H(tok_expired))
        check(r.status_code == 401, "过期令牌 → 401", f"http={r.status_code}")
        r = c.get("/api/v1/customers/")
        check(r.status_code == 401, "无令牌 → 401", f"http={r.status_code}")

    print("\n" + "=" * 64)
    if _failures:
        print(f"结论: {_failures} 项 FAIL —— 存在跨租户/鉴权隐患，必须处理")
        raise SystemExit(1)
    print("结论: 全部通过。跨租户隔离与令牌边界在这两个租户上未发现问题。")


if __name__ == "__main__":
    main()
