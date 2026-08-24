# MENU PERFORMANCE PHASE-03 MEASURE

```
MODE=READ_ONLY_MEASURE
DATE=2026-08-24
PHASE=P0-MENU-PERFORMANCE-MEASURE-PHASE-03
BASELINE=13d7355
SCOPE=分析 perf_sample，不改代码、不拆接口、不重构
AUTHORITY=
  docs/frontend/MENU_PERFORMANCE_AUDIT.md
  member-mini-client/src/subpkg-order/pages/menu.vue
  member-mini-client/src/utils/perf.js
  saas-base/app/api/v1/perf.py
  saas-base/app/api/v1/super_admin.py  GET /api/super/perf-stats
```

第一阶段：只分析数据。本文没有改产品代码。

---

## 0. 四问结论（先看这个）

| # | 问题 | 结论 |
|---|---|---|
| 1 | 缓存命中后 `first_content` 是否明显下降？ | **生产上还不能证实。** PHASE-02 只在 git `13d7355`，小程序走微信发版，不随 `git push` 上线。现有生产分位仍是 PHASE-01 编排（看见列表也等两次 HTTP）。代码预期重复进店会降到读缓存+一帧；**没有 PHASE-02 样本，不能写“已经下降”。** |
| 2 | 冷启动是否改善？ | **现网没有改善。** 无缓存时仍要等 `GET /v1/menu/items`。PHASE-02 上线后，冷启动 `first_content` 预期不再等 `shop/info`，但 P50 仍约等于菜单接口客户端耗时，不是秒开。 |
| 3 | 最大瓶颈是否已从前端编排转到 A/B/C/D？ | **现网：没有转走，仍是 D 编排**（骨架和打点等 `Promise.all`）。**仓库里的 PHASE-02：编排已不再是 `first_content` 的主因**；剩下是 A 后端 / B 网络，C JSON 体积未用量测排除，D 渲染仍解释不了 1.4s。 |
| 4 | 下一阶段是否值得优化 `shop/info` 或 menu payload？ | **现在不值得拆接口、不值得先砍 payload。** 先发 PHASE-02 小程序，再用 `menu_api` / `shop_info_api` 的 `server_ms` vs `network_approx_ms` 分位决定动谁。 |

分类口径（与审计相同）：A 后端处理 / B 公网与并行请求 / C JSON 体积 / D 前端编排与渲染。

---

## 1. 数据从哪来、哪里没有

### 1.1 已采到的生产客户端分位（PHASE-01 基线）

来源：中控台「性能监控」`GET /api/super/perf-stats?days=7`，PHASE-01 审计给定。本阶段未再登录中控台（接口无 token 返回 401）。

| 指标 | P50 | P95 | 样本窗口 |
|---|---:|---:|---|
| `menu_onload_to_first_content` | 1396ms | 3749ms | PHASE-01 给定 |
| `menu_onload_to_interactive` | 1392ms | 3729ms | 同上 |

这两条几乎相等（差 4ms / 20ms），与 PHASE-01 代码一致：同一 SelectorQuery 回调里连打。

中控台表 **只有** `metric + ms` 的 count/avg/p50/p95，**没有** meta，所以这个接口拆不出：

- 有缓存 vs 无缓存
- `server_ms` vs `network_approx_ms`
- PHASE-01 vs PHASE-02（`definition`）

### 1.2 本机查库

本机 MySQL `example_db.perf_sample`：**0 行**。不能用本机库代替生产。

### 1.3 生产库

样本在生产表 `perf_sample`（上报 `POST /api/v1/perf/report`）。本机：

- `root@iZ2ze1vb1w9yuqx7rdjwkpZ` DNS 无法解析
- `api.zhangbaiyang.com` / `39.102.86.170` SSH 可达，但本机只有 GitHub 部署公钥，登录被拒（`Permission denied (publickey)`）
- 因此 **本阶段没有把 `perf_sample` 行拉下来做 cache / server_ms 拆分**

`GET /api/v1/perf/report` 无对应读接口。要拆 meta，只能在 ECS 上只读查库，或以后给中控台加只读拆分（那是代码，本阶段禁止）。

### 1.4 PHASE-02 会不会已经进现网样本？

不会自动进。

- 后端 `git pull` 不影响顾客端打点逻辑（PHASE-02 只改了 `member-mini-client`）
- 小程序要微信开发者工具上传 + 审核发布
- PHASE-02 标记：`interactive.meta.definition = "ordering_context_ready"`（旧值 `category_and_dish_actions_available`）；`first_content_to_interactive` 在有缓存时应 > 0

在现网出现这些标记之前，所有 `first_content` 分位都应按 **PHASE-01** 读。

---

## 2. 现网数字在说什么（PHASE-01 包）

```
first_content P50 1396 ≈ interactive P50 1392
first_content P95 3749 ≈ interactive P95 3729
P95 / P50 ≈ 2.7
```

| 判断 | 依据 |
|---|---|
| 不是首图 decode | 打点只认 `.cat-item` + `.dish-item` 节点 |
| 不是分类 computed / `menu_processing` map | 那是内存循环，到不了秒级 |
| 不是 DishList 全量渲染主因 | 渲染在数据到达后，量级几十到两百毫秒，撑不起 P50 1.4s |
| 是「两次 HTTP 都回来才揭列表、才打两条指标」 | `createMenuInitialization` + 骨架 `:loading` OR `!orderingContextReady` |
| P95 是尾部，不是稳定 JS | 2.7 倍差是公网/服务端尾部分布 |

所以：**现网最大瓶颈仍是 D 编排（等网络），被 B（两次客户端 RTT）放大。** 还不能把 3.7s 判成「后端一定慢」或「JSON 一定大」，因为 `menu_api` / `shop_info_api` 的 `server_ms` / `network_approx_ms` 生产分位这次没取到。

Sidecar **已经在写**这些字段（`request.js` `recordApiTelemetry`）。缺的是查询，不是埋点。

---

## 3. 有缓存 vs 无缓存（现网拆不开）

`first_content` 的 meta **没有** `cache_hit`。`cache_hit` 在 `menu_processing` 上。应按 `meta.perf_session_id` 对齐。

| 会话形态 | PHASE-01 现网 | PHASE-02 代码预期 |
|---|---|---|
| 有菜单缓存 | 列表已在 DOM，骨架仍挡住；`first_content` 仍等两次 HTTP → 仍是 ~1.4s 这一档 | 立刻揭骨架并打 `first_content` → 约 100–300ms（机型/主线程） |
| 无菜单缓存 | 等菜单+店铺都成功 | `first_content` ≈ 菜单接口客户端耗时 + 一帧；`interactive` 仍等店铺上下文 |

**问题 1 的可证伪标准（发版后）：**

- 同一 `perf_session_id` 上 `menu_processing.cache_hit === true` 的 `first_content` P50 应明显低于 1396ms，目标带是 < 400ms
- `cache_hit === false` 的 `first_content` 不应掉到那个带，应贴近 `menu_api.client_ms`

注意：缓存命中但菜单接口抛错时，PHASE-02 仍会打 `first_content`，但 **不会** 写 `menu_processing`。这类会话 join 不上，应单独算「疑似有缓存、接口失败」，不要并进无缓存。

---

## 4. `interactive` 与 `first_content_to_interactive`

| | PHASE-01 现网 | PHASE-02 代码 |
|---|---|---|
| `interactive` 定义 | 与 first_content 同一回调 `category_and_dish_actions_available` | `ordering_context_ready`（`orderingContextReady === true`） |
| `first_content_to_interactive` | ≈ 0（同毫秒 consume） | 有缓存应为正：看见列表 → 可加购 |
| 加购闸门 | 仍是 `orderingContextReady` | **未改** |

现网 1396≈1392 说明间隔指标没有信息量。发版后若间隔 P50 仍 ≈ 0，说明要么没走到缓存路径，要么打点又并在一起了。

`interactive` 在 PHASE-02 之后仍约 `max(menu_api, shop_info_api)`。**优化看见列表 ≠ 优化可点餐。**

---

## 5. `menu_api` / `shop_info_api` 尾部

本阶段 **没有** 这两条的生产 P50/P95。下面是已经埋好、下次查库就能用的字段。

每条成功样本 meta：

```
client_ms, server_ms (X-Process-Time-Ms), network_approx_ms = max(client_ms - server_ms, 0)
status, http_status
```

判据（审计 §9 PHASE-03，仍然成立）：

| 模式 | 含义 | 下一刀 |
|---|---|---|
| `server_ms` P95 高，`network_approx_ms` 低 | A 后端 | 再考虑 shop/info 发券是否挡首屏；**先不要拆路由** |
| `network_approx_ms` P95 高，`server_ms` 低 | B 网络 | 连接/体积/弱网；不要先改 SQL |
| 两者都高 | A+B | 先看哪条接口是 `Promise.all` 的慢侧 |
| `menu_api` 体积随规格膨胀且 `network_approx` 高 | 才轮到 C | 仍不在本阶段拆 `spec_groups` |

`shop/info` 在 GET 上并发：进店券（可能写库）、新客券预览、分销开关。这是 **A 的结构嫌疑**，不是已证实的现网慢因。

列表 JSON 带齐 `spec_groups`（卡片只用 `has_options`）是 **C 的结构嫌疑**。仓库里的 SQLite 压测（`scripts/benchmark_menu_api.py`）描述应用层序列化，**不是** 生产 MySQL 或公网证据，不能拿来下「该砍 payload」的结论。

`menu_processing` 预算 10s，现网没有分位；从代码看只是一层 `desc` map，可忽略，除非查库后 P50 异常。

---

## 6. 瓶颈归属（现网 vs 仓库）

```
现网（未发 PHASE-02 小程序）
  D 编排（等 Promise.all + 骨架）  ← 最大
    └─ 放大 B 两次客户端请求
    └─ A/C 未用量测拆开

仓库 13d7355（未进微信包）
  first_content：缓存路径不再走 D 编排
  interactive / 冷启动 first_content：仍是 max/单条 HTTP → A 或 B
  D 渲染：次要
  C payload：未证实
```

**问题 3：** 对用户正在打的 1396/3749，**没有**转移到 A/B/C；仍是 D。对已经合进 git 的 PHASE-02，**first_content 的设计瓶颈已经离开编排**，但要等发版后的样本签字。

不要把「仓库已改」写成「现网已快」。

---

## 7. 下一阶段值不值得动 shop/info 或 payload

**不值得作为立刻实施项。禁止提前拆接口。**

顺序：

1. 把 `13d7355` 的小程序发到体验版/正式版（本阶段不发版、不改代码）。
2. 等带 `definition=ordering_context_ready` 的样本（建议至少几十条有缓存会话）。
3. 在 ECS 上只读拆分（附录 SQL）。看：
   - 有缓存 `first_content` 是否进入 <400ms
   - `interactive` 是否仍 ~1.4s
   - `shop_info_api` vs `menu_api` 谁是慢侧，以及 `server_ms` vs `network_approx_ms`
4. **只有** shop/info 的 `server_ms` P95 明显高于菜单、且挡住 `interactive` 时，才单独开后端任务（发券移出首屏 GET 等）。那是以后的阶段，不是现在。
5. **只有** `network_approx_ms` 高且与菜品数/规格数相关时，才考虑列表不带 `spec_groups`。现在没有体积分位，砍字段是猜测。

PHASE-02 若已让重复进店「看见菜单」达标，下一刀应打在 **可点餐等待**（`interactive`），对象仍可能是 shop/info，但要用数字选，不要先拆。

---

## 8. 附录：生产只读拆分（有 ECS 登录后再跑）

不要改表。在 `/www/wwwroot/xiao/saas-base` 用只读 SQL（库名以服务器 `.env` 的 `DATABASE_URL` 为准）。`meta` 是截断到 500 字的 JSON 字符串。

```sql
-- 总览（近 7 天）
SELECT metric,
       COUNT(*) AS n,
       MIN(ms) AS min_ms,
       MAX(ms) AS max_ms
FROM perf_sample
WHERE created_at >= UTC_TIMESTAMP() - INTERVAL 7 DAY
  AND metric IN (
    'menu_onload_to_first_content',
    'menu_onload_to_interactive',
    'first_content_to_interactive',
    'menu_api',
    'shop_info_api',
    'menu_processing'
  )
GROUP BY metric;
```

分位与 JSON 拆分用 Python 更稳（截断 JSON 直接 `JSON_EXTRACT` 会失败）：

```python
# 在服务器上只读：按 metric 收集 ms；解析 meta 得 definition / cache_hit / server_ms / network_approx_ms / perf_session_id
# 1) first_content 按同 session 的 menu_processing.cache_hit 分组
# 2) interactive 按 definition 分 PHASE-01 / PHASE-02
# 3) menu_api / shop_info_api 只取 status=success，对 client_ms、server_ms、network_approx_ms 做 P50/P95
```

PHASE-02 已上线的最低证据：

- 至少 1 条 `interactive` meta 含 `"ordering_context_ready"`
- 有缓存会话的 `first_content_to_interactive` 中位数 > 0

在那之前，不要根据 1396/3749 再改前端编排，也不要拆 `shop/info`。

---

## 9. 本阶段明确没做

- 没有改 `menu.vue` / 后端 / 数据库
- 没有拆 `shop/info`，没有从菜单 JSON 拿掉 `spec_groups`
- 没有发微信小程序
- 没有拿到 `menu_api` / `shop_info_api` 生产分位（访问限制，见 §1.3）

下一份度量报告应贴：有/无缓存 `first_content` 分位、`first_content_to_interactive` 分位、两条 API 的 `server_ms` vs `network_approx_ms`。没有这些数，就还不能开 PHASE-04 接口改动。
