# 2026-08-17 Mini V1 Hotfixes

## MINI-HF-001 — MEMBER CARD DISPLAY

**Date:** 2026-08-17
**Area:** Mini / Member Card (`member-mini-client`, `MemberCard.vue` + `useMemberCard.js`)

**User Visible Problem:**
会员中心的会员卡：等级专属背景不显示（只有纯色/tint）、等级徽章显示为空的深绿色圆、部分文字（普通会员/MEMBER/升级提示/会员号等）在浅色背景上发虚看不清。

这不是单一 bug，是四层独立问题叠加，逐层诊断、逐层修复：

---

### Issue A — Design Token Gap

- **Symptom:** 部分 Mini UI 引用的 CSS 自定义属性未定义，样式回退成默认值。
- **Root Cause:** `DESIGN_TOKEN_DEFINITION_GAP` — `global.scss` 缺少 `--text-inverse`/`--ink`/`--bg-muted`/`--bg-subtle`/`--btn-primary-height`/`--btn-primary-radius`/`--btn-primary-font-size`/`--btn-primary-font-weight` 共 8 个 token 的定义，但多处组件已经在用 `var(--xxx)` 引用它们。
- **Decision:** 只补齐能用 git 历史（`SpecSheet.vue` 74614aa 等提交的 diff）或现行组件（`ShopHeader.vue` 已工作的黑色 chip）证明原始数值的 8 个 token，不猜测无证据来源的 token。
- **Commit:** `6d9ccf27cc2bb718a3920e9d4ac4bd167a993992`
- **Files:** `member-mini-client/src/styles/global.scss`
- **Remaining:** `--page-pad` 没有可证明来源的原始数值，明确留空未定义。`queue-take.vue:251` 仍引用它（见 Known Remaining Issues）。

---

### Issue B — Level Background

- **Symptom:** 会员卡背景应根据会员等级显示专属图（LV1/LV2/LV3 各一张），实际只显示纯色 tint 渐变，没有背景图。
- **Root Cause（两轮诊断）：**
  1. 首次诊断：`useMemberCard.js` 从未定义/返回 `memberIdentityCardStyle`，`MemberCard.vue` 也没有声明对应 prop 或绑定 `:style` —— `menu.vue` 单方面尝试传递一个下游从未消费的值（不是"代码被删掉"式的回归，是这个能力从未在这条分支的历史上完整存在过）。
  2. 二次诊断（真机验证后发现第一次修复不完整）：即便补上 `:style="background-image: url('/static/...jpg')"`，微信真机运行时本地静态图仍不显示 —— 同一张图片改用 `<image :src>` 在同一环境能正常加载，证明问题在"动态 inline style 里的本地 CSS url()"这个机制本身。
- **Decision:** `LOCAL_STATIC_MEMBER_BACKGROUND_USES_IMAGE_COMPONENT_NOT_DYNAMIC_CSS_URL` —— 背景改成真正的 `<image mode="aspectFill">` 节点（z-index 0）+ 独立 tint 叠加层（z-index 1），原有内容包进 z-index 2 的容器，不再通过动态 inline style 的 `background-image: url(...)` 引用本地素材。
- **Assets:**
  - LV1 → `/static/member-levels/card-bg-lv1.jpg`
  - LV2 → `/static/member-levels/card-bg-lv2.jpg`
  - LV3 → `/static/member-levels/card-bg-lv3.jpg`
- **Commits:** `417260d076e886c139e0f2ad7c7d88e9e296d860`（第一次尝试，不完整）→ `103df6ccb80f7e28e6c61b45f24bacb62fe375b9`（改用 `<image>`，最终方案）

---

### Issue C — Level Badge

- **Symptom:** 会员卡头像位置的等级徽章显示为空的深绿色圆，没有图案。
- **Evidence Chain（均为真机 / 编译产物验证，非推测）：**
  1. WXML badge node 存在：`<image class="member-avatar-badge" :src="memberLevelBadgeSrc" mode="aspectFit">`
  2. `memberLevelBadgeSrc` 计算正确，src 路径无误
  3. 真机 Wxml Inspector 实测：Box Model 是 `360 × 0` —— 节点尺寸真实塌缩为 0 高
  4. 改成 `96rpx` 固定尺寸后，节点尺寸恢复为约 `46 × 46px`（非零）
  5. 尺寸修复后仍不可见；真机 A/B 测试：WebP 触发 `[MEMBER_BADGE_LOAD_ERROR]`，`errMsg = "GET static/member-levels/level-lv1.webp 404 (Not Found)"`
  6. 同一节点把 `src` 临时切到同目录 JPG（`card-bg-lv1.jpg`）：真机立即正常加载显示 —— 证明不是节点/路径/尺寸问题，是这几个 WebP 文件本身的运行时加载问题
  7. Git 历史找回的 `level-lv{1,2,3}.png`（WebP 性能优化前最后一版，commit `141d4fe`）：Pillow 解码确认 `300×300 RGBA`，真实 alpha 透明通道（38%-41% 透明像素）；当前 WebP 是 `RGB`、无 alpha、约 30%-40% 纯黑底（透明通道在某次转换中丢失）
- **Decision:** `MEMBER_BADGE_RUNTIME_ASSET=PNG` —— 恢复历史 PNG **字节**（`git show 141d4fe:...` 直接落盘，非重新转换/重新导出/AI 生成），作为 `MemberCard` 徽章的运行时素材。
- **Assets:**
  - `/static/member-levels/level-lv1.png`
  - `/static/member-levels/level-lv2.png`
  - `/static/member-levels/level-lv3.png`
- **Commits:** `2abbf88c5f5e55344a5521378a8e00760a6e55af`（尺寸修复）、`76e985cd9dfcbe85fd6a17d6f36efbc9042d9183`（PNG 资产恢复）

---

### Issue D — Badge Dimension

- **Symptom:** Issue C 证据链第 3 点 —— 真机 `96% × 96%` 百分比尺寸在 `.member-avatar`（row-direction flex + `align-items: center`，非默认 `stretch`）的交叉轴上塌缩成 0 高。
- **Root Cause:** `PERCENTAGE_SIZE_RUNTIME_COLLAPSE` —— WXSS 渲染引擎对 flex 交叉轴上、作用在 `<image>` 替换元素上的百分比高度解析不稳定，`Styles` 面板甚至没有显示该规则被应用。
- **Decision:** 改成固定尺寸 `96rpx × 96rpx` + `display: block`（`<image>` 默认 inline，会带行高间隙）+ `flex-shrink: 0`，取代原来的 `96% × 96%`，属于防御性运行时合同，不依赖百分比解析。
- **Commit:** `2abbf88c5f5e55344a5521378a8e00760a6e55af`

---

### Issue E — Foreground Contrast

- **Symptom:** 会员卡文字（`店名 · 甄选会员`/`会员等级标题`/`MEMBER`/升级提示/`NO. xxxxxx`）统一用同一套浅金色（`#f3e6cf` 系），LV1 的亮绿底上对比度不够，真机发虚看不清。
- **Root Cause:** 文字颜色跨等级统一硬编码，没有按各等级底色单独适配深浅。
- **Decision:** 在既有 `MEMBER_LEVEL_CARD_META` 里为每个等级增加 `textPrimary/textSecondary/textTertiary` 三级深色，通过单一 `memberIdentityCardForegroundStyle` 计算属性以 CSS 变量（`--member-text-primary/secondary/tertiary`）下发，`MemberCard.vue` 六个文字选择器（`.mic-issuer`/`.member-level`/`.mic-sub`/`.mic-chevron`/`.member-upgrade-text`/`.mic-number`/`.mic-since`）改用 `var(--member-text-*)`。进度条金色渐变（`.member-progress-fill`）明确保留不变，作为"金属会员卡"的识别点。`.member-identity-card-content` 上提供 LV1 兜底默认值，style 意外为空时仍可读。
- **Commit:** `44b6a5b45b6727d92a4aee35706e988dfdbbf54a`

---

**Commits (完整链，按时间顺序):**

| SHA | Message |
|---|---|
| `6d9ccf27cc2bb718a3920e9d4ac4bd167a993992` | fix(mini): restore missing design tokens |
| `417260d076e886c139e0f2ad7c7d88e9e296d860` | fix(mini): restore member level card backgrounds |
| `2abbf88c5f5e55344a5521378a8e00760a6e55af` | fix(mini): stabilize member badge dimensions |
| `76e985cd9dfcbe85fd6a17d6f36efbc9042d9183` | fix(mini): restore reliable member badge assets |
| `103df6ccb80f7e28e6c61b45f24bacb62fe375b9` | fix(mini): render member card backgrounds as images |
| `44b6a5b45b6727d92a4aee35706e988dfdbbf54a` | fix(mini): improve member card text contrast |

**Files (最终涉及的核心文件):**
- `member-mini-client/src/styles/global.scss`
- `member-mini-client/src/subpkg-order/composables/useMemberCard.js`
- `member-mini-client/src/subpkg-order/components/MemberCard.vue`
- `member-mini-client/src/subpkg-order/pages/menu.vue`
- `member-mini-client/src/static/member-levels/level-lv1.png`
- `member-mini-client/src/static/member-levels/level-lv2.png`
- `member-mini-client/src/static/member-levels/level-lv3.png`
- `member-mini-client/src/subpkg-order/composables/__tests__/useMemberCard.test.js`
- `member-mini-client/src/utils/__tests__/preload-rules.test.js`

**Regression:**
截至 `44b6a5b`：Vitest 30 files / 287 tests PASS，legacy 3/3 PASS，`build:mp-weixin` PASS。

**Runtime Validation（区分已确认 vs 待确认）：**
- Issue B（Level Background，`103df6c`）：**WeChat 真机已确认**——用户明确反馈"会员背景图片 = 正常显示"。
- Issue C + D（Level Badge + Dimension，`2abbf88`/`76e985c`）：**WeChat 真机已确认**——用户明确反馈"会员等级徽章 = 正常显示"（LV1 PNG 在 OPPO 真机正常显示）。
- Issue A（Design Token Gap，`6d9ccf2`）：仅 Mini Gate（Vitest/legacy/build）验证，**未获得针对这次修复本身的独立真机确认**。
- Issue E（Foreground Contrast，`44b6a5b`）：仅 Mini Gate 验证，**尚未做真机视觉确认**（本条目建立时用户已转向排查另一个 bug，未回到这次对比度修复做真机验证）。

**Do Not Regress:**
- Member badge runtime assets use historical transparent PNG (`level-lv{1,2,3}.png`) — do not switch back to local WebP without WeChat runtime validation proving the 404 is resolved.
- Member badge fixed dimensions remain `96rpx × 96rpx` (not percentage) — percentage sizing on this node has a proven runtime collapse failure mode.
- Member card background uses a real `<image>` component layer, not a dynamic CSS `background-image: url()` — the latter has a proven runtime non-render failure mode on this platform.
- `.member-progress-fill` stays gold (`linear-gradient(90deg,#c9a668,#f3e6cf)`) — do not follow the text-contrast recolor onto the progress bar.

**Remaining:**
见文末 Known Remaining Issues。

---

## MINI-HF-002 — ORDER BUBBLE MUTUAL SUPPRESSION

**Date:** 2026-08-17
**Area:** Mini / Order Bubble (`member-mini-client/src/components/order-bubble/order-bubble.vue`)

**User Visible Problem:**
用户反馈：刚进入小程序时，若已有订单状态发生变化（如"已送达"），左下角的提示会跟另一条提示冲突。经代码诊断确认：首次连接提示（"点这里随时看订单进度"）与状态变化提示（比如"请确认菜品"）由两个互不知晓彼此的独立触发条件驱动，在冷启动、订单数据异步刷新恰好同时满足两个触发条件时会同时显示，两者都是左下角附近的悬浮提示条，造成遮挡和视觉噪音。

**Root Cause:**
`TWO_INDEPENDENT_CALLOUT_STATES_COULD_RENDER_SIMULTANEOUSLY` —— 两个提示分别由 `props.visible` 和 `props.tone` 两个独立的 `watch()` 驱动，彼此毫无协调。冷启动时如果订单数据异步同步导致气泡"首次出现"与"状态刷新"落在同一时间窗口，两个 watcher 各自独立触发，互不知道对方的存在。

**Decision:**
`MUTUAL_SUPPRESSION_WITH_CONTEXTUAL_CALLOUT_PRIORITY` —— 当前具体状态反馈优先于首次教学提示。由于两个 watcher 的实际触发顺序不保证，双向都做了处理：
- `visible` watcher：如果状态变化提示条（`showChangeCallout`）已经在显示，跳过首次引导提示，但仍写入 `HINT_STORAGE_KEY`，避免下次启动重复打扰。
- `triggerChangeFeedback`（状态变化提示条的显示函数）：如果首次引导提示（`showHint`）正在显示，先 `dismissHint()` 收起它，再显示状态提示条。

**Changed Files:**
- `member-mini-client/src/components/order-bubble/order-bubble.vue`
- `member-mini-client/src/components/order-bubble/__tests__/order-bubble.test.js`（新增，之前该组件零测试覆盖）

**Commit:** `13790a5f22539e7f7a5eab8ce75246573bc2796f`

**Regression:**
Vitest 31 files / 289 tests PASS（含新增的 2 条互斥回归测试），legacy 3/3 PASS，`build:mp-weixin` PASS。

**Runtime Validation:**
仅 Mini Gate 验证，**尚未做真机验证**——本次改动没有经过 WeChat 真机复现原始冲突场景后再验证修复。

**Do Not Regress:**
- Never render the onboarding hint and the status-change callout simultaneously.
- The specific current-state callout has priority over the generic onboarding hint.
- First-time hint storage semantics (`HINT_STORAGE_KEY`, "only ever show once") must remain preserved even when the hint itself is suppressed by a callout.

---

## Known Remaining Issues (2026-08-17 收口时点)

1. **`GROWTH_PAGE_MEMBER_BADGE_STILL_REFERENCES_LOCAL_WEBP`**
   **Status:** OPEN
   **Evidence:** `growth.vue:74` 的 `LEVEL_BADGES` 仍是 `level-lv{1,2,3}.webp`，跟 MemberCard 曾经的问题同一根因（Issue C 的 WebP 404），大概率会在 growth 页面复现同样的空徽章问题，但**尚未在该页面单独做真机验证确认**。
   **Priority:** P1 BEFORE FINAL RELEASE —— 与 MemberCard 徽章是同一类已证实的运行时失败模式，风险等级相同，只是尚未在这个页面单独触发/验证。

2. **`UNRESOLVED_DESIGN_TOKEN_PAGE_PAD`**
   **Status:** OPEN
   **Evidence:** `--page-pad` 在 `global.scss` 中仍未定义，`queue-take.vue:251` 仍在引用它。没有可证明的原始数值来源（页面根节点 padding 在其他地方分别是 `24rpx`/`32rpx`/`40rpx 32rpx`，不统一，无法推断唯一正确值）。
   **Priority:** P2 —— 不阻塞当前会员卡/气泡收口，需要产品/设计明确一个值才能推进，不能猜。

---

*本 Ledger 追加维护，不覆盖历史条目。*
