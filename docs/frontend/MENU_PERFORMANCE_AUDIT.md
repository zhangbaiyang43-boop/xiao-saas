# MENU PERFORMANCE AUDIT

```
MODE=AUDIT_PLUS_PHASE_02
DATE=2026-08-24
PHASE=P0-MENU-PERFORMANCE-IMPLEMENTATION-PHASE-02
AUDIT_PHASE=P0-MENU-PERFORMANCE-AUDIT-PHASE-01
BASELINE=fe7f6e0（审计稿）；实施前 HEAD 同
SCOPE=member-mini-client 菜单首屏展示时序。后端 / 支付 / 加购规则 / 图片 / DishList 结构未改。
CODE_CHANGE=YES（仅 menu.vue 编排 + 契约测试）
NEW_FRAMEWORK=NO
BUSINESS_LOGIC_CHANGE=NO
AUTHORITY=
  member-mini-client/src/subpkg-order/pages/menu.vue
  member-mini-client/src/subpkg-order/composables/useMenuInitialization.js
  member-mini-client/src/subpkg-order/components/DishList.vue
  member-mini-client/src/utils/perf.js
  member-mini-client/src/api/request.js
```

PHASE-01 只审计。PHASE-02 只改前端展示时序，不重构菜单组件，不引入框架，不改加购/支付业务逻辑。

生产监控（本阶段给定，未再查库）：

| 指标 | P50 | P95 |
|---|---:|---:|
| `menu_onload_to_first_content` | 1396ms | 3749ms |
| `menu_onload_to_interactive` | 1392ms | 3729ms |

两条几乎重合，不是巧合。见 §2。

分类：

- **A 后端问题**：服务端处理、查询、序列化、GET 上的写操作
- **B 网络问题**：公网 RTT、payload、并行请求、微信到 `api.zhangbaiyang.com`
- **C 图片问题**：COS、缩略图、lazy-load、首屏图数量
- **D 前端渲染问题**：关键路径编排、骨架屏、节点数量、分类派生

---

## 1. 指标实际量的是什么

起点：`menu.vue` `onLoad` 里 `markStart('menu_onload_to_first_content')` 和 `markStart('menu_onload_to_interactive')`。

**不包含**：分包下载、扫码、entry 解析、`entry_to_menu`。`subpkg-order` 已在 `pages/entry/index` / `pages/index/index` 上 `preloadRule`。冷启动直达菜单时，分包耗时在本指标之外。

终点：`observeMenuContent` 用 `uni.createSelectorQuery().in(dishList)` 同时查到 **`.cat-item` 和 `.dish-item`** 各至少一个节点。

同一回调里立刻记两条 duration，并立刻 consume `first_content_to_interactive`（时长 ≈ 0）。

因此：

- `first_content` ≠ 首张菜图 decode，≠ 骨架屏消失，≠ 可加购
- `interactive` 的 meta 写的是 `basic_ordering_actions_ready`，但打点时刻与 `first_content` 相同
- 空菜单没有 `.dish-item`，这两条指标不会上报（不会污染分位）

加购真正闸门是 `orderingContextReady`（`addToCart` / `openSpecSheet`）。该旗标在 `onCriticalReady` 里、SelectorQuery 之前置 true。所以「节点可见」和「允许加购」被绑在同一次 `Promise.all` 成功上。

---

## 2. 首屏加载流程（关键路径）

`onLoad` 同步做完桌号/店铺 id、`loadMyOrders`（本地 storage）、支付草稿、鉴权刷新后，进入 `createMenuInitialization.run`。

```
onLoad markStart
  ├─ loadMenu()            GET /v1/menu/items     ─┐
  └─ loadShopSettings()    GET /v1/shop/info      ─┤ Promise.all
                                                   ▼
                              orderingContextReady = true
                              observeMenuContent（nextTick + SelectorQuery）
                              同时记下 first_content 和 interactive
                                                   ▼
                              才启动 deferred：会员 / 优惠券(800ms) / 桌会话 / 支付恢复
```

契约写在 `useMenuInitialization.js`，测试锁死：**菜单数据和 shop 权威上下文都必须成功，才 `onCriticalReady`**。会员、券、会话不在首屏指标里。这是对的；问题是 **连「看见分类和菜卡」也被绑在 shop/info 成功上**。

`loadMenu` 注释写「有缓存就先用缓存秒出首屏，跳过骨架屏」。实际没有：

1. 缓存命中会立刻写 `allDishes`，`loading = false`。
2. 骨架屏 prop 是 `loading || (!orderingContextReady && !orderingContextFailed)`。`orderingContextReady` 仍要等 **两次网络都成功**。
3. `observeMenuContent` 也只在 `Promise.all` 之后调用。

所以本地缓存目前既不缩短上报的 first_content，也不让用户先看到列表。缓存只是在骨架下面提前把节点放进 DOM。

`loadShopSettings` 同样：有 `shop_info_cache_` 会先 `applyShopInfoState`，但仍 `await getShopInfo`。网络失败时即使缓存已应用，函数仍 `return false` → `onCriticalFailure` → 不可点餐 toast；`onCriticalReady` 不跑，指标不上报。

`menu_processing` 只做 `rawItems.map(d => ({ ...d, desc: d.desc || d.description || '' }))` 再按 version 决定是否替换列表。预算 10s，相对 1.4s 首屏可忽略。

---

## 3. 分类初始化

`useDishCategories`：`categories` 是 computed，扫一遍 `allDishes` 去重，再按 `category_order`（来自 shop/info）或默认权重排序；有「推荐/招牌/热销」tag 时前置「推荐」。

`dishesByCategory(cat)` 是 **函数不是 Map**：每个分类一次 `filter` 全量菜品。模板里按分类嵌套 `v-for`，每轮渲染代价约 `分类数 × 菜品数`。推荐分类把招牌菜再渲染一遍（节点和图片翻倍占用）。

`applyDefaultCategoryIfNeeded` 在缓存命中、接口返回、`finally` 各走一次。shop/info 后到的 `category_order` 会让 sidebar 再排一次，多一次列表重排，不是秒级问题。

**结论**：分类派生是 D，便宜。真正贵的是它产出的 **全量嵌套列表**，以及分类顺序依赖 shop/info（把 D 绑回 A/B）。

---

## 4. DishList 与首次渲染数量

默认 Tab 是点餐（`activeTab = 'order'`）。DishList `v-show`，HomeTab / MemberCard 也是 `v-show`，**首屏就会创建**，只是不显示。

弹层 `v-if`（Checkout / Spec / CouponPicker / Welcome / Success / 本桌订单等）首屏不创建。

DishList：左侧 `scroll-view` 渲染全部 `cat-item`；右侧 **按分类渲染全部菜卡，无窗口、无分页**。每张卡固定 `236rpx` 高 + `16rpx` 间距。首屏可视大约 4 张卡 + 全部侧栏分类。屏幕外的卡、图、`PriceText` 仍然进节点树。`lazy-load` 只约束图片下载，不约束组件创建。

每张卡还挂一个自定义组件 `PriceText`。微信里自定义组件比普通 view 贵。

首屏常驻自定义组件（不含弹层）：

| 组件 | 数量 | 备注 |
|---|---:|---|
| ShopHeader / CouponBar / CartBar / BottomNav / LoadingStates / order-bubble | 1 各 | 点餐 Tab 常驻 |
| DishList | 1 | 两个 scroll-view |
| HomeTab + MemberCard | 1 各 | `v-show`，首屏仍创建 |
| PriceText | = 菜卡数 | 含推荐分类重复 |
| 原生 `<image>` | ≈ 菜卡数 + 店 Logo | 见 §5 |

量级（中位店估 8 分类 / 50 菜 / 5 道进推荐）：侧栏 9 项 + 菜卡 ~55 + PriceText ~55 + 图 ~55。这能解释 **数据到达后 50–200ms** 的 setData/节点成本，解释不了 P50 1396ms，更解释不了 P95 3749ms。

滚动时每 150ms 一次 SelectorQuery（侧栏高亮），发生在首屏之后。

---

## 5. 菜品图片策略

`dishImage()`：`image_url || image || cover_image`，对 `http(s)` 拼 COS 万象：

`imageMogr2/thumbnail/240x/format/webp`

列表默认 240px；规格弹层 750。生产桶 `poster-system-1253573799` 已开数据万象、未开原图保护（见 `Claude.md`）。列表图策略本身是对的。

模板里 `dishImage(dish)` 调用两次（`v-if` 和 `:src`）。`lazy-load` 已开。失败走本地 `dish-placeholder.png`。

**不在本指标里。** SelectorQuery 只认节点，不认 decode。骨架消失后用户仍可能看见灰底/占位，那是感知问题，不是 1396ms 的组成。

仍属 C 的点：

- 店 Logo（ShopHeader）走原图 URL，没有缩略图参数。
- 全量 `<image>` 仍创建；微信并发有限，首屏 4 张小 webp 通常不是主因，推荐分类重复加载同一 URL 会浪费。
- 非 `http(s)` 或非 COS 的地址原样下载，无缩略图。
- 首屏指标优化阶段不要先动图片管线。

---

## 6. 菜单 API 返回后的数据处理

顾客端 `GET /v1/menu/items?shop=`。服务端 `_list_menu_items`：租户校验 → 上架菜品 → `TenantConfig.business_info.menu_item_specs` → 每道 `serialize_item`（含 **完整 `spec_groups`** + `has_options`）→ `{ items, version }`。`version` 是本批 `updated_at` 最大值，无额外查询。慢请求会打 `SLOW_MENU_API` / `VERY_SLOW_MENU_API`（500ms / 1000ms）。

客户端：

- 有 version 缓存则先灌 `allDishes`。
- 网络回来后 `map` 一层 `desc`，version 变了才替换。
- 写回 `menu_cache_{shopId}`。

处理本身不是瓶颈。列表 JSON 带齐规格组，会加大 **B payload**；卡片其实只用 `has_options`。本阶段范围是小程序，记下即可。

`GET /v1/shop/info` 在首屏 `Promise.all` 里，而且在 GET 上并发：发进店券（可能写库）、新客券预览、分销邀请开关。这是 **A**，会抬高 `max(menu_api, shop_info_api)`。

请求 sidecar 已记 `menu_api` / `shop_info_api` 的 `client_ms`、`server_ms`（`X-Process-Time-Ms`）、`network_approx_ms`。本阶段没有这三条的生产分位。**分不清 P95 是 A 还是 B 的主因，必须先查这三条。**

---

## 7. A / B / C / D 对照

### A 后端

| 现象 | 证据 | 对 1396/3749 的作用 |
|---|---|---|
| shop/info 与菜单并列卡首屏 | `loadCriticalContext: loadShopSettings` | 首屏 = max(两接口) |
| shop/info GET 发券 + 预览 + 分销 | `menu.py` `asyncio.gather` 三个独立 session | 拉长较慢的那条 |
| 菜单列表带全量 spec_groups | `serialize_item` | 放大 JSON，间接变 B |
| 菜单查询 + TenantConfig 规格 JSON | `_list_menu_items` | 大店/大规格时 server_ms 上升 |

服务端目标 `<100ms`（`saas-base/PERFORMANCE.md`）只管 `X-Process-Time-Ms`，不含公网。即使后端达标，客户端仍可能 >1s。

### B 网络

| 现象 | 证据 | 作用 |
|---|---|---|
| P95/P50 ≈ 2.7 | 给定分位 | 典型公网/运营商尾部，不是稳定 JS |
| 首屏强制两次 request | Promise.all | 微信到 API 的 RTT 付两次，取较慢者 |
| 缓存命中仍等完整响应 | `loadMenu` / `loadShopSettings` | 重复进店也吃满 RTT |
| 无 HTTP 缓存/ETag | 客户端只用 storage version | 304 省不下来 |

P50 1.4s 的主体应是 `max(menu_api.client_ms, shop_info_api.client_ms)` + 一帧查询。P95 3.7s 同结构的尾部。

### C 图片

| 现象 | 证据 | 作用 |
|---|---|---|
| 不进 first_content | SelectorQuery 只查 class | **解释不了给定分位** |
| 列表 240 webp + lazy-load | `useOrderFormatters.dishImage` | 策略已对 |
| Logo 原图；推荐分类重复图 | ShopHeader；`dishesByCategory('推荐')` | 感知/带宽，次要 |
| 全量 image 节点 | DishList 无窗口 | 次要 D×C |

### D 前端渲染

| 现象 | 证据 | 作用 |
|---|---|---|
| 看见列表也要等 shop/info | initialization 契约 + 骨架屏 OR | **主因编排** |
| 缓存不揭骨架、不打 first_content | 注释与代码相反 | 重复访问优化失效 |
| first_content ≡ interactive | 同一 SelectorQuery 回调 | 指标塌缩，掩盖图/加购 |
| 全量菜卡 + PriceText×N + HomeTab/MemberCard 预创建 | DishList / menu 模板 | 数据到达后的小头 |
| `dishesByCategory` 每次 filter | 函数 prop | 小 |
| `menu_processing` 一层 map | `loadMenu` | 可忽略 |

---

## 8. 性能瓶颈排序（对给定两条指标）

从贡献从大到小。括号里是类别。

1. **首屏把门挂在 `max(GET /v1/menu/items, GET /v1/shop/info)` 上，本地缓存不能揭列表、不能打点。**（D 编排，放大 B）  
   这是 P50≈1.4s 的主结构。没有这条，缓存进店应接近「读 storage + 一帧」。

2. **P95 尾部来自这两次客户端耗时的慢侧，不是渲染。**（B 为主，A 未知）  
   必须用已有 `menu_api` / `shop_info_api` 的 `server_ms` vs `network_approx_ms` 拆开。本阶段没有数字，不能把 3.7s 判成「后端慢」或「纯弱网」。

3. **`/v1/shop/info` 把发券/预览/分销放进首屏 GET。**（A）  
   只在 shop/info 经常是 Promise.all 的慢侧时才值得动。先看分位再改。

4. **菜单 JSON 带齐 spec_groups。**（A 形态 → B 体积）  
   卡片已有 `has_options`。下一阶段不要先做。

5. **全量 DishList + PriceText×N + 隐藏 Tab 预创建。**（D）  
   解释数据到达后的一小段，解释不了 1.4s/3.7s。禁止本阶段上虚拟列表。

6. **图片。**（C）  
   不在给定指标里。列表缩略图已做。不要作为 PHASE-02 主项。

7. **分类 computed / menu_processing map。**（D）  
   不是瓶颈。

**不要做的判断：**

- 不要因为 interactive≈first_content 就去「加速加购交互」。那是打点写在同一时刻。
- 不要为 1396ms 重写 DishList 或换渲染框架。
- 不要在没有 `menu_api`/`shop_info_api` 分位之前改后端发券或拆规格字段。

---

## 9. 下一阶段最小优化方案

目标：只动编排，不改点餐规则（没有 shop 权威上下文仍不能加购），不改 UI 合同，不上虚拟列表，不换图片库。

### PHASE-02（建议立刻做，仅 member-mini-client）

范围必须小：

1. **缓存命中揭骨架**  
   LoadingStates 的 `loading` 只跟「没有可展示的菜单数据」走，不要 OR `!orderingContextReady`。这是兑现现有注释，不是新业务。  
   `orderingContextReady` 继续闸 `addToCart` / `openSpecSheet` / 提交。

2. **缓存命中后立刻 `observeMenuContent`**  
   不要等 `Promise.all`。`first_content` 应对「分类+菜卡节点在」。网络仍在后台校对 version。  
   `menu_onload_to_interactive` 仍在两次关键请求成功（现契约）后打，两条指标才能分开，才能看见「看见菜单」和「可点餐」的差距。

3. **shop 缓存且已 `applyShopInfoState` 时，网络失败不要 `return false` 把整次 critical 判死**  
   展示用缓存；点餐闸门是否放行要单列，避免「屏幕上有菜、指标没有、toast 不可用」搅在一起。产品语义保持：没有权威 shop 就不加购。

禁止写进 PHASE-02：虚拟列表、抽菜单 SDK、改 `dishImage`、拆 shop/info、从列表 JSON 去掉 spec_groups、新依赖。

预期（重复进店、有菜单缓存）：`menu_onload_to_first_content` P50 应从 ~1.4s 掉到「storage + 一帧」（量级 100–300ms 视机型）。冷启动无缓存的 P50 仍约等于较慢接口，PHASE-02 救不了。P95 冷启动仍是网络尾部。

### PHASE-03（先查数，再决定动谁）

度量结论见 [MENU_PERFORMANCE_PHASE03_MEASURE.md](./MENU_PERFORMANCE_PHASE03_MEASURE.md)。现网仍是 PHASE-01 分位；PHASE-02 小程序尚未进入 `perf_sample`。

从同一套 `perf_samples` 拉：

| 指标 | 要用的 meta |
|---|---|
| `menu_api` | `client_ms` / `server_ms` / `network_approx_ms`，P50/P95 |
| `shop_info_api` | 同上 |
| `menu_processing` | 确认仍可忽略 |
| `first_content_to_interactive` | PHASE-02 之后应 > 0 |

判据：

- `server_ms` P95 高 → 再开后端任务：shop/info 发券移出首屏 GET，或菜单规格延迟加载。
- `network_approx_ms` P95 高、`server_ms` 低 → 只做体积/连接，不动业务 SQL。
- PHASE-02 后 first_content 已低、interactive 仍高 → 再动 shop/info，仍不要动 DishList。

### 明确不做

- 重构 `menu.vue` / DishList。
- 引入虚拟列表框架或新图片组件。
- 改加购、支付、发券业务规则。
- 把图片当首屏 P0（除非 PHASE-02 后用户投诉的是灰图而不是等待）。

---

## 10. 结论

给定的 1.4s / 3.7s 量的是 **onLoad → 两次关键 HTTP 都成功 → 节点查询**，不是图，也不是分类 computed。

`first_content` 和 `interactive` 几乎相等，是因为写在同一回调。

已经写了菜单/店铺缓存，但骨架屏和打点仍等网络，所以重复进店也快不了。

下一刀最小：让缓存真正露出列表，并分开两条指标。然后再用已经在报的 `menu_api` / `shop_info_api` 拆 A 和 B。

---

## 11. PHASE-02 已落地（展示时序）

落地文件：`member-mini-client/src/subpkg-order/pages/menu.vue`。契约：`composables/__tests__/menu-first-content-timing.test.js`。`useMenuInitialization.js` 未改：两次关键请求仍必须成功才 `onCriticalReady`。

| 项 | 实施 |
|---|---|
| 缓存揭骨架 | DishList / LoadingStates 的 `:loading` 只跟 `loading`（菜单是否还没有可展示数据）。不再 OR `!orderingContextReady` |
| first_content | 缓存写入 `allDishes` 后立刻 `observeMenuFirstContent`（不 await 网络）。冷启动在菜单 JSON 写入后再观察。定义仍是分类+菜卡节点 |
| interactive | `orderingContextReady = true` 之后才 `recordMenuInteractive`。加购 / 选规格 / 提交闸门未改 |
| shop 缓存 | `loadShopSettings` 网络失败时 `return Boolean(cachedData)`：有已应用的店铺缓存则 critical 成功，没有则仍失败、不能加购 |
| 后台刷新 | `loadMenu` 仍 `await getMenuItems`；version 变化才替换列表 |

新加载流程：

```
onLoad markStart
  loadMenu()
    有缓存 → 写 allDishes，loading=false，observe first_content（不挡网络）
    GET /v1/menu/items 后台刷新
  loadShopSettings()
    有缓存 → applyShopInfoState
    GET /v1/shop/info 刷新；失败且无缓存 → 不能加购
  Promise.all 都 true
    → orderingContextReady = true（可加购）
    → record interactive
```

### 指标预期（生产需等下一轮采样，本阶段没有新 P50/P95）

| 指标 | PHASE-01 基线 | PHASE-02 预期 |
|---|---|---|
| `menu_onload_to_first_content` 重复进店（有菜单缓存） | P50 1396 / P95 3749 | 降到读 storage + 一帧（约 100–300ms 视机型） |
| `menu_onload_to_first_content` 冷启动无缓存 | 同上 | 约等于菜单接口客户端耗时 + 一帧，不再等 shop/info |
| `menu_onload_to_interactive` | 与 first_content 几乎相等 | 仍约 `max(menu_api, shop_info_api)`；与 first_content 分开 |
| `first_content_to_interactive` | ≈ 0 | 重复进店应为正值（看见列表到可点餐） |

未做：后端、虚拟列表、图片、加购规则。PHASE-03 仍是先查 `menu_api` / `shop_info_api` 的 `server_ms` vs `network_approx_ms`。
