# admin-h5 Phase-04F Staging 环境就绪报告

本报告记录 Source B（受控 staging/test tenant）性能采样环境的就绪证据。它只确认环境、数据集、访问链路与既有性能事件能够工作，不进行性能归因，不形成 P50/P95 结论，也不授权性能优化。

## 1. Environment status

| 项目 | 实际值 | 状态 |
| --- | --- | --- |
| 环境 | `staging` | PASS |
| admin-h5 | `http://127.0.0.1:18989` | PASS |
| Backend health | `http://127.0.0.1:19898/health`，HTTP 200，`healthy` | PASS |
| admin-h5 版本 | `823708c1cbac8ba7c730715afafbecd27d641f09` | PASS |
| 构建器 | `local-docker-performance-staging` | PASS |
| Compose 项目 | 本机 Docker、loopback-only | PASS |

运行时 `release` 信息中的 SHA、environment 和 builder 均与上表一致。容器在验证时均处于 healthy/running 状态；主机仅发布 `127.0.0.1:18989` 和 `127.0.0.1:19898`，MySQL 与 Redis 未发布主机端口，仅在 staging Compose 私有网络中可达。

本次运行记录到的镜像身份如下：

| 服务 | 运行时 image id（缩写） |
| --- | --- |
| MySQL | `sha256:7dcddc...` |
| Redis | `sha256:c9d92...` |
| Admin | `sha256:8ad4...` |
| Backend | `sha256:e8cb...` |
| Migrate | `sha256:182afe...` |

这些身份用于记录本次执行事实。当前基础镜像标签尚未使用 digest 固定，因此不能保证未来重建获得完全相同的基础镜像；这是严格可复现性的已知限制，不影响本次环境就绪结论。

## 2. Performance Tenant

| 项目 | 值 |
| --- | --- |
| tenant_id | `perf_test_only_v1` |
| 用途 | `performance_test_only` |
| dataset_version | `PERF_DATASET_V1` |
| 数据来源标记 | `source=test` |
| Owner 登录手机号 | `199****0000` |

租户是 staging 中的独立性能测试租户。Owner 登录通过现有 UI 和现有登录接口完成，一次性验证码由 staging-only Redis helper 写入；没有发送短信、没有注入 JWT、没有绕过鉴权，也没有新增认证接口。

## 3. Dataset execution table

真实 Docker/MySQL 生命周期已按以下顺序执行并通过：

`create -> verify -> cleanup -> create -> verify`

首次与最终生成的数据集 checksum 完全一致：

`5319392b275d337671ef1334c2976daf616d25526bb8548ed2342a29236d5a9f`

| 数据 | 目标 | 最终实际 | cleanup 删除 | 状态 |
| --- | ---: | ---: | ---: | --- |
| 菜品 | 500+ | 500 | 500 | PASS |
| 会员 / customers | 10000+ | 10000 | 10000 | PASS |
| 会员账户 / member_accounts | 与会员一致 | 10000 | 10000 | PASS |
| 订单 | 10000+ | 10000 | 10000 | PASS |
| 订单明细 / order_items | 多明细 | 30000 | 30000 | PASS |
| 分类 | 有分类分布 | 20 | 20 | PASS |
| 菜品规格 | 有 SKU/规格关系 | 125 | 125 | PASS |
| 非法打印记录 | 0 | 0 | 0 | PASS |
| 孤立会员账户 | 0 | 0 | 0 | PASS |

cleanup 删除数量与被创建的数据数量一致。四页浏览完成后再次执行 `verify`，结果仍为 PASS，证明本轮只读页面验证没有破坏数据集合同。

## 4. Admin access validation (page events + API events)

admin-h5 已使用 Performance Tenant 登录并只读访问以下页面：

- Dashboard
- OrderManage
- DishManage
- MemberManage

从既有 `window.__ADMIN_PERF_EVENTS__` 只读出口取得 41 条事件，41 条有效、0 条无效；时间范围为 `2026-08-24T17:13:11.783Z` 至约 `2026-08-24T17:16:26Z`。所有事件均满足：

- `environment=staging`
- `version=823708c1cbac8ba7c730715afafbecd27d641f09`
- timestamp、event_name 有效

### 页面事件

| 页面 | page_enter | first_content_visible | page_ready | 观测 duration（ms） |
| --- | ---: | ---: | ---: | --- |
| Dashboard | 1 | 1 | 1 | 31.4 / 3367.2 / 3367.2 |
| OrderManage | 1 | 1 | 1 | 32 / 3970 / 3970 |
| DishManage | 1 | 1 | 1 | 13.8 / 3111.3 / 3111.3 |
| MemberManage | 2 | 2 | 2 | enter: 133.2、0.6；first/ready: 657.7、1286.5 |

上述数据只证明四个页面能够产生完整事件。样本量不足以计算可靠 P50/P95，也不得据此判断页面快慢或归因瓶颈。

### API 事件

| API 组 | start/end | duration（ms） | 状态 |
| --- | --- | --- | --- |
| marketing | 1 / 1 | 650.3 | success |
| members | 2 / 2 | 345.8、1000.9 | success |
| menu | 1 / 1 | 395.1 | success |
| orders | 9 / 9 | 2660.4、3076.8、34.2、2798.3、38.8、3699.7、3116.1、2863.1、2764.6 | success |

API 事件检查结果：0 个未配对事件、0 个负 duration、0 个非法 end status。这里同样只确认事件采集链路存在且结构有效，不对 API 或网络性能作结论。

数据集中的图片 URL 为确定性占位地址 `https://perf-assets.invalid/...`。Chrome 出现多条 `ERR_CONNECTION_CLOSED`，因此本阶段只验证了图片字段存在，**没有验证真实图片资源加载或图片性能**；这些占位地址错误不得归因于前端、网络或生产资源服务。它不阻塞页面/API staging 采样入口，但后续任何图片性能分析都必须使用独立、可访问且来源明确的测试资源。

## 5. Isolation proof

| 隔离项 | 证据 | 状态 |
| --- | --- | --- |
| 网络边界 | 仅两个 loopback 端口；MySQL/Redis 私网 | PASS |
| 租户边界 | 固定 `perf_test_only_v1`，purpose 与 marker 双重限制 | PASS |
| 环境边界 | 所有事件为 `staging` | PASS |
| 版本边界 | 所有事件为冻结 admin SHA | PASS |
| 数据来源 | `PERF_DATASET_V1` / `source=test` | PASS |
| 清理边界 | cleanup 仅删除性能租户数据且数量可核对 | PASS |
| 前端边界 | `git diff 823708c1cbac8ba7c730715afafbecd27d641f09 -- admin-h5` 无差异 | PASS |
| 生产边界 | 未连接生产数据库；`PRODUCTION_COUNTS=NOT_QUERIED` | PASS |

边界审计确认没有修改 admin-h5 业务代码、业务 API、model、数据库 schema、migration、CI workflow、依赖或生产部署流程。`.env.local` 被忽略且未跟踪；测试中出现的 `user:secret` 是合成测试字面量，不是实际提交的凭据。

Source A（production）与 Source B（本报告的 staging）必须独立统计，严禁混合计算 P50、P95 或错误率。本阶段仅建立 Source B，不补足生产样本，也不满足 Phase-05 性能归因或性能优化的进入条件。

浏览器证据仅来自一台本地设备上的一次 Chrome 会话，只能证明该受控本地访问链路可产生事件；它不证明跨设备、跨浏览器或外部网络环境行为。

### 验证命令与结果

本阶段使用既有 lifecycle 脚本执行 Prepare/Start/Verify/Cleanup 等动作，并通过 Docker Compose、HTTP health、release metadata、数据集 verify 及浏览器只读事件出口完成验证。相关自动化测试结果：

```powershell
powershell -NoProfile -File scripts/performance-staging.ps1 -Action Prepare
powershell -NoProfile -File scripts/performance-staging.ps1 -Action Start
powershell -NoProfile -File scripts/performance-staging.ps1 -Action Verify
powershell -NoProfile -File scripts/performance-staging.ps1 -Action Cleanup
powershell -NoProfile -File scripts/performance-staging.ps1 -Action Start
powershell -NoProfile -File scripts/performance-staging.ps1 -Action Verify
Push-Location saas-base
$env:JWT_SECRET_KEY = 'phase04f-test-only-secret-32-bytes-minimum'
py -3.10 -m pytest tests/test_performance_staging_environment_contracts.py -q

# lifecycle 相关组合测试（69 个测试；包含上述 24 个 environment contracts）
py -3.10 -m pytest -p no:cacheprovider `
  tests/test_admin_performance_dataset.py `
  tests/test_admin_performance_owner_code.py `
  tests/test_performance_staging_environment_contracts.py -q

# 最终相关 regression（106 个测试；包含上述 69 个测试）
py -3.10 -m pytest -p no:cacheprovider `
  tests/test_admin_performance_dataset.py `
  tests/test_admin_performance_owner_code.py `
  tests/test_performance_staging_environment_contracts.py `
  tests/test_performance_contracts.py `
  tests/test_menu_performance_contracts.py `
  tests/test_tenant_account_contracts.py `
  tests/test_merchant_staff_security_gate.py -q
Pop-Location
```

命令输出中的密码、验证码等敏感值不进入本报告；浏览器事件通过既有只读内存快照导出，没有新增网络上报。

- staging environment contracts：24 passed
- lifecycle 相关组合测试：69 passed（包含上述 24 个测试），2 条既有 deprecation warnings，50.35s
- 最终相关 regression：106 passed（包含上述 69 个测试），12 条既有 deprecation warnings，150.36s
- 浏览器读取事件后 dataset verify：PASS

警告均为既有弃用警告，没有新增失败。具体设计与实现背景见：

- `docs/superpowers/specs/2026-08-24-admin-performance-staging-ready-design.md`
- `docs/superpowers/plans/2026-08-24-admin-performance-staging-ready.md`
- `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04E_IMPLEMENTATION.md`

## 6. Phase-04F entry judgment

**READY：YES**

**RESULT A：性能测试 staging 与 Source B 采样入口已就绪，可以进入 `P0-ADMIN-PERFORMANCE-OBSERVABILITY-PHASE-04F` 双数据源采样。**

判断依据是环境、租户、数据集 lifecycle、四页面访问、页面事件、API 事件和隔离边界均已获得实际执行证据。此结论不是“性能良好”，也不是允许进入优化阶段。

进入 Phase-05 性能归因前，仍必须单独满足既定的 production 样本门槛；不得以本报告的 staging 数据替代真实生产用户体验数据。没有独立且充分的生产样本前，MUST NOT 修改代码进行性能优化。

### Acceptance 回答

1. 是否存在独立 staging 环境？**是**，本机 Docker 环境且仅 loopback 可访问。
2. 是否存在 performance tenant？**是**，`perf_test_only_v1`。
3. 是否生成 500+ 菜品？**是**，实际 500。
4. 是否生成 10000+ 会员？**是**，customers 与 member_accounts 均为 10000。
5. 是否生成 10000+ 订单？**是**，订单 10000、订单明细 30000。
6. admin-h5 是否可以访问？**是**，Owner UI 登录及四个目标页面只读访问均通过。
7. 性能事件是否产生？**是**，41/41 有效，页面与 API 事件均存在且版本/环境正确。
8. 是否可以进入 Phase-04F 双源采样？**是**；但 Source A/Source B 必须严格隔离，且不代表可以进入 Phase-05 或优化。
