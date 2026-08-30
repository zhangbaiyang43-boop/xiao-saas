# 上线前系统完整性 / 稳定性筛查清单

日期：2026-08-30
适用：`saas-base`(后端) · `admin-h5`(商家后台) · `member-mini-client`(顾客小程序)
用法：逐项勾选。`[x]` = 已验证通过；`[~]` = 部分完成 / 有已知缺口；`[ ]` = 未做。
配套只读脚本（都在 `saas-base/scripts/`，不写库）：
`check_demo_tenant.py` · `diagnose_tenant_coupons.py` · `probe_tenant_isolation.py`
前端时区断言：`admin-h5/scripts/test-beijing-time.mjs`

---

## A. 钱 —— 阻塞级，必须全绿才上线

- [ ] **收款模式契约**：`prepay / postpay / table_account` 三种，桌码分区 `zone_type` 能强制覆盖店铺默认。
  验：每种模式真机各下一单，确认小程序按钮文案（"立即支付" / "提交桌台"）与后端实际走的流程一致。
- [ ] **最终金额权威**（`fix/p0-14` 已合）：金额一律服务端按菜单价重算。
  验：构造一个改价的下单请求，应被拒 / 以服务端价为准。
- [ ] **一单只能用一张券**、券折扣 ≤ 本单原价 20%（`platform_rules.cap_discount_amount`）。
  验：`diagnose_tenant_coupons.py <tenant>` 看规则；造不同客单价样例订单跑结算，无一单减免超 20%。
- [ ] **月优惠预算总闸**：近 30 天优惠 ≤ GMV × (3/5/8)%，超了 `issue_auto_coupon`/`issue_entry_coupon` 直接不发。
  验：admin「智能营销 → 发券效果」预算进度条；或造数据触发闸。
- [ ] **退款 / 取消契约**（`fix/p0-09` 已合）：已支付订单取消 → 券恢复、状态回滚、退款路径明确。
  验：真机下单支付 → 取消，检查券、订单状态、退款记录。
- [x] **WXPay 恢复闸已在 main**：`saas-base/app/services/wxpay_recovery_gate.py`（374 行，commit `e8b399b`，2026-08-20）——
  单一共享节流闸，per-order 冷却/退避、monotonic 计时、同一 order_id 同时只有一个真实 provider 查询在飞、有界内存。
  测试 `tests/test_p1_wxpay_recovery_gate.py`（22 个）。
  注：分支 `fix/p1-wxpay-recovery-gate` 名字有误导——本地那两个 commit 是别的（商户开通）且已被 PR #11 取代，勿合，建议删。
- [ ] **平台订阅收款**：线上确认 `SAAS_REAL_PAYMENT_ENABLED=False`、走 `SAAS_MANUAL_PAYMENT_ENABLED`（官方码 + 超管确认）。
  验：`PROVIDER_IMPLEMENTATION_READY` 代码常量没被误开；试跑一次手动核销流程。
- [ ] **幂等**（`fix/p0-04` 已合）：同 `request_id` 重试返回同一张订单。
  验：真机弱网 / 双击重试一次。

## B. 多租户隔离 —— 阻塞级

- [ ] **跨租户探针全绿**：`python scripts/probe_tenant_isolation.py <大宝羊肉馆tenant_id> <另一个真实tenant_id>`
  覆盖：A 令牌读 B 的订单/客户/入口码/券全拒；令牌类型 / 伪造 / 过期 / 无令牌 fail-closed；库内子表 tenant_id 一致性。
- [x] **非 demo 令牌打 `/api/v1/demo/*` → 403**（原为 500，`d589a80` 已修）。
- [ ] **令牌边界**：merchant / member / staff / demo_merchant / channel_partner 五种，各自越界访问应 401/403。
  （`fix/p0-10` `p0-11` `sessionless` 桌台隔离均已合，仍需真机多设备复核同桌多人 / 换桌）
- [ ] 员工角色默认拒（owner 全通），套餐降级后 staff JWT 立即失效（`_staff_capability_denial`）。

## C. 时间 / 时区 —— 已修，需回归

- [x] 后端 naive UTC 时间戳 → 前端统一按北京时间解析展示。`admin-h5/src/utils/beijingTime.js` +
  `format.js` + 全量清扫 ~20 处 `new Date(服务端值)`；`member-mini-client` 补齐两处。(`3cc3a05`)
- [x] `admin-h5/scripts/test-beijing-time.mjs` 通过（多时区）。
- [ ] **回归**：admin-h5 重新部署后，真机看订单时间 / "X 分钟前" / 今日营收统计 / 券到期，均为北京时间且日期不跨天错。
- [ ] `member-mini-client` 重新发布后同样回归（券到期、"会员自 X 年"）。

## D. 订单生命周期 & 实时同步

- [ ] 状态机 `pending → preparing → done → served`：越级 / 重复提交 / 并发操作行为正确（`p0-08` `p0-15` 已合）。
- [ ] **厨房出票可靠性**（`fix/p0-07` 已合）：飞鹅云打印机离线 / 超时 / 重复打印的恢复；`FEIEYUN_*` 未配的店不报错。
  （注意：生产日志里有订单 `7496403891492360192` 长期卡在 `PRINT_RECOVERY_ATTEMPT` 循环，排查是否僵尸任务。）
- [ ] **异步 / 事务陷阱**：`MissingGreenlet` 类（已修一次）；**批量循环共享 session 时任一 rollback 会让其余对象过期**——审计批量发券 / 批量改状态代码。
- [ ] 工作台 2 秒轮询：N 家店同时开工作台的 DB / 连接池压力（见 J 压测）。

## E. 部署 / 运维 / 恢复 —— 阻塞级

- [ ] **`.env` 与 `saas-base/static/` 异地备份**（都不在 git、只在服务器；机器挂了配置和入口码图全丢）。
- [ ] `deploy-production.sh` 健康检查抢跑问题（`systemctl restart` 后立刻 curl，旧进程关得慢误判失败）——加等待 / 重试窗口，或记录"失败后手动 `curl /health` 复核"的 SOP。
- [ ] 确认生产 admin-h5 走的链路（`deploy-production.sh` 统一链路 vs 老的手工 `dist`；`docs/production-deployment.md` 说首次切换"尚未执行"）。
- [ ] **回滚演练**：`rollback-admin-h5.sh` 真跑一次；后端出问题退到上一个 SHA 的步骤。
- [ ] Alembic：新迁移人工审过再上；确认线上 revision。
- [x] MySQL < 8.0（`SKIP LOCKED` 踩过并修）——全库已扫，无其它 8.0-only 语法；压测时留意 ORM 生成的 SQL。
- [ ] 生产机 ~1.6G 内存 + 后端/MySQL/Redis 同机：上量后的 OOM 风险，压测时盯内存。

## F. 新商户自助开通

- [ ] 陌生老板：扫体验卡 → 注册 → 激活 → 录菜单 → 选业态 / 强度 → 首单，全程不卡不白屏。
  （`phase02-merchant-signup-activation-v2`、注册码白名单、`existing-tenant-commercialization-trial` 均已合）
- [ ] 试用期 → 到期 → 转付费订阅的边界（`codex/phase03a-subscription-selection` 已合）。
- [ ] 冷启动（无菜单 / 无订单）各页面兜底正常。

## G. 微信平台依赖

- [ ] `member-mini-client` 审核状态 / 版本；`channel=DEMO` 那一版是否已发布（体验卡演示用，不发也能演示但不够干净）。
- [ ] `getwxacodeunlimit` 日调用配额：一家店几十桌 × 多家店批量建码时留意。
- [ ] 订阅消息模板 ID（券提醒 / 排队 / 订单 / 取餐）线上还在、字段顺序对。
- [ ] **`ALLOW_MOCK_WECHAT_SESSION` 线上必须 `False`**；`code2session` 失败必须 fail-closed。
- [ ] access_token 全局限流：多处获取要复用缓存。

## H. 营销 / 券经济性 —— 观察项，不阻塞（已决定先上线观察）

- [ ] 冷启动客单价可能把宽菜单正餐店误判进 micro 带 → 发无门槛券（红线兜住不亏本，但是漏损）。
  盯：`diagnose_tenant_coupons.py <tenant>`；攒够 5 单后重跑看有没有跳出 micro 带；admin「发券效果」面板。
  红旗：优惠总额逼近 GMV×5%；某顾客天天核销无门槛券；核销率高但复购没起来。
- [ ] `MARKETING_AUTO_TUNING_ENABLED` 若开着：确认每周跑、乘数夹在 `[0.75,1.3]/[0.7,1.4]`、有回滚。

## I. 可观测性 / 告警

- [x] 生产事件可追踪性 + 关键事件告警（`bb97262` `2fbe00f` 已合）——**验证告警真的能推达**（造一次后端异常 / 支付失败，确认收到）。
- [ ] `/health` 覆盖 DB + Redis；Redis 挂时哪些功能降级（限流、Demo 直接 503）、正常下单是否受影响。
- [ ] `request_id` 贯穿日志（`fix/p0-16-b1` 已合）——抽查一条链路。

## J. 压测（上线前至少一轮）

- [ ] N 家店 × 每店若干桌 × 并发下单 + 并发工作台 2s 轮询，观察 P95、DB 连接池、CPU/内存、有无 SQL 报错 / 死锁 / greenlet 报错。
- [ ] 重点：同桌多人并发下单、支付回调并发、批量发券。

---

## 未合并分支（上线前确认取舍）

| 分支 | 内容 | 处置 |
|---|---|---|
| ~~`fix/p1-wxpay-recovery-gate`~~ | 名字误导——恢复闸本体已在 main（`e8b399b`）；本地这条 = 别的旧活（商户开通），已被 PR #11 取代 | **删本地分支**，勿合 |
| `perf/phase1-p0-certified` / `release/perf-phase1-backport` | 性能优化回填 | 压测结果决定是否上 |
| `p0-02-pricing-authority` | 定价权威（大概率被已合的 `p0-14` 覆盖） | 确认后删分支 |
| `fix/ops-p0-guest-order-status-tenant`（`-v2` 已合） | 旧版，已被 v2 取代 | 删分支 |

## 已完成（本轮）

- 时区全端统一北京时间（`3cc3a05`）
- 非 demo 令牌打 `/api/v1/demo/*` 由 500 改 403（`d589a80`）
- 只读诊断脚本：`check_demo_tenant` / `diagnose_tenant_coupons` / `probe_tenant_isolation`
- 生产告警（`2fbe00f`，需验证推达）
- 核实 **WXPay 恢复闸已在 main**（`e8b399b` / `wxpay_recovery_gate.py` / 22 测试）——之前以为未合，是笔记过期
