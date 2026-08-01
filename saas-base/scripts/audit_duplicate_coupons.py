"""发券系统数据体检：扫描是否有客户名下同一 rule_type 堆积了多张未使用的自动券。

这是只读排查脚本，不修改任何数据。用来验证 consumption_coupon/recall_coupon
去重修复前后的实际效果，也可以定期跑一次当作监控——正常情况下这个脚本应该
永远不报任何异常分组。

用法（在 saas-base 目录下）：
    .venv/Scripts/python.exe scripts/audit_duplicate_coupons.py

只依赖 coupon / coupon_template 两张表里最基础、几乎不会随迁移变化的列
（id/tenant_id/customer_id/template_id/status/created_at/expire_time，
以及 template 的 name/value/min_amount/description），避免脚本本身因为
个别环境的迁移滞后（缺列）而跑不起来。
"""

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import async_engine

# 跟 CouponService.get_available_auto_coupon 里用的是同一份映射——一张券属于
# 哪个 rule_type，看它绑定的模板 description（新模）或者 name（旧模兜底）。
LEGACY_NAME_TO_RULE_TYPE = {
    "新客券": "new_customer_coupon",
    "消费后发券": "consumption_coupon",
    "老客召回券": "recall_coupon",
    "今日专享券": "entry_coupon",
}

# 动态算法给不同权重档位起的名字，同样归到各自的 rule_type 家族，
# 只按 description 匹配就够了，这里列出来只是方便人读报告时对上号。
WEIGHTED_NAME_HINT = {
    "新客专享券": "new_customer_coupon",
    "下次专享券": "consumption_coupon", "感谢惠顾券": "consumption_coupon", "超值回馈券": "consumption_coupon",
    "幸运券": "recall_coupon",
    "今日专享券": "entry_coupon", "幸运优惠券": "entry_coupon", "超值大礼券": "entry_coupon",
}


def log(message: str) -> None:
    print(f"[coupon_audit] {message}", flush=True)


def classify_rule_type(description: str | None, name: str | None) -> str | None:
    """复刻 get_available_auto_coupon 的匹配顺序：新模看 description，
    旧模/新模都对不上 description 时，退回按名字猜一个家族，猜不到就是
    手动建的活动券，不算在"自动发券"的去重范围内，返回 None。
    """
    if description in LEGACY_NAME_TO_RULE_TYPE.values():
        return description
    if name in LEGACY_NAME_TO_RULE_TYPE:
        return LEGACY_NAME_TO_RULE_TYPE[name]
    if name in WEIGHTED_NAME_HINT:
        return WEIGHTED_NAME_HINT[name]
    return None


async def fetch_unused_coupons(conn) -> list[dict]:
    result = await conn.execute(
        text(
            """
            SELECT
                c.id AS coupon_id,
                c.tenant_id,
                c.customer_id,
                c.template_id,
                c.status,
                c.created_at,
                c.expire_time,
                t.name AS template_name,
                t.value AS template_value,
                t.min_amount AS template_min_amount,
                t.description AS template_description
            FROM coupon c
            LEFT JOIN coupon_template t ON t.id = c.template_id
            WHERE c.status = 'UNUSED'
              AND (c.expire_time IS NULL OR c.expire_time > NOW())
            ORDER BY c.tenant_id, c.customer_id, c.created_at
            """
        )
    )
    return [dict(row) for row in result.mappings().all()]


async def audit() -> int:
    async with async_engine.connect() as conn:
        database = (await conn.execute(text("SELECT DATABASE()"))).scalar()
        log(f"database={database}")

        rows = await fetch_unused_coupons(conn)
        log(f"未使用且未过期的券总数：{len(rows)}")

        groups: dict[tuple, list[dict]] = defaultdict(list)
        unclassified = 0
        for row in rows:
            rule_type = classify_rule_type(row["template_description"], row["template_name"])
            if not rule_type:
                unclassified += 1
                continue
            key = (row["tenant_id"], row["customer_id"], rule_type)
            groups[key].append(row)

        if unclassified:
            log(f"有 {unclassified} 张券对不上任何自动发券 rule_type（大概率是商家手动建的活动券），不计入去重范围")

        anomalies = {key: items for key, items in groups.items() if len(items) > 1}

        if not anomalies:
            log("体检结果：没有发现同一客户名下同一类型自动券堆积超过1张的情况")
            return 0

        log(f"体检结果：发现 {len(anomalies)} 组异常——同一客户同一类型自动券手上有多张未用完的")
        log("=" * 70)
        for (tenant_id, customer_id, rule_type), items in sorted(anomalies.items(), key=lambda kv: -len(kv[1])):
            log(f"租户={tenant_id}  客户={customer_id}  类型={rule_type}  张数={len(items)}")
            for item in items:
                log(
                    f"    券id={item['coupon_id']}  模板={item['template_name']!r}  "
                    f"面额={item['template_value']}  门槛={item['template_min_amount']}  "
                    f"发放时间={item['created_at']}  到期={item['expire_time']}"
                )
        log("=" * 70)
        log("如果这些异常都发生在这次去重修复（consumption_coupon/recall_coupon 加锁）"
            "上线之前，属于历史遗留，不代表修复没生效——修复只保证以后不再新增，"
            "历史数据需要单独决定要不要清理/合并。")
        return 1


def main() -> int:
    try:
        return asyncio.run(audit())
    except Exception as exc:
        log(f"FAILED: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
