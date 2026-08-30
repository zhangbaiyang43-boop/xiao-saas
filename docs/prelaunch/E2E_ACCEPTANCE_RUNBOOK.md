# 上线前真机端到端验收 Runbook

日期：2026-08-30
目的：把"三种收款模式 + 用券 + 退款 + 幂等 + 并发 + 打印降级"这几条真机走一遍，
每条有明确的**期望屏幕文案**和**期望库状态**，打勾不是凭感觉。

## 前置

- 一台真实测试门店（不是 `demo` 演示租户）：菜单已录、至少 1 张桌码、收款账户已配。
- 两台手机（顾客 A / 顾客 B）。
- 一个能查库的窗口 + 服务器上：
  ```bash
  cd /www/wwwroot/xiao/saas-base && source venv/bin/activate
  ```
- 每条场景跑完，用只读脚本兜一遍金额契约：
  ```bash
  python scripts/audit_order_money_contract.py <测试门店tenant_id> --days 1
  ```
  期望：全部 `[ PASS ]`，结论"金额硬约束全部通过"。

判定：**期望列全部命中 = 通过**；任一不符 = 记录 order_id + 现象，不要"应该没事"。

---

## 场景 1 — prepay（预付，扫码即付）

门店/桌码收款模式 = `prepay`（或桌码分区 `zone_type=quick`）。

| 步 | 操作 | 期望屏幕 | 期望库（`SELECT status,payment_status,payment_mode,payment_method,total,discount_amount FROM orders WHERE id=?`） |
|---|---|---|---|
| 1 | 顾客 A 扫桌码进菜单 | 顶部显示门店名 + 桌号 + "堂食" | — |
| 2 | 选 1 个菜，进结算 | 按钮文案 **"立即支付 ¥X"**（不是"提交桌台"） | — |
| 3 | 点支付，走微信支付真实付款 | 微信收银台弹出 → 付款成功 → 回到订单页显示"已支付/制作中" | `status` 进入 `pending`/`preparing`；`payment_status=paid`；`payment_mode=prepay`；`payment_method=wxpay`；`total` = 实付金额 |
| 4 | 商家工作台 | 2 秒内出现该单，可"接单" | — |

必须成立：`payment_status=paid` 且 `wx_transaction_id` 非空；`total` = 微信实付金额。

---

## 场景 2 — postpay（后付，先吃后付）

门店/桌码收款模式 = `postpay`。

| 步 | 操作 | 期望屏幕 | 期望库 |
|---|---|---|---|
| 1 | 顾客 A 扫码点 1 个菜进结算 | 按钮文案 **"提交订单"/"提交桌台"**，**不弹微信支付** | — |
| 2 | 提交 | 显示"已下单/等待出餐"，无扣款 | `status=pending`；`payment_status=unpaid`；`payment_mode=postpay` |
| 3 | 工作台接单 → 制作完成 → 确认上菜 | 每步有结果 | `status` 依次 `preparing`→`done`；`served_at` 落值 |
| 4 | （如有）前台/顾客侧后付结账 | 结清后状态更新 | `payment_status=paid`（结账后） |

必须成立：**第 1 步全程没有微信支付弹窗**（这是 postpay 的核心）。

---

## 场景 3 — table_account（挂账，整桌最后一起结）

门店/桌码收款模式 = `table_account`（或桌码分区 `zone_type=full`）。

| 步 | 操作 | 期望屏幕 | 期望库 |
|---|---|---|---|
| 1 | 顾客 A 扫码点菜提交 | 按钮"提交桌台"，不弹支付 | 订单 `payment_mode=table_account`，`payment_status=unpaid` |
| 2 | 顾客 A 再加一单（同桌） | 加菜成功 | 同一 `dining_session_id` 下多个订单 |
| 3 | 顾客 B 用另一台手机扫**同一张桌码**，也点一单 | 进的是同一桌 | 三单同一个 `dining_session_id`（`SELECT id,customer_id,total FROM orders WHERE dining_session_id=?`） |
| 4 | 前台对这一桌整桌结账 | 一次性结清全部未付订单 | 该 session 下所有订单 `payment_status=paid`；金额 = 各单之和 |

必须成立：三单归到**同一个 `dining_session_id`**（不串桌、不各自成桌）；结账金额 = 明细合计。

---

## 场景 4 — 用券，验证金额没算错

在场景 1 或 2 的基础上，顾客账户里先有券（进店/新客券）。

| 用券类型 | 造的订单 | 期望减免 | 期望库 |
|---|---|---|---|
| **¥3 无门槛** | 原价 ¥15 | 减 `min(3, 15×20%)` = **¥3**，实付 ¥12 | `discount_amount=3.00`，`total=12.00`，`coupon_id` 非空 |
| **¥3 无门槛** | 原价 ¥6（只点便宜的） | 减 `min(3, 6×20%)` = **¥1.20**，实付 ¥4.80 | `discount_amount=1.20`，`total=4.80` |
| **满 100 减 15** | 原价 ¥88（没到门槛） | 结算页报"未达到优惠券使用门槛"，券用不了 | 不生成带该券的订单 |
| **满 100 减 15** | 原价 ¥120 | 减 `min(15, 120×20%=24)` = **¥15**，实付 ¥105 | `discount_amount=15.00`，`total=105.00` |

必须成立：**没有一单 `discount_amount > (total+discount_amount)×0.2`**；一单只用一张券（不叠加）。
跑完 `audit_order_money_contract.py` 应全 PASS。

---

## 场景 5 — 退款 / 取消

| 步 | 操作 | 期望屏幕 | 期望库 |
|---|---|---|---|
| 1 | 拿场景 1 的已支付单，商家侧发起取消/退款 | 提示退款处理中 → 成功 | `status=cancelled`；`refund_status=success`；`refund_amount ≤ total` |
| 2 | 该单如果用了券 | 券应恢复为可用 | `SELECT status FROM coupon WHERE id=<coupon_id>` → 回到 `UNUSED`（不是 `USED`/`LOCKED`） |
| 3 | 取消一个 postpay 未付单 | 直接取消，无退款 | `status=cancelled`，无 `refund_*` |

必须成立：退款金额不超过实付；用掉的券取消后能再用。

---

## 场景 6 — 幂等（双击 / 弱网重试）

| 步 | 操作 | 期望 |
|---|---|---|
| 1 | 结算页**快速双击**提交按钮 | 只生成 **1 张**订单 |
| 2 | 手机开飞行模式模拟弱网：提交 → 立刻断网 → 恢复 → 客户端自动重试 | 仍只有 1 张订单，金额一致 |
| 3 | 查库 | `SELECT COUNT(*),client_request_id FROM orders WHERE dining_session_id=? GROUP BY client_request_id` —— 同一 `client_request_id` 只有 1 行 |

必须成立：无论重试几次，一次"提交"= 一张订单。`audit_order_money_contract.py` 第 6 项 PASS。

---

## 场景 7 — 同桌多人并发下单

| 步 | 操作 | 期望 |
|---|---|---|
| 1 | 顾客 A、B 同时扫同一张桌码 | 都进同一桌 |
| 2 | 两人**几乎同时**各自提交一单 | 两单都成功，都归到同一 `dining_session_id`，互不覆盖 |
| 3 | 工作台 | 两单都出现，可分别处理 |

必须成立：无一单丢失、无一单串到别的桌。

---

## 场景 8 — 打印失败降级（如门店配了飞鹅云打印机）

| 步 | 操作 | 期望 |
|---|---|---|
| 1 | 拔掉/关掉打印机，下一单 | 订单正常生成，**不因打印失败而下单失败** |
| 2 | 工作台 | 该单标"打印失败/待补打"，有"补打"按钮 |
| 3 | 恢复打印机，点补打 | 补打成功，`print_status=SUCCESS` |
| — | 没配打印机的门店下单 | 完全不报打印相关错误 |

---

## 通过标准

- 场景 1–7 全部"必须成立"命中。
- 每个场景后 `audit_order_money_contract.py <tenant> --days 1` 全 `[ PASS ]`。
- 场景 8 视门店是否用打印机。

任一场景失败：记 `order_id` + 现象 + 复现步骤，回到对应服务代码定位，不带病上线。
