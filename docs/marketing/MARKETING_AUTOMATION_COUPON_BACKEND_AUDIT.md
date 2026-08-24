# 自动化发券能力审计

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
BASELINE=78ccd74
SCOPE=saas-base + admin-h5（member-mini-client 只确认消费端承接）
CODE_CHANGE=NO
NEW_DB=NO
NEW_MARKETING_CENTER=NO
```

对照商家配置规则 → 自动触发 → 生成券 → 领取/使用 → 效果追踪。不设计新营销中心。

---

## 1. 当前架构

没有独立「营销中心」服务。发券叠在三层上：

| 层 | 位置 | 职责 |
|---|---|---|
| 平台规则 | `saas-base/app/core/platform_rules.py` `build_dynamic_rules(aov, intensity)` | 按客单价 + 营销强度算出五种自动券的门槛/面额/有效期 |
| 发券执行 | `CouponService`（`coupon_service.py`） | 建模板、`send_coupons_with_result`、`issue_auto_coupon` / `issue_entry_coupon` / `batch_issue_recall_coupon` |
| 触发点 | 入会 API、菜单进店、支付成功、线下消费 API、积分兑券、每日召回循环 | 直接调 CouponService，**不是**通用 `order_paid` 事件 |
| 商家 UI | `admin-h5` `CouponCenter.vue` + `Dashboard` 强度开关 + `MarketingEffectiveness.vue` | 强度三档、说明五种时机、可选手动建券、看发/核销/GMV |
| 顾客端 | `member-mini-client` 结算用券、成功页展示本单赠券、券列表 | 承接领取后的展示与自动核销 |

套餐：`CAP_COUPONS` 与 `CAP_MARKETING_AUTOMATION` 都在 **Pro**（`plan_capabilities.py` L73–L81）。非 Pro 支付成功路径会跳过自动发券（`optional_entitlement` 测试已锁）。

领域事件总线只有 `consumption.created`（`events.py`），处理器是会员成长/积分插件，**不发券**。堂食发券走 `order_payment_service._on_payment_success` 的同步调用。

---

## 2. 优惠券模型能力

**没有**独立表 `user_coupon` / `coupon_record`。实际两张主表：

### `coupon_template`（`models/coupon_template.py`）

商家/系统券蓝图：`name, type, value, min_amount, total_stock, used_stock, start_time, end_time, status, description`。

自动券把 `description` 写成 `rule_type`（如 `new_customer_coupon`），用来去重和效果统计，不是给人看的长文案。

已发过券的模板禁止改 type/value/min_amount（`coupon_service.py` L722–L743），因为券实例 **不快照面额**，核销时读模板。

### `coupon`（`models/coupon.py`）

一张券 = 发给一个顾客的一份实例：`template_id, customer_id, code, verify_code, status, use_time, expire_time, revoke_*`。

没有：`source` 列、`order_id`（发券来自哪一单）、领取渠道。`send_coupons_with_result(..., source=)` 只进返回值，**不落库**。

状态：`UNUSED` / `USED` / `EXPIRED` / `REVOKED`。列表查询可 `not_expired=True` 滤掉过期未用（L1038–L1054）。**没有**定时把 UNUSED 批量改成 EXPIRED；核销时过期才写成 EXPIRED（`verify_service.py` L120–L124）。

核销：堂食结算自动用券（支付链路 `cap_discount_amount`）；店员扫码 `verify_service` 仍在，后台写「只用于少数手动场景」。

| 能力 | 有？ | 说明 |
|---|---|---|
| A 商家创建模板 | 是 | `POST /api/v1/coupon-templates/`；CouponCenter 高级设置「手动建券」 |
| B 系统主动发券 | 是 | `issue_auto_coupon` / `issue_entry_coupon` / 召回循环 |
| C 用户主动领取 | **基本无** | 无领券广场。进店/入会/支付后系统塞进账户，顾客端是「已持有」 |
| D 自动核销 | 是 | 结算选最划算 UNUSED 券；红线单张不超过订单 20% |
| E 过期处理 | 部分 | 有 `expire_time`；查询过滤；核销时标记。无每日过期批处理 |

消费端承接（mini）：CheckoutSheet 选券、支付成功展示 `reward_coupon_snapshot`、券列表/详情「去点餐」。顾客不能在小程序里「领一张活动券」，只能用已发的。

---

## 3. 发券流程

统一出口：`CouponService.send_coupons_with_result(template_id, customer_ids, source=)`。自动券先 `_get_or_create_auto_coupon_template`。同类 UNUSED 用 Redis 锁去重。

### 当前发券入口

| 入口 | 触发 | 规则 | 执行者 |
|---|---|---|---|
| 后台手动发 | 顾客详情选模板 `POST /coupons/send` | 指定 `customer_ids` | 人工 + API |
| 入会/注册 | `miniapp.py` 入会、`member.py` 新客 | `new_customer_coupon` | API 同步 |
| 进店 | `menu.py` `_issue_entry_coupon` | `entry_coupon` 当日有效 | API 同步（打开菜单） |
| 支付成功（预付） | `order_payment_service._on_payment_success` | 按已支付单数解析 `new_customer_coupon` 或 `consumption_coupon` | API 同步 |
| 餐后付/桌台结清 | `_apply_paid_order_member_assets_once` | 同上 | API 同步 |
| 后台记一笔消费 | `consumptions.py` 创建消费后 | 同上 `issue_auto_coupon` | API 同步 |
| 积分兑券 | `membership_service.add_points` 达阈值 | `points_reward_coupon` | API 同步 |
| 邀请奖励 | 邀请规则（默认 **关闭**） | `invite_reward` | 核销/入会副作用 |
| 老客召回 | `main.py` `_marketing_recall_loop` 每 24h | `recall_coupon`，默认 7 天未消费 | **进程内定时任务** |
| 核销后再发复购 | `verify_service` 扫码核销成功 | `consumption_coupon` | API 同步 |

商家 **不能**在后台为自动规则勾选「全部会员 / 仅新客 / 满 80 元」。对象和门槛由平台 AOV 算法 + 强度档决定。手动发只能选具体顾客（顾客详情）或模板库存（建券时的「发多少张」是库存，不是自动圈人）。

CouponCenter 主界面五种时机是 **说明文案**，不是可配参数表（`CouponCenter.vue` L33–L56：「不给参数、不给独立开关」）。商家唯一全局旋钮：保守 / 标准 / 激进（`marketing_intensity`）。

---

## 4. 后端事件能力

| 订单生命 | 有没有通用事件名 | 会不会发券 |
|---|---|---|
| 创建 | 无 `order_created` 总线事件 | 否 |
| 支付成功 | **无** `order_paid` 事件；`_on_payment_success` 内直调 | **会**（Pro + CAP_COUPONS） |
| 订单完成/出餐 | 无独立 `order_completed` 发券钩子 | 否（出餐不发券） |
| 桌台结清 / 餐后付标记已付 | `_apply_paid_order_member_assets_once` | **会**（与预付对齐过） |
| 退款/取消 | 测试锁死：取消路径 **不得** 调 `_on_payment_success` | 不发券；已发券不因退款自动收回（需手动作废） |

真正的 EventBus：

- 名字：`consumption.created`
- 用途：更新最后消费时间、会员成长、积分插件
- **不**发券（发券在写消费 API 里先 `issue_auto_coupon` 再 dispatch）

**可作为自动发券触发点（已经在用）：** 支付成功、桌台结清、入会、进店、积分达标、每日召回扫描。  
**尚未抽象成可订阅事件：** 没有商家/插件能自己挂 `on_order_paid` 的扩展点；再加一种营销要改支付服务。

---

## 5. 商家后台能力

`admin-h5`：`/coupons`（CouponCenter）、今日页营销卡、`/marketing-effectiveness`、顾客详情发券、`/coupon-records`。

| 问 | 现状 |
|---|---|
| 1. 能否创建券模板？ | **能。** 高级设置手动建券（名称、减多少、满多少、库存、有效天数）。自动券模板由系统按规则 upsert，商家不填面额。 |
| 2. 发放对象？ | **自动规则：系统定**（新客/复购/进店/7 天未到/积分够）。**手动：指定单个顾客**（顾客详情）。没有「全部会员」一键、没有标签圈人 UI。 |
| 3. 能否设规则（满多少、次数、时间）？ | **不能逐条填。** 只能选强度。满多少由近 30 天 AOV 算出。召回天数写死在规则默认 7（API `recall-batch` 可传 `inactive_days`，CouponCenter 主界面没有该输入）。 |
| 4. 效果？ | **有汇总，没有「这张券带来哪一单」明细。** 本月已发/已核销/核销率（CouponCenter、Dashboard）；营销效果按 rule_type：发券数、核销率、带来 GMV（`Order.coupon_id` 关联 **用券单**）。裂变人数仅邀请/员工渠道。 |

发券记录页看的是 `coupon` 列表（谁、状态、模板名、发放时间、使用时间），`rule_type` 来自模板 `description`。

---

## 6. 当前成熟度评分

| Level | 含义 | 本系统 |
|---|---|---|
| 0 | 只有库 | 超过 |
| 1 | 人工建 + 人工发 | 有（模板 + `/coupons/send`） |
| 2 | 固定规则自动发（如注册送券） | **有**（入会新客券、进店券、积分兑券） |
| 3 | 事件营销（消费完成后自动送） | **有**（支付成功 / 结清 / 后台消费记录后发复购或新客券） |
| 4 | 用户分层（沉睡召回等） | **部分**：每日扫 7 天未消费发召回券；**不是**商家自建分层（RFM、指定标签、自定义沉默天数 UI） |

**评级：Level 3。** 召回循环是平台写死的一层「弱 Level 4」，不能当成完整用户分层营销。

闭环五问：

1. **商家创建券后如何到用户手里？** 自动券：系统在进店/入会/支付等点 `issue_*`，顾客账户出现 UNUSED。手动模板：必须再在顾客详情点发放，否则只是库存。  
2. **何时触发？** 见 §3 表。不是「保存规则后立即群发」。  
3. **谁执行？** 业务 API 同步为主；召回是 FastAPI 进程内 24h 循环；无独立 worker/队列。  
4. **发券后记什么？** `coupon` 行：谁（customer_id）、何时（created_at）、是否用（status/use_time）、哪张模板。**不记** 触发哪笔订单。用掉之后 `Order.coupon_id` 才把「哪单用了这张券」连上，这是核销归因，不是发放归因。  
5. **商家能否看效果？** 能看渠道汇总（发/核销/GMV），不能看「这笔营销带来的订单列表」。

---

## 7. 第一阶段 MVP 建议

目标仍是现有 CouponService + 强度档，不新建营销中心、不新表也能做的最小增强（建议，不实施）：

1. **说清楚自动 vs 手动：** 手动建的模板若未「发给谁」，Dashboard 提示「活动券尚未发放」。  
2. **发放归因（若下一阶段动库）：** `coupon` 上可选 `source` + `issue_order_id`。本审计禁止加表，故列为缺口而非现在做。  
3. **召回对商家可见：** 效果页已有召回渠道；CouponCenter 可展示「上次召回发出 N 张」（读现有 issued 统计即可）。  
4. **不要** 先做自定义分层、满 X 元编辑器、领券广场——那是 Level 4 产品，超出当前闭环补齐。

消费端已能用券、展示成功赠券；缺的是「用户主动领」和「商家自配触发规则」，不是结算核销。

---

## 审计结论（给下一阶段）

**当前营销自动化等级：Level 3**（事件发券已跑在支付/结清上；召回为平台定时、非商家分层）。

**已实现：** 模板 + 实例两表；平台 AOV 动态规则；入会/进店/支付/积分/召回自动发；结算自动核销；强度三档；按规则类型的发券/核销/GMV 汇总；Pro 能力门禁。

**缺失：** 商家可编辑的触发规则与圈人；用户主动领取；券实例上的发放来源/来源订单；通用 `order_paid` 事件总线；过期批处理；退款自动收回；「带来哪些订单」明细。

**下一阶段建议：** 产品若只想「商家感知自动营销在跑」，补文案与效果可见性即可。若要「商家自己配一条消费满送」，需要规则配置与触发解耦（那是新能力，本审计不设计）。
