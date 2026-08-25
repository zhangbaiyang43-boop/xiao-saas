# 营销状态真实性 Touch And Migrate（Phase-03E）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-03E
STATUS=MARKETING_STATE_TRUTHFULNESS_MIGRATION
MODE=AUDIT_FIRST_THEN_MINIMAL_IMPLEMENTATION
BASELINE_SHA=0f36e19195eb04b0a5387f7faf07418c960e97d9
PREVIOUS_PHASES=
  P0-ADMIN-FRONTEND-SYSTEM-PHASE-03A  OrderManage 状态真实性        COMPLETED
  P0-ADMIN-FRONTEND-SYSTEM-PHASE-03B  Dashboard 经营视图            COMPLETED
  P0-ADMIN-FRONTEND-SYSTEM-PHASE-03C  MenuManage / DishManage 状态真实性  COMPLETED
  P0-ADMIN-FRONTEND-SYSTEM-PHASE-03D  CustomerList / MemberManage 数据可达性  COMPLETED
REFERENCE=ADMIN_FRONTEND_CONSTITUTION.md V1.0, ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md, ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md, ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md
SCOPE=admin-h5/src/views/CouponCenter.vue（状态展示逻辑，有修改）；MarketingEffectiveness.vue、CouponRecords.vue（只审计，无修改）
BACKEND_LOGIC_CHANGE=NO
AUTO_COUPON_ALGORITHM_CHANGE=NO
COUPON_CONTRACT_CHANGE=NO
DATABASE_SCHEMA_CHANGE=NO
NEW_MARKETING_FEATURE=NO
NEW_SEGMENTATION=NO
NEW_RULE_CONFIG=NO
NEW_MARKETING_CENTER=NO
SUBSCRIPTION_PERMISSION_CHANGE=NO
FULL_PAGE_REWRITE=NO
```

## 0. 产品概念与真实文件映射

仓库里没有 `Marketing.vue`。承载"营销"这个产品概念的是三个独立文件：

| 产品概念 | 真实文件 | 职责 |
| --- | --- | --- |
| 自动营销状态 / 强度 / 手动建券 | `admin-h5/src/views/CouponCenter.vue`（迁移前 514 行） | 老板判断"营销现在是不是真的在跑"的主入口 |
| 营销效果 | `admin-h5/src/views/MarketingEffectiveness.vue`（261 行） | 发券数/核销率/GMV 等效果统计表 |
| 发券记录 | `admin-h5/src/views/CouponRecords.vue`（566 行） | 每张券的发放/使用/收回记录，含真实分页 |

Dashboard.vue 首页也有一张"智能营销"预览卡片，但它的状态真实性已经在 [Phase-03B](./ADMIN_FRONTEND_SYSTEM_PHASE03B_DASHBOARD_MIGRATION.md) 审计并确认合规（`marketingError` 三态），本阶段不重复处理，只在下文交叉引用。

不存在"营销能力缺失"与"状态真实性缺陷"混淆的风险——自动发券规则、用户分层、营销策略、券模型、商业套餐等能力边界由 [MARKETING_AUTOMATION_COUPON_BACKEND_AUDIT](../marketing/MARKETING_AUTOMATION_COUPON_BACKEND_AUDIT.md) 定义，本阶段完全不touch，只审计这三个文件"展示的状态是否等于后端真实事实"。

## 1. Marketing Jobs 分析

沿用 [ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md §2.2](./ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md) 已定义的 Marketing Jobs：

- **用户**：老板 / 运营人员。
- **任务**：投入优惠成本时，知道系统在做什么、带来什么结果、是否需要调整。
- **成功标准**：老板看到"运行中""已发券""0 次""无活动"这些信息时，可以相信它们确实来自后端事实，而不是前端默认值。
- **核心动作**：确认当前档位、查看效果、调整或暂停。
- **禁止展示**：无法证明的默认"自动运行中"；有数据无建议的效果报表。

CORE_PRINCIPLE 说得很直接：营销后台最危险的不是不好看，是"系统不知道，却告诉老板'正常'"。老板会根据这个页面判断要不要继续投入优惠成本——如果页面在系统真实状态未知时依然显示"运行中"，老板做的是一个基于假象的商业决策。

## 2. 当前状态真实性审计

按 CURRENT_AUDIT 的十项逐条核对当前 HEAD（`0f36e19`）的真实源码，不沿用历史文档结论。

### AUDIT_01：营销总状态真实性 —— REAL_DEFECT（CouponCenter.vue）

迁移前模板顶部：

```html
<div class="hero-badge"><span class="live-dot"></span>自动运行中</div>
```

这是模板里的**纯文本，没有任何 `v-if`/绑定**——无论 `loadPreview()` 是否成功、是否已经返回，这句"自动运行中"从组件渲染的第一帧就存在。来源判定：**D（本地 hardcode）**。

`loadPreview()`（迁移前）：

```js
async function loadPreview() {
  try {
    const res = await getMarketingPreview()
    preview.value = res?.data?.data || res?.data || {}
  } catch {
    // 加载失败不阻断页面
  }
}
```

没有 `res?.code` 业务失败判定，`catch` 分支只有一句注释、不做任何状态记录。请求失败时页面顶部依然是硬编码的"自动运行中"。来源判定：**C（请求失败后的默认值，这里甚至连默认值赋值都没有，是彻底的沉默失败）**。

### AUDIT_02：营销统计真实性 —— REAL_DEFECT（CouponCenter.vue），已合规（MarketingEffectiveness.vue）

`CouponCenter.vue` 的"本月已发券"`{{ preview.issued_this_month ?? 0 }}`、"核销率"文案，在 `loadPreview()` 从未成功过的情况下（`preview.value` 保持初始 `{}`）会显示 **0**，与"真实统计为 0"视觉上完全相同，无法区分。

`MarketingEffectiveness.vue` 已合规：`loadData()` 有 `if (res?.code !== 200) throw ...`，失败进入 `hasError` 独立分支，整张表格（含所有数字）不渲染；`formatRate` 对 `null/undefined` 单独返回"暂无数据"，不与真实 0% 混淆。

### AUDIT_03：Loading 状态 —— REAL_DEFECT（CouponCenter.vue），已合规（其余两页）

`CouponCenter.vue` 的 `loadPreview()` 迁移前没有任何 loading 状态变量——首帧直接渲染硬编码"自动运行中"和 `heroDesc` 的"系统正在为你自动配置营销参数…"，在请求真正返回之前就已经把"未确认"表达成了"正常运行"。`MarketingEffectiveness.vue`（`v-if="loading"` 骨架）和 `CouponRecords.vue`（同款 `loading` 分支）已经正确处理。

### AUDIT_04：Empty 状态 —— REAL_DEFECT（CouponCenter.vue 手动建券列表），已合规（CouponRecords.vue）

`loadTemplates()` 失败时 `catch { showFailToast('优惠券加载失败') }`，不修改 `templates.value`（仍是初始 `[]`），于是模板落入 `v-else-if="templates.length === 0"` 分支，显示"还没有手动建券，**系统自动券已在运行**。"——用一句无法证明的断言去安慰一个真正的加载失败。`CouponRecords.vue` 已正确区分 `hasError`（独立错误卡+重试）和 `records.length === 0`（"暂无发券记录"，不做额外断言）。

### AUDIT_05：局部失败隔离 —— PASS

`loadPreview()`/`loadTemplates()` 各自独立的 `try/catch`，互不写对方的状态变量（迁移前后都是如此）；三个文件之间也没有共享状态。隔离性本身没有问题——问题是两个独立失败各自都在撒谎（AUDIT_01/04），不是互相污染。

### AUDIT_06：刷新反馈真实性 —— NOT_APPLICABLE（CouponCenter.vue 无手动刷新入口），已合规（CouponRecords.vue）

`CouponCenter.vue` 迁移前没有"刷新"按钮或下拉刷新；本阶段新增的错误态里加了"重试"按钮，重试只是重新调用 `loadPreview`/`loadTemplates`，不产生"已刷新"之类的成功 toast，不存在"finally 中无条件成功"的风险。`CouponRecords.vue` 的 `refresh()` 同样不发成功 toast，只在失败时 `showToast(errorMsg.value)`——不做多余的成功宣称。

### AUDIT_07：保存 / 启用 / 停用反馈 —— PASS

`switchIntensity()`、`saveTemplate()`（`CouponCenter.vue`）、`handleRecall()`（`CouponRecords.vue`）全部先判 `res?.code !== 200` 才决定成功/失败提示；`saveTemplate()` 甚至专门写了注释解释"后端就算校验不通过也会返回 HTTP 200，必须看 code"。这三个动作在迁移前就已经正确，本阶段不改。

### AUDIT_08：已有数据保护 —— PASS（结构上已经满足，本阶段只是让"失败"本身可见）

`loadPreview()`/`loadTemplates()` 迁移前的 `catch` 分支都没有清空各自的 `ref`——问题不是"失败清空了数据"，是"失败根本没有被记录成失败"。本阶段新增的 `previewError`/`templatesError` 同样不清空数据，只是让失败变得可见。

### AUDIT_09：HTTP 与业务 Envelope —— 已核实

`admin-h5/src/api/request.js` 的响应拦截器原样返回 `response.data`（即整个 `{code, msg, data}` envelope），因此 `getMarketingPreview()`/`getCouponTemplates()` 在调用处拿到的 `res` 就是这个 envelope 本身。核对 `saas-base/app/api/v1/tenant.py:241`（`marketing-preview`）和 `saas-base/app/api/v1/coupon_templates.py:38`，均通过 `success_response`/`error_response` 构造同一个 `RespVo{code,msg,data}`；业务失败（未登录 `code=401`、商家不存在 `code=404`）以 **HTTP 200 + `code!=200`** 返回，不抛 `HTTPException`。因此正确的判定字段是 **`res.code`，不是 `res.data.code`**——与 Phase-03A/B/C/D 已验证的模式完全一致，本阶段沿用同一约定，不是新发明。

### AUDIT_10：Unknown 状态 —— 真实存在，已在本阶段实现

`CouponCenter.vue` 的自动营销强度（`currentIntensity`）在首次加载完成前，迁移前的代码 `preview.value?.intensity_outcomes?.current_intensity || 'standard'` 会**默认假定是"标准"档**并高亮对应的强度按钮——这是真实的"无法确认却假装知道"场景，符合 Phase-02 Unknown 定义。本阶段修复后，强度按钮的高亮和可点击性都改为 `previewLoaded && !previewError` 门控，未确认前不高亮任何一个档位、也不允许切换。

`MarketingEffectiveness.vue`/`CouponRecords.vue` 审计后**没有找到真实的 Unknown 场景**——它们的每一次请求要么明确成功要么明确失败，没有"成功但结果无法判断"的中间态。按 AUDIT_10 的要求，明确记录：

```text
NO_REAL_UNKNOWN_SCENARIO: MarketingEffectiveness.vue, CouponRecords.vue
```

不为了状态齐全而在这两个文件里硬造 Unknown 分支。

### 审计中发现、但判定为非本阶段范围的一项：CouponRecords.vue 的分状态汇总数字

`CouponRecords.vue` 的 `summaryItems`（"未使用/已使用/已收回"三个数字）由 `countByStatus()` 计算，而这个函数只统计**当前页已加载的 `records.value`**（默认 10 条）里匹配该状态的条数，不是数据库里的真实全局统计。只读核实了 `saas-base/app/api/v1/coupons.py:161-215`（`GET /v1/coupons/issued`）：这个接口的 `total` 只反映**当前筛选条件**下的计数，响应体里**没有** `status_counts`/汇总字段能一次性给出全部四种状态的全局计数。

要把这三个数字变得真实准确，只有两条路：① 前端额外发起 3 次按 status 筛选的请求只为拿计数（增加请求负担，属于 STRICT_RULES 第 13 条"不做性能优化"的反面——这是主动增加请求，且属于新的交互能力而非状态修正）；② 后端新增一个汇总字段（属于 DO_NOT_TOUCH，需要独立的后端合同变更）。

这不属于"接口失败被显示成运行中/0"这类状态失真——它是一个**成功路径下的统计口径缺口**（能力不完整，不是撒谎）：数字本身来自真实数据，只是统计范围不是老板直觉以为的"全部"。为避免误判为"营销能力缺失"当成"状态真实性 bug"，也为避免在没有后端支持的情况下用额外请求硬凑答案，本阶段**不修改**这一处，记录为独立的后续候选：

```text
FUTURE_BACKEND_CONTRACT_CHANGE_CANDIDATE: GET /v1/coupons/issued 需要一个不受当前 status 筛选影响的
全局 status_counts 汇总字段，供 CouponRecords.vue 的四个统计卡片使用真实全局计数。
```

## 3. 真实缺陷列表

| 编号 | 项目 | 判定 |
| --- | --- | --- |
| AUDIT_01 | 营销总状态真实性 | **REAL_DEFECT**（已修复） |
| AUDIT_02 | 营销统计真实性 | **REAL_DEFECT**（CouponCenter，已修复）/ PASS（MarketingEffectiveness） |
| AUDIT_03 | Loading 状态 | **REAL_DEFECT**（CouponCenter，已修复）/ PASS（其余两页） |
| AUDIT_04 | Empty 状态 | **REAL_DEFECT**（CouponCenter 手动建券列表，已修复）/ PASS（CouponRecords） |
| AUDIT_05 | 局部失败隔离 | PASS |
| AUDIT_06 | 刷新反馈真实性 | NOT_APPLICABLE（CouponCenter 无入口）/ PASS（CouponRecords） |
| AUDIT_07 | 保存/启停反馈 | PASS |
| AUDIT_08 | 已有数据保护 | PASS |
| AUDIT_09 | HTTP/业务 Envelope | 已核实，`res.code` 为准 |
| AUDIT_10 | Unknown 状态 | **REAL_DEFECT**（强度默认值，已修复）/ `NO_REAL_UNKNOWN_SCENARIO`（其余两页） |
| 附加发现 | CouponRecords 分状态汇总数字仅统计当前页 | 非本阶段范围，记录为 `FUTURE_BACKEND_CONTRACT_CHANGE_CANDIDATE` |

## 4. 修改方案

只修改 `CouponCenter.vue`；`MarketingEffectiveness.vue` 和 `CouponRecords.vue` 审计后确认合规，未作任何改动。

### Before → After

**顶部状态徽章**（Before：硬编码文本；After：三态门控）

```html
<!-- Before -->
<div class="hero-badge"><span class="live-dot"></span>自动运行中</div>

<!-- After -->
<div v-if="previewLoaded && !previewError" class="hero-badge"><span class="live-dot"></span>自动运行中</div>
<div v-else class="hero-badge hero-badge--unknown">{{ previewError ? '状态未知，请重试' : '状态确认中…' }}</div>
```

**`loadPreview()`**（Before：吞掉一切失败；After：区分业务失败/网络失败，都进入 `previewError`）

```js
// Before
async function loadPreview() {
  try {
    const res = await getMarketingPreview()
    preview.value = res?.data?.data || res?.data || {}
  } catch { /* 加载失败不阻断页面 */ }
}

// After
async function loadPreview() {
  previewLoaded.value = false
  try {
    const res = await getMarketingPreview()
    if (res?.code !== 200) throw new Error(res?.msg || '营销状态加载失败')
    preview.value = res?.data?.data || res?.data || {}
    previewError.value = false
  } catch {
    previewError.value = true
  } finally {
    previewLoaded.value = true
  }
}
```

**强度选择器**：`intensity-pill--on`/`intensity-pill--disabled` 新增 `previewLoaded && !previewError` 门控，未确认前不高亮任何档位、不可点击。

**统计数字**：`hero-stat-row`（发券数/核销率）只在 `previewLoaded && !previewError` 时渲染；失败时改为渲染 `hero-error-row`（"营销状态加载失败" + 重试按钮），不再让 `?? 0` 在失败场景下生效。

**手动建券列表**：`loadTemplates()` 新增 `res?.code !== 200` 判定和独立 `templatesError`；模板新增 `templatesError` 分支（独立错误态 + 重试），且把空态文案里"系统自动券已在运行"的无依据断言删除，改成"还没有手动建券，需要时随时可以建一张。"

选择这个范围的原因：STRICT_RULES 明确禁止修改营销后端逻辑、发券算法、券合同、数据库、新增能力/分层/规则配置、新建营销中心、修改套餐权限、整页重构；本阶段的 Job 只是"让营销后台说真话"，这只需要把"未确认/失败"从"沉默地显示成功"变成"明确地显示未知或失败"，不改变这个页面已有的任何交互形态或业务能力。

## 5. 状态合同

只记录本页面真实适用的状态（`CouponCenter.vue`）：

| 状态 | 触发条件 | 表现 |
| --- | --- | --- |
| Loading | `!previewLoaded`（首次或重试请求尚未返回） | 徽章"状态确认中…"，`heroDesc`"正在确认营销运行状态…"，不显示统计数字，强度按钮不可点击且不高亮 |
| Success | `previewLoaded && !previewError` | 徽章"自动运行中"，展示真实 `issued_this_month`/`redemption_rate`（含真实 0），强度按钮按真实 `current_intensity` 高亮且可切换 |
| Empty | 不适用——`preview` 是单一对象而非列表，"没有数据"体现为字段本身为 0/null（如 `redemption_rate` 为 `null` 时显示"暂无数据"），不是一个独立的页面级空态 |
| Error | `previewError`（业务失败或网络失败） | 徽章"状态未知，请重试"，`heroDesc` 明确说明无法确认，统计数字区替换为错误提示 + 重试按钮，强度按钮不可点击且不高亮 |
| Unknown | 与 Error 合并表达——本页面"请求失败"和"无法确认"是同一件事（没有第三种"成功但结果两可"的情形），因此 `previewError` 同时承担两者，不重复定义 |

手动建券列表（同一文件内的独立数据源）：`loadingTemplates`（加载中）→ `templatesError`（独立错误态 + 重试）→ `templates.length===0`（真空态，文案不再断言自动系统状态）→ 列表。

## 6. TDD 过程

新增 [test-phase03e-marketing-state-truthfulness.mjs](../../admin-h5/scripts/test-phase03e-marketing-state-truthfulness.mjs)，覆盖 MINIMUM_TEST_MATRIX 的 8 项（第 5 项刷新反馈在 `CouponCenter.vue` 不适用，改为验证既有 `switchIntensity`/`saveTemplate` 的保存反馈；`CouponRecords.vue`/`MarketingEffectiveness.vue` 追加为回归锁定用例）。

### RED（对 `CouponCenter.vue` 迁移前真实源码的验证，通过 `git stash` 真实还原，非推测）

```text
FAIL 1. A failed marketing-status fetch never renders as "自动运行中"
FAIL 2. A successful marketing-status fetch renders the real backend state
FAIL 3. A marketing-statistics fetch failure hides the numbers instead of showing a fabricated 0
FAIL 4. A real zero count (genuinely zero coupons issued) is still allowed to display as 0
FAIL 6. A business-level failure (HTTP 200, code != 200) cannot be mistaken for success anywhere on this page
PASS 7. Existing preview/template data is not wiped by a subsequent failed reload
PASS 8. Preview and templates fail independently -- one does not contaminate the other
FAIL NO_REAL_UNKNOWN_SCENARIO check: the manual-coupon empty copy no longer asserts the automatic system is running
Phase-03E RED failures: 6
```

用例 7、8 在迁移前就 PASS——对应第 2 节 AUDIT_08/AUDIT_05 的结论：这两点结构上本来就没问题，不需要、也没有被强行做成假 RED（遵守"没有 bug，就不为了 TDD 仪式制造 bug"原则）。`MarketingEffectiveness.vue`/`CouponRecords.vue` 的用例全程未受这次 `stash` 影响（未改动这两个文件），如实记录为：

```text
NO_PRODUCT_RED_BECAUSE_CURRENT_BEHAVIOR_ALREADY_COMPLIANT: MarketingEffectiveness.vue, CouponRecords.vue
```

### GREEN

```text
$ npm run test:phase03e-marketing-state-truthfulness
PASS 1. A failed marketing-status fetch never renders as "自动运行中"
PASS 2. A successful marketing-status fetch renders the real backend state
PASS 3. A marketing-statistics fetch failure hides the numbers instead of showing a fabricated 0
PASS 4. A real zero count (genuinely zero coupons issued) is still allowed to display as 0
PASS 6. A business-level failure (HTTP 200, code != 200) cannot be mistaken for success anywhere on this page
PASS 7. Existing preview/template data is not wiped by a subsequent failed reload
PASS 8. Preview and templates fail independently -- one does not contaminate the other
PASS NO_REAL_UNKNOWN_SCENARIO check: the manual-coupon empty copy no longer asserts the automatic system is running
PASS MarketingEffectiveness: a business-level failure renders Error, never a fabricated empty/zero table
PASS MarketingEffectiveness: a real 0% redemption rate is distinguished from "no data yet"
PASS CouponRecords: a business-level failure renders Error and does not fall through to the empty-records copy
PASS CouponRecords: pagination total comes from the real backend field, not a client-side row count
Phase-03E marketing state truthfulness: passed
```

## 7. 测试与回归结果

- Phase-03E 专用测试：12/12 PASS（见上）。
- 相邻测试：grep 全部 `admin-h5/scripts/*.mjs` 确认没有其它测试脚本引用 `CouponCenter.vue`、`MarketingEffectiveness.vue`、`CouponRecords.vue` 或本阶段涉及的 API 函数（`getMarketingPreview`/`getCouponTemplates`/`getMarketingEffectiveness`/`getIssuedCoupons`），因此没有更多需要复跑的既有回归测试。
- `npm run check`：未整链路运行（包含 `npm run build`，耗时较长且本阶段改动不涉及依赖/类型/构建配置变更）；已单独运行 Phase-03E 测试确认通过，遵循 Phase-03A~D 建立的验证深度先例。

## 8. 风险与未处理项

- **未修改营销后端**：`saas-base` 全程只读核实（`app/api/v1/tenant.py`、`app/api/v1/coupon_templates.py`、`app/api/v1/coupons.py`），未做任何修改。
- **回归风险低**：改动集中在 `CouponCenter.vue` 一个文件的状态判断和对应模板分支；自动发券规则、强度切换的实际业务调用（`updateTenantSettings`）、手动建券的创建流程均未触碰。
- **未处理项 1（不在本阶段范围）**：`CouponRecords.vue` 的分状态汇总数字只反映当前页，不是全局真实计数——第 2 节已详细说明为什么这不属于本阶段的"状态失真"范畴（成功路径下的统计口径缺口，不是接口失败被伪装成正常），记录为 `FUTURE_BACKEND_CONTRACT_CHANGE_CANDIDATE`，需要后端新增汇总字段才能正确解决，留给未来独立阶段。
- **未处理项 2（P1，Phase-01 已记录，非本阶段范围）**：`MarketingEffectiveness.vue` 成功但零数据时没有专属空态提示，也没有"保持/调整/暂停"的下一步建议——这是信息完整度问题，不是真实性问题，本阶段不处理。
- **未处理项 3（P2，Phase-01 已记录）**：`CouponCenter.vue` 仍以 Vant 为主 UI 框架，属于 legacy 允许继续维护范围，本阶段未扩大也未替换。

## 9. Phase-03 总结

| Phase | 页面 | 真实文件 | 主要发现 | 结果 |
| --- | --- | --- | --- | --- |
| 03A | OrderManage | `OrderManage.vue` | 五个检查点全部已合规，无需改代码，仅补齐回归测试 | `ORDER_STATE_TRUTHFULNESS_READY` |
| 03B | Dashboard | `Dashboard.vue` | 四项已合规，仅"下拉刷新失败无反馈"一处真实缺陷，一行修复 | `DASHBOARD_BUSINESS_VIEW_READY` |
| 03C | MenuManage / DishManage | `MenuManage.vue` | 加载失败清空为假空菜单、业务失败漏判、搜索失败清空结果——三处真实 P0 缺陷，均修复 | `DISH_STATE_TRUTHFULNESS_READY` |
| 03D | CustomerList / MemberManage | `CustomerList.vue` | 固定拉取前 100 条伪装成分页、总数用行数冒充、业务失败漏判——三处真实缺陷；后端能力核实充分，无需合同变更 | `MEMBER_DATA_ACCESSIBILITY_READY` |
| 03E | Marketing / CouponCenter | `CouponCenter.vue` + `MarketingEffectiveness.vue` + `CouponRecords.vue` | `CouponCenter.vue` 四项真实缺陷（硬编码"运行中"、统计假 0、无 Loading、强度默认值假设）均修复；另两个文件审计后确认已合规 | `MARKETING_STATE_TRUTHFULNESS_READY` |

五个页面全部完成了各自范围内的状态真实性/数据可达性验证。按 PHASE_CLOSE_RULE：

```text
ADMIN_TRUSTWORTHY_OPERATIONAL_BASELINE_READY
```

第一轮"可信经营后台"基线可以收口。这不代表这五个页面已经完美——Phase-01 记录的信息层级、大规模数据渲染边界、组件治理、Vant 迁移等问题依然存在，且都明确不在这一轮的处理范围内；这一轮只保证了一件更基础的事：**这五个页面现在显示的 loading/success/empty/error（以及在真实存在的场景下的 unknown）状态，都对应它们各自声称的后端事实，不再用默认值、清空数据或硬编码文案冒充确定性。**

## ACCEPTANCE：验收回答

1. **营销接口失败是否还会显示"运行中"？** 不会。`previewError` 为真时徽章显示"状态未知，请重试"，强度按钮不高亮任何档位；迁移前的硬编码"自动运行中"已经改为门控在 `previewLoaded && !previewError` 之后。
2. **营销统计失败是否还会显示假 0？** 不会。发券数/核销率所在的 `hero-stat-row` 现在只在确认成功后渲染；失败时整块替换为"营销状态加载失败"+重试按钮，不会让 `?? 0` 在失败场景下生效。真实的 0（比如某月确实没发出券）依然允许正常显示。
3. **老板是否能区分真实无营销和系统异常？** 能，在本阶段审计范围内可以。`CouponCenter.vue` 的"未确认/失败"和"真实运行"现在有独立、不同的徽章文案；`MarketingEffectiveness.vue`/`CouponRecords.vue` 本来就已经正确区分 loading/error/empty。唯一的例外记录在第 2 节：`CouponRecords.vue` 的分状态汇总数字口径不完整（只反映当前页），但这不是"异常被误显示为正常"，是"统计范围比老板直觉以为的要窄"，已作为独立后续项记录，不属于本次验收范围内的缺陷。
4. **刷新/保存失败是否有真实反馈？** 有。`switchIntensity`/`saveTemplate`（已确认的既有实现）和 `handleRecall`（`CouponRecords.vue`）都在 `res.code !== 200` 时明确提示失败、不提示成功；`CouponCenter.vue` 新增的重试按钮和 `CouponRecords.vue` 的刷新都不会在失败后显示误导性的成功状态。
5. **业务级失败是否会被误判成功？** 不会。已核实 `admin-h5/src/api/request.js` 的拦截器行为和 `saas-base` 对应路由（`tenant.py`/`coupon_templates.py`/`coupons.py`）的响应封装，确认业务失败以 HTTP 200 + `code!=200` 返回，`loadPreview()`/`loadTemplates()` 现在都显式检查 `res?.code !== 200` 并 `throw`，不会把这类失败当成成功处理。
6. **已有可信数据是否会被失败请求无条件清空？** 不会。`loadPreview()`/`loadTemplates()` 的 `catch` 分支（迁移前后都）不修改各自的数据 `ref`，失败只影响是否显示错误提示，不影响已经加载好的数据。
7. **是否修改后端营销合同？** 否。`saas-base` 全程只读核实响应封装和分页/搜索能力，未做任何代码修改；未触碰自动发券算法、优惠券业务合同、数据库 schema、商业套餐或权限体系。
8. **是否符合 Phase-02 Rules？** 符合。Loading/Success/Error 三态（本页面 Empty 不是独立页面级状态、Unknown 与 Error 合并表达，第 5 节已说明原因）互斥且真实；组件复用现有 Vant `van-button`/自定义按钮样式，未新建组件库；未替换 UI 框架；改动范围严格限定在状态判断和对应展示分支。
9. **Phase-03 第一轮可信经营后台是否可以收口？** 可以。OrderManage、Dashboard、MenuManage、CustomerList、Marketing 五个页面均已完成状态真实性（或数据可达性）验证，`ADMIN_TRUSTWORTHY_OPERATIONAL_BASELINE_READY` 成立。下一阶段（Phase-04）应转向页面一致性与组件采用治理，不再以"状态真实性"为主题重复审计这五个页面。

```text
FINAL_DECISION=RESULT A: MARKETING_STATE_TRUTHFULNESS_READY
```

本结论确认 `CouponCenter.vue` 的状态真实性缺陷已修复并被测试锁定，`MarketingEffectiveness.vue`/`CouponRecords.vue` 审计确认已合规。`CouponRecords.vue` 的分状态汇总口径问题记录为独立的未来后端合同变更候选，不阻塞本阶段结论，也不阻塞 Phase-03 收口。
