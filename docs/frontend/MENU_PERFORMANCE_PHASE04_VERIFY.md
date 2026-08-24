# MENU PERFORMANCE PHASE-04 PRODUCTION VERIFY

```
MODE=READ_ONLY_VERIFY
DATE=2026-08-24
PHASE=P0-MENU-PERFORMANCE-PRODUCTION-VERIFY-PHASE-04
BASELINE=9eb688d
SCOPE=只读生产 perf_sample。禁止改代码、禁止拆接口、禁止重构菜单。
AUTHORITY=
  docs/frontend/MENU_PERFORMANCE_AUDIT.md
  docs/frontend/MENU_PERFORMANCE_PHASE03_MEASURE.md
  saas-base/app/api/v1/perf.py
  saas-base/app/api/v1/super_admin.py
```

本阶段目标是用生产行数据回答：PHASE-02 编排优化有没有真正让缓存用户变快，以及下一刀该打 A/B/C/D 哪一类。

**结果：生产 `perf_sample` 的 meta 本机读不到。下面四问全部是「未验证」，不是「优化失败」。禁止据此拆接口。**

---

## 0. 三问结论

| # | 问题 | 结论 |
|---|---|---|
| 1 | 缓存命中用户是否达到预期提升？ | **未验证。** 没有把 `cache_hit` 和 `first_content` 对齐到同一 `perf_session_id` 的生产行。不能写「达到了」或「没达到」。 |
| 2 | 冷启动当前最大耗时来源？ | **未用新数据拆开。** 现有唯一生产分位仍是 PHASE-01 给定的 `first_content` P50=1396 / P95=3749，且与 `interactive` 几乎相等。那只能说明现网包仍在等关键路径 HTTP，不能指出是 `menu_api.server_ms`、`shop_info_api.server_ms` 还是 `network_approx_ms`。 |
| 3 | 下一刀该优化哪一类？ | **现在不能选 A/B/C/D 去实施。** 没有 `server_ms` vs `network_approx_ms` 分位，拆 `shop/info` 或砍 payload 都是猜测。保持：不拆接口、不重构菜单。 |

分类：A 后端接口 / B 网络 / C payload / D 前端渲染。

---

## 1. 本阶段实际读到了什么

| 来源 | 结果 |
|---|---|
| 生产 `perf_sample`（需要 ECS 登录或带 meta 的读接口） | **未读到行。** SSH `root@39.102.86.170` / `api.zhangbaiyang.com`：`Permission denied (publickey)`。本机只有 `id_ed25519_github`，不是服务器登录密钥。 |
| `GET /api/super/perf-stats` | 无 token 401。用本机 JWT 密钥签发的中控台 token 也被拒（生产密钥不同）。该接口即使登录也只有 `metric+ms` 分位，**仍然没有** `cache_hit` / `server_ms`。 |
| 本机 MySQL `example_db.perf_sample` | 0 行。 |
| 微信开发者工具 `WeappStorage` | 有 `perf_session_v1` / timeline，**没有** `perf_samples_menu_*` 数组（已上报或被刷掉）。不能当生产全集。 |
| PHASE-01 中控台给定分位 | 仍是目前唯一生产客户端数字，见下表。 |

PHASE-01 基线（未在本阶段刷新）：

| 指标 | P50 | P95 |
|---|---:|---:|
| `menu_onload_to_first_content` | 1396ms | 3749ms |
| `menu_onload_to_interactive` | 1392ms | 3729ms |

这两条差 4ms / 20ms，仍符合 PHASE-01「同一回调连打」。**不能当作 PHASE-02 已生效的证据。**

PHASE-02 是否已进微信正式包：本机无法从 `perf_sample.meta.definition` 判断。标记应为 `ordering_context_ready`（新）vs `category_and_dish_actions_available`（旧）。没读到 meta 就当 **正式包状态未知**。

---

## 2. 五个分析项：现有证据 vs 缺口

### 2.1 `cache_hit` × `first_content`

`cache_hit` 只写在 `menu_processing` 的 meta 里，不在 `first_content` 上。必须按 `meta.perf_session_id` join。

预期（代码，不是生产实测）：

- `cache_hit=true`：`first_content` 降到读缓存 + 一帧（约 100–300ms）
- `cache_hit=false`：`first_content` 贴近 `menu_api.client_ms`

**生产关联：未计算。**

注意：缓存命中但菜单请求抛错时，PHASE-02 仍会打 `first_content`，却不写 `menu_processing`。join 不上的会话应单列，不要并进无缓存。

### 2.2 `cache_hit` × `interactive`

`interactive` 在 PHASE-02 仍绑 `orderingContextReady`（两次关键路径成功，或店铺缓存兜底）。预期：

- 有缓存：`first_content` 快，`interactive` 仍约 `max(menu_api, shop_info_api)`，`first_content_to_interactive` > 0
- 无缓存：两条仍可能接近（菜单更慢时）

**生产关联：未计算。** 现网 1396≈1392 更像旧打点，不像「缓存已揭列表、加购仍等接口」。

### 2.3 `menu_api.server_ms`

sidecar 已写 `server_ms`（`X-Process-Time-Ms`）。中控台 `perf-stats` 用的是 **客户端** `ms`（≈ `client_ms`），不是 `server_ms`。

**生产 `server_ms` 分位：未读到。**

### 2.4 `shop_info_api.server_ms`

同样未读到。GET `/v1/shop/info` 上发券/预览/分销是结构嫌疑，不是已证实的现网慢因。

### 2.5 `network_approx_ms`

`max(client_ms - server_ms, 0)`。未读到分位。没有它就不能在 A 和 B 之间落刀，更不能宣称 C payload。

---

## 3. 为什么现在不能选下一刀

| 选项 | 现有生产证据 | 本阶段决定 |
|---|---|---|
| A 后端接口 | 无 `server_ms` P50/P95 | **不实施** |
| B 网络 | 无 `network_approx_ms`；P95/P50≈2.7 只是旧包的尾部形态 | **不实施** |
| C payload | 无体积、无「规格数 vs 耗时」相关 | **不实施、不拆字段** |
| D 前端渲染 | 1.4s 仍远超节点成本；编排优化未用量测签字 | **不重构菜单** |

仓库里的 PHASE-02 已经把「看见列表」从 `Promise.all` 上解开。那是代码事实，不是生产效果。在缓存会话的 `first_content` 分位出来之前，不要再改前端首屏编排，也不要动 `shop/info` 形状。

---

## 4. 解除阻塞（只读，在 ECS 上跑）

服务器：`root@iZ2ze1vb1w9yuqx7rdjwkpZ`（本机需能登录的密钥，不是 GitHub 公钥）。库名以 `/www/wwwroot/xiao/saas-base/.env` 的 `DATABASE_URL` 为准。不要改表、不要输出 `tenant_id` / `client_id`。

把下面脚本拷到服务器跑，把打印结果贴回本文件即可完成 PHASE-04。`meta` 是截到 500 字的 JSON，用 Python 解析，不要 `JSON_EXTRACT`。

```python
import json, statistics
from collections import defaultdict
from datetime import datetime, timedelta

# rows = [(metric, ms, meta_text, created_at), ...]  近 7 天
# 只读 SELECT metric, ms, meta, created_at FROM perf_sample
# WHERE created_at >= UTC_TIMESTAMP() - INTERVAL 7 DAY
# AND metric IN ('menu_onload_to_first_content','menu_onload_to_interactive',
#   'first_content_to_interactive','menu_api','shop_info_api','menu_processing')

def pct(xs, p):
    if not xs: return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, -(-p * len(xs) // 100) - 1))
    return xs[i]

def parse(meta):
    if not meta: return {}
    try: return json.loads(meta)
    except Exception: return {"_truncated": True}

# 然后：
# 1) 按 session 对齐 menu_processing.cache_hit 与 first_content / interactive
# 2) interactive.definition 计数：ordering_context_ready vs category_and_dish_actions_available
# 3) menu_api / shop_info_api 且 status==success：client_ms、server_ms、network_approx_ms 的 n/p50/p95
```

PHASE-02 已在正式包的最低证据：

- 至少若干条 `interactive.definition = ordering_context_ready`
- `cache_hit=true` 的 `first_content` P50 明显低于 1396ms（目标带 <400ms）
- 同批 `first_content_to_interactive` 中位数 > 0

有了第 3 项的 `server_ms` vs `network_approx_ms`，才能选 A 或 B。在那之前禁止拆接口。

---

## 5. 本阶段没做

- 没有改任何业务代码
- 没有拆 `shop/info`，没有从菜单 JSON 去掉 `spec_groups`
- 没有重构 DishList / menu.vue
- 没有在生产库上执行查询（无登录权限）

PHASE-04 在拿到 §4 的打印结果之前应视为 **未完成验证**，不是「PHASE-02 无效」。
