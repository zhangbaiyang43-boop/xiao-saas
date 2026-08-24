# P1-MINI-FEATURE-VISIBILITY-AUDIT-PHASE-01

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
SCOPE=member-mini-client
CODE_CHANGE=NO
BASELINE=ba12226
```

只根据 `pages.json`、页面跳转、组件引用和 API 调用判断「用户能不能点到」。没有改代码。

`pages.json` **没有**微信原生 `tabBar`。顾客主路径是扫码进 `menu.vue`，底部 `BottomNav` 四个图标：首页 / 点餐 / 会员 / 我的（我的是 `navigateTo` 独立页）。

---

## 1. 当前用户可见功能地图

冷启动第一页是 `pages/index/index`：有门店上下文则进点餐，否则提示扫码，并可去「我的」。

### 点餐

| 用户看到的 | 实际实现 | 入口 | 可达 |
|---|---|---|---|
| 首页 | `menu.vue` 内 `HomeTab`（不是 `pages/index`） | BottomNav 第一个图标 | 是 |
| 菜单 | `DishList` | BottomNav 第二个图标；首页「立即点餐」 | 是 |
| 菜品详情 / 规格 | `SpecSheet` 弹层，无独立页 | 点菜卡 / 店长推荐 | 是 |
| 购物车条 | `CartBar` | 点餐 Tab 底部常驻 | 是 |
| 结算确认 | `CheckoutSheet` | CartBar「去结算」 | 是 |
| 选券 | `CouponPicker` + `CouponBar` | 结算条 / 点餐页券条 | 是 |
| 微信支付 | 系统收银台；中转页 `payment-handoff` | 结算；代客下单 deep link | 是（handoff 无店内菜单入口，靠 URL） |
| 支付成功 | `PaymentSuccessSheet` | 支付完成 | 是 |
| 本桌订单 | `OrderHistorySheet` / `TableBillSheet` | 成功页「查看订单」；我的「最近订单」带 `openOrders=1` 回菜单 | 是 |

### 会员

| 用户看到的 | 实际实现 | 入口 | 可达 |
|---|---|---|---|
| 会员中心 | `menu.vue` 内 `MemberCard` | BottomNav 第三个图标 | 是 |
| 会员成长 | `subpkg-member/pages/growth` | 会员卡头图；我的页等级/积分行 | 是 |
| 积分 | `subpkg-member/pages/points` | 会员中心资产格 + 服务行；成长页 | 是 |
| 优惠券列表/详情 | `subpkg-coupon/pages/list` `detail` | 会员中心；券详情「去点餐」 | 是 |
| 邀请好友 | `subpkg-member/pages/invite` | 我的页，且 `inviteRewardEnabled` | 条件可达 |
| 员工推荐页 | `subpkg-member/pages/staff-share` | `entry` 识别员工邀请 scene | 扫特定码可达 |
| 资料 / 绑手机 | `subpkg-member/pages/profile-edit` | 我的页「去绑定」 | 是（未绑手机时） |
| 用户协议 | `subpkg-member/pages/agreement` | 我的页底；结算入会 | 是 |

### 订单 / 我的

| 用户看到的 | 实际实现 | 入口 | 可达 |
|---|---|---|---|
| 我的 | `pages/mine/mine` | BottomNav 第四个图标；index「我的」 | 是 |
| 我的订单（历史列表） | `subpkg-member/pages/orders` | 我的 → 我的订单 | 是 |
| 最近一单 | 我的页卡片 | 跳回 `menu?openOrders=1` 打开本桌弹层 | 是，但不是订单列表页 |
| 消费记录 | `subpkg-member/pages/consumptions` | 我的（需登录） | 是 |
| 排队取号 | `subpkg-common/pages/queue-take` | 我的 | 是 |
| 性能自测 | `subpkg-common/pages/perf-debug` | 头像连点 5 次 | 隐藏可达 |

### 用户在「我的」看不到、但会员 Tab 看得到

优惠券、积分明细。只走「我的」、不点会员图标的人会错过这两项。

---

## 2. 页面地图

状态定义：

- **ACTIVE**：`pages.json` 已注册，且业务代码有跳转或它是启动页
- **ORPHAN**：已注册，用户主路径到不了（无 `navigateTo` / 唯一来源也是孤儿）
- **DUPLICATE**：同一任务有两套仍存活的实现
- **LEGACY**：旧体验文件还在，现行入口已指向另一套

| 页面路径 | 功能 | 入口 | 用户可达 | 状态 |
|---|---|---|---|---|
| `pages/index/index` | 冷启动路由 | 小程序首页 | 是 | ACTIVE（不是点餐首页 UI） |
| `pages/entry/index` | 扫码入店 / 分流 | 扫码、`scanStoreCode` | 是 | ACTIVE |
| `pages/mine/mine` | 我的 | BottomNav / index | 是 | ACTIVE |
| `subpkg-order/pages/menu` | 点餐壳（含首页/菜单/会员 Tab） | 扫码、index、我的回店 | 是 | ACTIVE |
| `subpkg-order/pages/payment-handoff` | 代客付款中转 | 外部 token URL | 仅 deep link | ACTIVE |
| `subpkg-member/pages/orders` | 历史订单列表 | 我的 | 是 | ACTIVE |
| `subpkg-member/pages/consumptions` | 消费记录列表 | 我的 | 是 | ACTIVE |
| `subpkg-member/pages/consumption-detail` | 消费详情 | **无** | 否 | ORPHAN |
| `subpkg-member/pages/profile-edit` | 编辑资料/绑手机 | 我的「去绑定」 | 是 | ACTIVE |
| `subpkg-member/pages/invite` | 顾客邀请 | 我的（开关） | 条件 | ACTIVE |
| `subpkg-member/pages/staff-share` | 员工带客转发 | entry 员工码 | 扫码 | ACTIVE |
| `subpkg-member/pages/points` | 积分明细 | 会员 Tab / 成长 | 是 | ACTIVE |
| `subpkg-member/pages/growth` | 会员成长 | 会员 Tab / 我的等级行 | 是 | ACTIVE |
| `subpkg-member/pages/agreement` | 协议 | 我的 / 结算 | 是 | ACTIVE |
| `subpkg-member/pages/card` | 旧版「本店会员卡」+ 出示核销 | **无跳转** | 否 | ORPHAN + LEGACY |
| `subpkg-coupon/pages/list` | 我的优惠券 | 会员 Tab | 是 | ACTIVE |
| `subpkg-coupon/pages/detail` | 券详情 | 列表 | 是 | ACTIVE |
| `subpkg-common/pages/verify-qr` | 出示优惠券二维码给店员 | 仅旧 `card.vue` | 否 | ORPHAN + LEGACY |
| `subpkg-common/pages/queue-take` | 排队取号 | 我的 | 是 | ACTIVE |
| `subpkg-common/pages/perf-debug` | 性能自测 | 头像连点 | 隐藏 | ACTIVE（调试） |
| `subpkg-plugins/pages/crm-placeholder` | 「会员活动」占位 | 无 | 否 | ORPHAN + LEGACY |
| `subpkg-plugins/pages/bargain-placeholder` | 「活动」占位 | 无 | 否 | ORPHAN + LEGACY |
| `subpkg-plugins/pages/points-placeholder` | 「积分」占位 | 无 | 否 | ORPHAN + DUPLICATE（真页是 `points.vue`） |

同目录残留的 `.wxml` / `.wxss`（`pages/index`、`pages/mine`、`card`、`verify-qr`、三个 placeholder）不是 uni-app 运行入口，属于 LEGACY 文件。

`pages.json` 给 `pages/index` 注册了一整套 `van-*`，业务 `.vue` 未使用。

---

## 3. 用户任务链路

### 3.1 点餐

```
扫码/index → menu(HomeTab) → 点餐(DishList)
  → CartBar → CheckoutSheet → 微信收银台
  → PaymentSuccessSheet → 继续点餐 / 查看本桌订单弹层
```

完整，无断链。购物车和支付都不是独立 page，是菜单页上的弹层，符合 `PRODUCT_RULES.md`（确认单不是第二菜单）。

缺口：

- 成功页没有跳「优惠券列表」（`menu.vue` 里有 `goCoupons`，模板未接到 `PaymentSuccessSheet`）。
- 「查看订单」打开的是本桌 `OrderHistorySheet`，不是 `subpkg-member/pages/orders`。
- `deliveryEnabled` 会从店铺配置读入，文案仍是「外卖配送正在完善」，无配送 UI。

### 3.2 会员

```
menu BottomNav 会员 → MemberCard
  → 成长 / 积分 / 优惠券列表
我的 → 等级行→成长；去绑定→资料；邀请（开关）
```

断链 / 旧入口：

- 独立页 `card.vue`（出示给店员、旧会员卡）无入口。
- 核销码页因此也无入口。现行券详情文案已改成「结算自动核销」，与 `card.vue`「出示二维码」是两套体验。
- 「我的」没有优惠券、积分、会员卡行。

### 3.3 订单

```
我的 → 我的订单 = 历史列表（无点击进详情）
我的 → 最近订单卡片 = 回到 menu 本桌弹层
点餐成功 → 本桌弹层
```

没有独立「订单详情」页。列表卡片不可点。`getMyOrders` 有数据，UI 只展示状态/金额/桌牌摘要。

---

## 4. 孤儿功能列表

| 名称 | 位置 | 用途 | 引用 |
|---|---|---|---|
| 旧会员卡页 | `subpkg-member/pages/card.vue` | 会员卡 + 出示核销 | 仅 `pages.json` |
| 出示核销码 | `subpkg-common/pages/verify-qr.vue` | 店员扫顾客券码 | 只被 `card.vue` 引用 |
| 消费详情 | `subpkg-member/pages/consumption-detail.vue` | 单条消费 | API `getConsumptionDetail` 仅本页；列表无跳转 |
| 插件占位 ×3 | `subpkg-plugins/pages/*-placeholder.vue` | 「后续开放」 | 无跳转；`api/plugin.js` 也无人调用 |
| `goCoupons` | `menu.vue` | 成功后去券列表 | setup 返回了，无模板事件 |
| `getAvailablePlugins` | `src/api/plugin.js` | `/v1/plugins/available` | 无引用 |
| `login.js` | `src/api/login.js` | 登录别名 + logout | 无引用（我的页自己清 session） |
| `customer.js` | `src/api/customer.js` | profile/timeline 别名 | 无引用 |
| `getMyCoupons` | `api/auth.js` | 与 `coupon.js` 重复 | 无引用 |
| `mockPayOrder` | `api/order.js` | 模拟支付 | 无引用 |
| `submitReview` | `api/order.js` | 订单评价 | 无引用 |
| `bindInviter` / `getCommissionRecords` | `api/invite.js` | 旧邀请绑定/佣金 | 无引用（邀请码走 `entryJoin.invite_code`） |
| `createVerification` | `api/verify.js` | POST `/v1/verify` | 无引用（核销页只 GET 券码） |
| Vant weapp 注册 | `pages.json` index | button/cell/grid… | 模板 0 次 |

点餐 composable 均被 `menu.vue` 引用，没有整文件孤儿 composable。`AddBtn` / `PriceText` 只有 SpecSheet 在用，但仍被引用，不算 ORPHAN。

---

## 5. 重复入口列表

| 任务 | 现行 | 另一套仍在 | 说明 |
|---|---|---|---|
| 点餐「首页」 | `menu` + `HomeTab` | `pages/index` 启动路由页 | 名字都像首页，职责不同 |
| 会员卡 | `MemberCard` Tab | `card.vue` | 后者不可达，是旧皮肤 |
| 积分 | `points.vue` | `points-placeholder.vue` | 占位页不可达 |
| 订单 | 本桌弹层 vs 历史列表 vs 我的最近一单 | 三套 | 最近一单故意回本桌，不是列表 |
| 优惠券 | 会员 Tab / CouponBar / 结算选券 / 券列表 | `card.vue` 也有「查看优惠券」 | 主路径不经过 card |
| 核销 | 结算自动核销（券详情文案） | `verify-qr` 出示码 | 出示码不可达 |

---

## 6. 缺失入口列表

用户任务存在、或后端已有能力，但当前顾客端没有入口：

| 能力 | 证据 | 前端现状 |
|---|---|---|
| 出示优惠券/会员码给店员 | `verify-qr.vue`；后端 `GET /v1/member/verify-code`、券 verify-code | 页面 ORPHAN；会员码 API 无调用 |
| 储值余额 | `GET /api/v1/member/balance` | 无页面；支付成功只展示本单积分/已省，不展示储值 |
| 储值充值 | `POST /api/v1/member/recharge` | 无 UI；后端默认 403（`ALLOW_MOCK_MONEY_ENDPOINTS`） |
| 订单评价 | `submitReview` → `POST /v1/orders/{id}/review` | 无 UI |
| 历史订单详情 | `GET /v1/member/orders` 已用于列表 | 列表不可点；无详情页 |
| 消费记录详情 | `GET /v1/member/consumptions/{id}` + `consumption-detail.vue` | 列表不跳转 |
| 我的页优惠券/积分 | 会员 Tab 已有 | 「我的」服务列表没有这两行 |
| 插件/活动 | `/v1/plugins/available` + placeholder 页 | 无入口，占位页也进不去 |
| 外卖 | `delivery_enabled` 写入 `deliveryEnabled` | 无配送流程，仅 toast 文案 |

---

## 7. 代码资产（存在但未进入用户路径）

点餐业务组件（`CheckoutSheet`、`DishList`、`CartBar` 等）都挂在 `menu.vue`，用户路径内。未进入用户路径的是 **页面级孤儿** 和 **未引用 API 模块**，见第 4 节。

`login.js` / `customer.js` / `plugin.js` 是整文件未引用。其余 API 文件有真实页面或 composable 调用。

---

## 8. 接口能力 vs 展示

小程序已在用的顾客接口（摘要）：进店 `miniapp/entry/join`、入口码 resolve、菜单/店铺、下单/支付/状态、本桌 dining-session、会员 login/profile/coupons/points/membership、消费列表、邀请 summary/records、排队、付款 handoff、券 remind-me。

后端有、前端无展示或无调用：

| 后端 | 前端 |
|---|---|
| `GET /api/v1/member/balance` | 无 |
| `POST /api/v1/member/recharge` | 无（且生产锁死） |
| `GET /api/v1/member/verify-code` | 无 |
| `POST /api/v1/orders/{id}/review` | 封装了未用 |
| `GET /v1/plugins/available` | 封装了未用 |
| `GET /v1/member/consumptions/{id}` | 详情页存在但不可达 |
| `POST /v1/verify` | 封装了未用 |
| `GET /v1/miniapp/member/commission-records` | 封装了未用 |

商家/超管/POS/订阅/渠道等 API 本来就不该出现在顾客小程序，不记为缺失入口。

---

## 9. P0 / P1 / P2 建议

本阶段不实施。建议只针对「代码在、用户看不到」或「入口仍指向旧体验」。

### P0

1. **确认核销产品合同后再决定 `verify-qr`。**  
   若店员仍要扫顾客券码：当前唯一入口在不可达的 `card.vue`，等于功能下线。  
   若合同已改为结算自动核销：应把 `card.vue` / `verify-qr` 标成 LEGACY，避免以后又接到旧页。  
   现在两套文案同时存在（`card.vue` 叫出示二维码，券详情叫结算自动核销）。

### P1

1. `card.vue` 与 `MemberCard` Tab：保留一个会员卡入口，不要让独立页继续注册却无跳转。
2. 「我的」补券/积分入口，或明确会员中心是唯一资产入口，避免只逛「我的」的人找不到券。
3. 历史订单列表可点进详情，或明确「详情只在本桌弹层」。现在成功页/最近订单进弹层，列表进不了详情。
4. `consumption-detail` 要么从列表进去，要么不要再留独立页。
5. 删掉或停用三个 `subpkg-plugins` 占位页和未用的 `plugin.js`，避免被当成可做活动的入口。
6. 接上或删除 `menu.vue` 的 `goCoupons`（成功页去券包）。

### P2

1. 清理无引用 API：`login.js`、`customer.js`、`mockPayOrder`、`submitReview`、`getMyCoupons`、`bindInviter`、`getCommissionRecords`、`createVerification`。
2. 清理伴随 `.wxml/.wxss` 和 index 上未用的 Vant 注册。
3. `perf-debug` 保持隐藏即可，不要进「我的」。
4. 储值余额/充值：后端未对顾客开放前，不要做入口。
5. `points-placeholder` 与真积分页不要长期并存。

---

## 10. 本阶段边界

- 未修改任何页面、跳转、组件、API。
- 未新增功能。
- 未做真机点击；可达性以源码跳转与 `pages.json` 为准。
- 影响端：无运行时影响（仅本审计文档）。
