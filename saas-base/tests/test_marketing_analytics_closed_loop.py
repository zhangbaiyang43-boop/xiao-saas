"""归因闭环 + 核销率闭环调参 —— 见 docs/prelaunch/AUTO_MARKETING_STRATEGY_SPEC.md 8~9 步。"""

import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.platform_rules import apply_tuning, build_dynamic_rules, clamp_tuning_adjustment
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.marketing_analytics_service import (
    MarketingAnalyticsService,
    TUNING_MIN_ISSUED,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

T = "tenant-mkt-loop"
NOW = datetime.utcnow()


class ClosedLoopTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._redis = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(Tenant(tenant_id=T, name="羊肉馆", password_hash="x", status=True))
        self.db.add(TenantConfig(tenant_id=T, member_rules={}, coupon_rules={}, business_info={}, plugin_settings={}))
        await self.db.commit()
        self._cust_seq = 0

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        settings.REDIS_ENABLED = self._redis

    # ---- fixture helpers ----
    async def _customer(self) -> int:
        self._cust_seq += 1
        c = Customer(id=generate_snowflake_id(), tenant_id=T, openid=f"o{self._cust_seq}", name=f"c{self._cust_seq}")
        self.db.add(c)
        await self.db.flush()
        return c.id

    async def _template(self, rule_type: str, value=5, min_amount=30) -> int:
        t = CouponTemplate(
            id=generate_snowflake_id(), tenant_id=T, name=rule_type, type="FIXED",
            value=value, min_amount=min_amount, total_stock=9999, used_stock=0,
            start_time=NOW - timedelta(days=90), end_time=NOW + timedelta(days=30),
            status=1, description=rule_type,
        )
        self.db.add(t)
        await self.db.flush()
        return t.id

    async def _coupon(self, tpl_id, cust_id, *, status="UNUSED", age_days=5, expired=False):
        cp = Coupon(
            id=generate_snowflake_id(), tenant_id=T, template_id=tpl_id, customer_id=cust_id,
            code=f"K{generate_snowflake_id()}", status=status,
            created_at=NOW - timedelta(days=age_days),
            use_time=(NOW - timedelta(days=age_days - 1)) if status == "USED" else None,
            expire_time=(NOW - timedelta(days=1)) if expired else (NOW + timedelta(days=10)),
        )
        self.db.add(cp)
        await self.db.flush()
        return cp

    async def _order(self, cust_id, total=40, *, age_days=5, coupon_id=None, discount=0, status="paid"):
        o = Order(
            id=generate_snowflake_id(), tenant_id=T, customer_id=cust_id, table_no="",
            total=total, status=status, coupon_id=coupon_id,
            discount_amount=discount, created_at=NOW - timedelta(days=age_days),
        )
        self.db.add(o)
        await self.db.flush()
        return o

    def _svc(self):
        s = MarketingAnalyticsService(self.db)
        s.set_tenant_id(T)
        return s

    # ---- apply_tuning wiring ----
    def test_apply_tuning_scales_and_clamps(self):
        base = build_dynamic_rules(90, "standard", "hotpot")
        tuned = apply_tuning(base, {"entry_coupon": {"threshold_mult": 0.9, "amount_mult": 1.1}})
        b = base["entry_coupon"]["weighted_coupons"]
        t = tuned["entry_coupon"]["weighted_coupons"]
        self.assertLess(t[0]["threshold"], b[0]["threshold"])
        self.assertGreaterEqual(t[0]["amount"], b[0]["amount"])
        # 带门槛档面额不超门槛 19%
        for c in t:
            if c["threshold"] > 0:
                self.assertLessEqual(c["amount"], round(c["threshold"] * 0.19) + 0.5)
        # 极端值被夹死
        clamped = apply_tuning(base, {"entry_coupon": {"threshold_mult": 0.01, "amount_mult": 50}})
        self.assertGreaterEqual(clamped["entry_coupon"]["weighted_coupons"][0]["threshold"],
                                round(b[0]["threshold"] * 0.75) - 1)
        self.assertEqual(clamp_tuning_adjustment({"threshold_mult": 0.01, "amount_mult": 50}),
                         {"threshold_mult": 0.75, "amount_mult": 1.4})
        self.assertEqual(apply_tuning(base, None), base)
        self.assertEqual(apply_tuning(base, {"_log": [1]}), base)

    # ---- attribution ----
    def test_attribution_cohorts_and_roi(self):
        async def scenario():
            tpl = await self._template("entry_coupon", value=6, min_amount=40)
            # 3 个用券客人：都核销了、且回头（2 单）
            users = []
            for _ in range(3):
                cid = await self._customer()
                users.append(cid)
                await self._coupon(tpl, cid, status="USED")
                o1 = await self._order(cid, total=44, coupon_id=None)
                await self._order(cid, total=50, coupon_id=None, age_days=3)
                # 有一单挂了券折扣
                await self._order(cid, total=40, discount=6, age_days=4)
            # 2 个没用券客人：只 1 单
            for _ in range(2):
                cid = await self._customer()
                await self._order(cid, total=38)
            # 挂在券上的折扣订单要能被 join 到（coupon_id 指向真实 coupon）
            # 上面简化没连 coupon_id，这里补一单确保 discount_total 有值
            cid = users[0]
            cp = await self._coupon(tpl, cid, status="USED", age_days=2)
            await self._order(cid, total=46, coupon_id=cp.id, discount=6, age_days=2)
            await self.db.commit()
            return await self._svc().attribution_summary(days=30)

        res = asyncio.run(scenario())
        self.assertEqual(res["window_days"], 30)
        es = res["per_source"]["entry_coupon"]
        self.assertGreaterEqual(es["issued"], 3)
        self.assertGreaterEqual(es["redeemed"], 3)
        self.assertIsNotNone(es["redemption_rate"])
        self.assertGreater(es["discount_total"], 0)
        self.assertEqual(res["cohorts"]["coupon_users"]["n"], 3)
        self.assertEqual(res["cohorts"]["non_users"]["n"], 2)
        # 用券组回头率更高
        self.assertGreater(res["cohorts"]["coupon_users"]["repeat_rate"],
                           res["cohorts"]["non_users"]["repeat_rate"])
        self.assertIn("roi", res)

    def test_attribution_empty_is_safe(self):
        res = asyncio.run(self._svc().attribution_summary(days=30))
        self.assertEqual(res["cohorts"]["coupon_users"]["n"], 0)
        self.assertIsNone(res["roi"])

    # ---- tuning signal ----
    def test_tuning_signal_redemption_and_repeat(self):
        async def scenario():
            tpl = await self._template("consumption_coupon")
            # 20 张核销、40 张过期未用 → 核销率 1/3
            for _ in range(20):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="USED", age_days=10)
                await self._order(cid, total=40, age_days=9)
                await self._order(cid, total=40, age_days=7)  # 回头
            for _ in range(40):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="UNUSED", age_days=20, expired=True)
            await self.db.commit()
            return await self._svc()._tuning_signal("consumption_coupon")

        sig = asyncio.run(scenario())
        self.assertEqual(sig["issued"], 60)
        self.assertEqual(sig["settled"], 60)
        self.assertAlmostEqual(sig["redemption_rate"], round(20 / 60, 4), places=3)
        self.assertEqual(sig["repeat_rate"], 1.0)

    # ---- tuning loop ----
    def test_tuning_skips_on_insufficient_data(self):
        async def scenario():
            tpl = await self._template("entry_coupon")
            for _ in range(TUNING_MIN_ISSUED - 5):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="UNUSED", age_days=20, expired=True)
            await self.db.commit()
            return await self._svc().compute_and_apply_tuning()

        out = asyncio.run(scenario())
        d = next(x for x in out["decisions"] if x["rule"] == "entry_coupon")
        self.assertEqual(d["action"], "skip")
        self.assertEqual(d["reason"], "insufficient_data")
        self.assertFalse(out["wrote"])

    def test_tuning_lowers_threshold_when_redemption_low_and_persists(self):
        async def scenario():
            tpl = await self._template("recall_coupon")
            # 2 核销 / 58 过期 → 核销率 ~3% < 10%
            for _ in range(2):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="USED", age_days=10)
            for _ in range(58):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="UNUSED", age_days=20, expired=True)
            await self.db.commit()
            svc = self._svc()
            out = await svc.compute_and_apply_tuning()
            # 重新读配置确认落库
            from app.services.tenant_service import TenantService
            cfg = await TenantService(self.db).get_tenant_config(T)
            return out, cfg.business_info.get("coupon_tuning")

        out, tuning = asyncio.run(scenario())
        d = next(x for x in out["decisions"] if x["rule"] == "recall_coupon")
        self.assertEqual(d["action"], "adjust")
        self.assertLess(d["to"]["threshold_mult"], 1.0)
        self.assertTrue(out["wrote"])
        self.assertIn("recall_coupon", tuning)
        self.assertLess(tuning["recall_coupon"]["threshold_mult"], 1.0)
        self.assertTrue(tuning["_log"])
        self.assertEqual(tuning["_log"][-1]["rule"], "recall_coupon")

    def test_tuning_cooldown_blocks_second_change(self):
        async def scenario():
            tpl = await self._template("recall_coupon")
            for _ in range(2):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="USED", age_days=10)
            for _ in range(58):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="UNUSED", age_days=20, expired=True)
            await self.db.commit()
            svc = self._svc()
            first = await svc.compute_and_apply_tuning()
            second = await svc.compute_and_apply_tuning()
            return first, second

        first, second = asyncio.run(scenario())
        self.assertEqual(next(x for x in first["decisions"] if x["rule"] == "recall_coupon")["action"], "adjust")
        self.assertEqual(next(x for x in second["decisions"] if x["rule"] == "recall_coupon")["reason"], "cooldown")

    def test_tuning_write_false_computes_but_does_not_persist(self):
        async def scenario():
            tpl = await self._template("recall_coupon")
            for _ in range(2):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="USED", age_days=10)
            for _ in range(58):
                cid = await self._customer()
                await self._coupon(tpl, cid, status="UNUSED", age_days=20, expired=True)
            await self.db.commit()
            out = await self._svc().compute_and_apply_tuning(write=False)
            from app.services.tenant_service import TenantService
            cfg = await TenantService(self.db).get_tenant_config(T)
            return out, (cfg.business_info or {}).get("coupon_tuning")

        out, tuning = asyncio.run(scenario())
        self.assertEqual(next(x for x in out["decisions"] if x["rule"] == "recall_coupon")["action"], "adjust")
        self.assertFalse(out["wrote"])
        self.assertFalse(tuning)


if __name__ == "__main__":
    unittest.main()
