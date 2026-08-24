# P1-ORDER-ENTRY-CONSOLIDATION-PHASE-01

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
SCOPE=member-mini-client 订单入口
CODE_CHANGE=NO
VISIBILITY_AUDIT=docs/frontend/MINI_FEATURE_VISIBILITY_AUDIT.md
BASELINE_REQUESTED=ba12226
HEAD_AT_AUDIT=c3443fc
```

本阶段只审计订单相关代码。会员、优惠券、储值、核销不在范围。

用户给定边界（本审计用来对照现状，不是已经落地的代码合同）：

- **实时订单**：当前桌点餐过程
- **历史订单**：用户查看过去订单

---

## 一、当前订单入口地图

三套入口都还活着，职责并不相同。

| # | 入口文案 | 代码 | 实际打开 | 数据 |
|---|---|---|---|---|
| 1 | 本桌订单 / 已点菜品 | `menu.vue` `showOrders` → `OrderHistorySheet` 或 `TableBillSheet` | 点餐页底栏弹层 | 本机 `myOrders`（按店+桌+dining_session 缓存），不是 `GET /v1/member/orders` |
| 2 | 我的订单 | `mine.vue` `goOrders` | `/subpkg-member/pages/orders` | `GET /v1/member/orders` |
| 3 | 最近订单 | `mine.vue` `openRecentOrder` | `/subpkg-order/pages/menu?...&openOrders=1` | 扫全部 `my_orders_*` 本地缓存取最新一单，再用该单的 shop/table 进菜单并拉开弹层 |

支付成功页「查看订单详情」**不是第四套页面**，它复用入口 1。

### 1.1 我的订单 — `mine.vue`

服务行「我的订单」只去历史列表：

```518:528:member-mini-client/src/pages/mine/mine.vue
    const goOrders = () => {
      if (!isLoggedIn.value) {
        goLogin()
        return
      }
      // "我的订单" 这一行本身就写着"查看历史订单和消费明细"，点进去应该永远是完整的
      // 历史订单列表——不能因为本地缓存里存在 recentOrder 就顺手劫持成只看那一笔最新
      // 订单的详情。最近订单卡片（recent-order-card）自己已经单独绑了 openRecentOrder，
      // 这里不需要、也不应该重复那条分支。
      go('/subpkg-member/pages/orders')
    }
```

未登录会 `goLogin()`，不会进 `orders.vue`。

同一页另有「最近订单」卡片（`v-if="isLoggedIn && recentOrder"`），点击走 `openRecentOrder`，**不**走 `goOrders`。

合约测试钉死了「我的订单 → 列表」：`pages/mine/__tests__/mine-orders-entry.test.js`。

### 1.2 历史列表 — `orders.vue`

能力（源码全部能力，没有隐藏动作）：

- 必须 `customer_token`，否则 `reLaunch` 回我的
- `getMyOrders(skip, PAGE_SIZE)` → `/v1/member/orders`
- 分页 20，`onShow` 全量重载
- 展示：`status_text`、退款提示、时间、桌牌、份数、金额

没有：点击、详情、菜品行、取消、轮询、跳回本桌弹层。

后端列表字段同样不含 items（`saas-base/app/api/v1/member.py` `list_member_orders` 只返回 `order_id/status/status_text/total/created_at/pickup_no/dish_count/refund_required`）。

这是**历史订单中心的雏形**，还不是完整订单中心。

### 1.3 `openOrders=1` — `menu.vue` onLoad

唯一生产写入点在我的页最近订单：

```568:580:member-mini-client/src/pages/mine/mine.vue
    const openRecentOrder = () => {
      const table = recentOrder.value?.table || currentTableNo.value
      const shop = recentOrder.value?.shop || uni.getStorageSync('tenant_id') || customer.value.tenant_id || ''
      const query = [
        table ? `table=${encodeURIComponent(table)}` : '',
        shop ? `shop=${encodeURIComponent(shop)}` : '',
        'openOrders=1'
      ].filter(Boolean).join('&')
      uni.navigateTo({ url: `/subpkg-order/pages/menu${query ? `?${query}` : ''}` })
    }
```

`recentOrder` 来自本机所有 `my_orders_*` 键拼起来后按 `createdTs` 取最新，**不是** `/v1/member/orders`。

菜单页接到该参数后做两件事：

```1511:1512:member-mini-client/src/subpkg-order/pages/menu.vue
        await this.recoverPendingPaymentResult({ showDetail: options.openOrders === '1', presentSuccess: true })
        if (options.openOrders === '1') this.showOrders = true
```

即：可能先弹出支付成功恢复，再强制 `showOrders = true` 打开本桌弹层。

弹层数据是当前这次 `dining_session` 的本地 `myOrders`，不是「最近订单」那张卡片指向的历史订单 ID。注释已承认：必须带上订单自己的 shop/table，否则会对不上；即便 shop/table 对了，若会话已换代，弹层仍可能是空的或另一拨客人的本桌单。

### 1.4 支付成功页

`PaymentSuccessSheet.vue` 第三按钮文案是 `successText.viewDetail` = **「查看订单详情」**（`orderText.js` L31）。

```81:83:member-mini-client/src/subpkg-order/components/PaymentSuccessSheet.vue
          <view class="success-btn-ghost" @click="$emit('view-order-detail')">
            <text>{{ successText.viewDetail }}</text>
          </view>
```

`menu.vue` 处理：

```870:877:member-mini-client/src/subpkg-order/pages/menu.vue
    const viewOrderDetail = () => {
      showSuccess.value = false
      // 查看订单详情不是"结束这次结账"，不动购物车——不管是不是 preserveDraft。
      successMemberValue.value = null
      earnedCoupon.value = null
      successPreserveDraft.value = false
      refreshAllOrderStatuses()
      showOrders.value = true
    }
```

不跳 `orders.vue`。关掉成功页，打开本桌弹层。测试明确写了「进入订单列表」指的是这个弹层，不是会员订单页（`useCheckout.p0-b2b-payment-recovery-parity.test.js`）。

同函数还挂在点餐 Tab 的 `order-bubble` 上（`menu.vue` L170）。

### 1.5 本桌 Sheet 业务定位

`showOrders` 在 `menu.vue` 里分叉：

| 条件 | 组件 | 标题 | 定位 |
|---|---|---|---|
| `isSharedBillMode`（桌台账 / 餐后付） | `TableBillSheet.vue` | 已点菜品 | **本桌工作台**：进度、多人分组、继续加菜、结账 |
| 非分账（预付堂食） | `OrderHistorySheet.vue` | 本桌订单 | **本桌当前单**：状态、桌牌、菜品、同会话其它单折叠为「历史订单」 |

`OrderHistorySheet` 文件头写明：非分账下的「本桌订单状态 + 历史订单视图」。这里的「历史订单」是 **同一 `myOrders` 里非当前单**，不是全店会员历史。

数据来源 `useTableBillView.js`：`currentTableOrder` 从 `myOrders` 里挑未取消/未拒单的活跃单；`historyTableOrders` 是其余本地单。`useMyOrdersStore.js` 把列表存在 `my_orders_{shop}_{table}_{dining_session_id}`。注释写明这不是后端权威全量列表。

因此本桌 Sheet 是 **实时点餐过程中的桌台状态机 UI**，不是订单中心。

---

## 二、用户路径

### 路径 A — 正在这桌吃饭（实时）

```
扫码 → menu
  → 下单支付 → PaymentSuccessSheet
       →「关闭并等待」/「继续加菜」
       →「查看订单详情」→ OrderHistorySheet 或 TableBillSheet
  → 点餐 Tab 订单气泡 → 同一套 Sheet
  → 分账：Sheet 上继续加菜 / 呼叫结账
```

这条路径需要实时状态、桌牌、加菜、结账。`orders.vue` 目前做不到。

### 路径 B — 离开后看过去的单（历史）

```
menu BottomNav「我的」→ mine.vue →「我的订单」→ orders.vue
```

需要登录。看到的是本店会员维度的摘要列表，点不开。

### 路径 C — 「最近订单」卡片（混用）

```
mine 最近订单卡片 → menu?shop=&table=&openOrders=1 → 恢复支付成功？+ 打开本桌 Sheet
```

用户以为在看「那一笔最近的单」。代码打开的是 **那张桌子当前会话的实时弹层**。

---

## 三、存在冲突

1. **文案「订单详情」指向本桌弹层，不是详情页，也不是「我的订单」。**  
   成功页 `viewDetail: '查看订单详情'` → `showOrders = true`。

2. **「我的订单」和「最近订单」在同一屏，跳向两套系统。**  
   列表走服务端会员订单；卡片走本地桌台缓存。注释刻意拆开，用户仍会当成同一个「订单」。

3. **`openOrders=1` 把历史意图灌进实时工作台。**  
   会话已结束、换桌、或缓存跨店时，弹层可能空、或不是卡片那一单。

4. **`OrderHistorySheet` 内部也有「历史订单」。**  
   仅本会话其它本地单。和 `orders.vue` 的「历史」重名不同义。

5. **历史列表不是订单中心。**  
   无详情、无菜品、无操作。若把所有入口收成它，实时能力会丢（结账/加菜/进度/桌牌大字）。

6. **实时 Sheet 也不是订单中心。**  
   看不到其它桌、其它天、需登录才能列全的会员订单。

---

## 四、AB 方案

### 方案 A — 「我的订单」作为唯一订单中心

含义：成功页、最近订单、气泡，最终都进入 `orders.vue`（或它升级后的详情）。本桌 Sheet 不再承担「查看订单」语义。

要落地必须先补 `orders.vue`（至少：可点、菜品、状态、退款提示；实时桌还要加菜/结账）。

| | |
|---|---|
| 优点 | 一个心智：订单都在「我的订单」；消灭 `openOrders=1` 错配 |
| 缺点 | 当前列表撑不住实时工作台；若强行关掉 Sheet，餐后付/本桌加菜会断 |

**不可在本阶段直接把 Sheet 删掉。** 那是功能回退，不是收口。

### 方案 B — 保留多入口

维持三套，只改文案或不管。

| | |
|---|---|
| 优点 | 零改动；实时路径继续工作 |
| 缺点 | 「查看订单详情 / 最近订单 / 我的订单」继续三套语义；`openOrders=1` 冲突仍在 |

这不是收口，是维持审计里已经标出的问题。

### 方案 A 的可执行边界（推荐采用的形态，不是第三套产品名）

按用户给定的实时 / 历史切开，而不是合成一个页：

| 任务 | 唯一入口 | 实现 |
|---|---|---|
| 实时：这桌正在进行的单 | 点餐页气泡、成功页「查看本桌订单」、分账账单 Sheet | 现有 `OrderHistorySheet` / `TableBillSheet` |
| 历史：过去的单 | 我的 → 我的订单 | `orders.vue`（后续可加详情，本阶段只定入口） |
| 最近订单卡片 | **改为进历史列表**，或删卡片只留「我的订单」 | 不再写 `openOrders=1` |

成功页按钮建议改成「查看本桌订单」，避免「详情」一词。

`openOrders=1` 仅保留给「仍在本桌会话内需要自动拉开工作台」的恢复（例如支付恢复 `showDetail`），不要再从「我的」历史意图写入。

---

## 五、推荐方案

**推荐：按实时 / 历史拆入口（方案 A 的边界版，不是「只留 orders.vue」）。**

理由：

1. 用户自己已经把任务分成实时 vs 历史。代码里两套数据源正好对应：`myOrders` 本地会话 vs `GET /v1/member/orders`。
2. 本桌 Sheet 有加菜/结账/进度，历史列表没有。唯一订单中心若等于 `orders.vue` 现状，会拆掉实时链路。
3. 真正该收的是第三条：`最近订单 → openOrders=1`。它用历史卡片打开实时弹层，是冲突源。
4. 「我的订单」已经是历史唯一正规入口（`goOrders` 注释 + 测试）。不要再让最近订单把人带回菜单。

明确不推荐：

- 纯方案 B（继续三套）
- 纯方案 A 且立刻废弃 Sheet

下一阶段若实施（本文件不实施）：

1. `openRecentOrder` 改为 `go('/subpkg-member/pages/orders')`，或去掉最近订单卡片
2. 成功页 / 气泡文案改为「本桌订单」，继续 `showOrders = true`
3. `orders.vue` 保持历史中心；详情作为后续，不在入口收口里做会员/券/核销

---

## 证据索引

| 主题 | 路径 |
|---|---|
| 我的订单跳转 | `member-mini-client/src/pages/mine/mine.vue` `goOrders` |
| 最近订单 + openOrders | 同文件 `openRecentOrder` / `loadRecentOrder` |
| 历史列表 | `member-mini-client/src/subpkg-member/pages/orders.vue` |
| 会员订单 API | `member-mini-client/src/api/order.js` `getMyOrders`；`saas-base/app/api/v1/member.py` `list_member_orders` |
| 成功页按钮 | `PaymentSuccessSheet.vue`；文案 `orderText.js` `viewDetail` |
| 成功页处理 | `menu.vue` `viewOrderDetail` |
| 气泡 | `menu.vue` `order-bubble` `@click="viewOrderDetail"` |
| openOrders 消费 | `menu.vue` onLoad ~L1511 |
| 本桌 Sheet 分叉 | `menu.vue` L324–383 |
| 本桌数据 | `useTableBillView.js`；`useMyOrdersStore.js` |
| 入口测试 | `pages/mine/__tests__/mine-orders-entry.test.js` |

未改业务代码。影响端：无运行时影响。
