# admin-h5 性能测试租户与数据集实施报告

## 1. 实施范围

本阶段仅建设 Source B 的测试基础设施，不修改业务能力或性能采集模型。

新增文件：

- `saas-base/scripts/admin_performance_dataset.py`：固定性能测试租户、确定性数据构造、`create / verify / cleanup` 生命周期、运行环境防护和清单输出。
- `saas-base/tests/test_admin_performance_dataset.py`：安全边界、确定性、规模、重复执行、回滚、隔离、清理及清单脱敏测试。
- `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04E_IMPLEMENTATION.md`：本实施记录。

未修改：

- `admin-h5` 与 `member-mini-client`；
- 业务 API、性能事件、数据库 schema、订单状态机、会员逻辑；
- migration、依赖清单与锁文件；
- 生产部署或生产数据。

固定身份合同：

| 字段 | 值 |
| --- | --- |
| dataset_version | `PERF_DATASET_V1` |
| tenant_id | `perf_test_only_v1` |
| tenant name | `[PERFORMANCE TEST ONLY] PERF_DATASET_V1` |
| staff username | `perf_operator` |
| source | `test` |

## 2. TDD 过程

### RED

第一轮测试先导入尚不存在的模块和生命周期 API，测试收集按预期失败：

```text
ModuleNotFoundError: No module named 'scripts.admin_performance_dataset'
```

生命周期阶段先增加 `create_dataset / verify_dataset / cleanup_dataset` 合同，因 `cleanup_dataset` 尚不存在而在导入阶段失败。CLI 阶段先增加解析器和清单合同，因 `build_cli_parser` 尚不存在而失败。

关系完整性阶段先破坏会员账户关联，验证测试按预期失败：

```text
Failed: DID NOT RAISE DatasetVerificationError
```

以上失败均发生在实现相应能力之前，没有通过删除或弱化断言消除。

### GREEN

最小实现依次加入：

1. 固定身份、环境/数据库/人工确认三重防护；
2. 不使用随机数和当前业务时间的确定性构造器；
3. marker 保护的创建、验证和清理事务；
4. CLI、原子 JSON manifest 和敏感字段隔离；
5. 会员关系与菜品规格映射验证。

阶段性结果：

```text
10 passed
14 passed
16 passed
18 passed
```

### VERIFY

默认规模独立生命周期测试执行了：创建、验证、重复创建、再次校验和清理。结果：

```text
1 passed in 39.70s
```

全量专项测试结果：

```text
18 passed, 2 warnings in 48.34s
```

两条 warning 来自项目已有的 Pydantic V2 class-config 与 SQLAlchemy `declarative_base()` 弃用提示，不是本阶段新增失败。

## 3. 数据集生命周期

### create

`create` 必须同时满足：

- `APP_ENV` 精确为 `test` 或 `staging`；
- 数据库名以 `_test` 或 `_staging` 结尾；
- `PERF_DATASET_ACK=PERF_DATASET_V1`；
- `PERF_TEST_PASSWORD` 非空；
- 数据库已有启用的 `PRO` 套餐；
- 固定 tenant_id 不存在，或已存在对象同时具有精确名称与 V1 测试 marker。

创建在单一外层事务中完成。若旧 V1 数据集存在，采用已批准的幂等方案 B：先在同一事务中清理旧数据，再确定性重建。插入或验证失败时整个事务回滚，旧的已提交数据集保持可用。

默认精确规模：

| 数据 | 数量 |
| --- | ---: |
| 菜品 | 500 |
| 菜品分类 | 20 |
| 会员 Customer | 10000 |
| 会员 MemberAccount | 10000 |
| 订单 | 10000 |
| 订单明细 | 30000 |

生成内容由序号和固定时间锚点推导。数据库主键仍使用项目已有雪花 ID，因此物理 ID 可以变化；语义内容、规模、分布与 SHA-256 checksum 保持一致。

### verify

`verify` 为只读操作，检查：

- 固定租户名称和测试 marker；
- 数据集版本、规模与语义 checksum；
- 菜品、会员、会员账户、订单和订单明细精确数量；
- 分类、订单状态和会员等级覆盖；
- 会员账户不存在孤立关联；
- 菜品规格映射数量及所属租户正确；
- 打印状态全部为 `SUCCESS`；
- 专用登录账户和有效测试订阅存在。

任一检查失败均返回 `FAIL`，不会把部分数据标记为可用数据集。

### cleanup

`cleanup` 再次验证固定名称和 marker，只按 `perf_test_only_v1` 删除：订单明细、订单、会员账户、会员、菜品、登录账户、订阅、租户配置和租户。全局套餐与其他租户不在删除范围内。

CLI 入口：

```text
py -3.10 scripts/admin_performance_dataset.py create --dataset-version PERF_DATASET_V1 --manifest-out ../outputs/performance/PERF_DATASET_V1.json
py -3.10 scripts/admin_performance_dataset.py verify --dataset-version PERF_DATASET_V1 --manifest-out ../outputs/performance/PERF_DATASET_V1.json
py -3.10 scripts/admin_performance_dataset.py cleanup --dataset-version PERF_DATASET_V1
```

## 4. 数据隔离证明

隔离测试数据库预置一个 `production-control` 控制租户及其菜品。完整创建、重复创建和清理后，断言：

| 对象 | 操作前 | cleanup 后 | 结论 |
| --- | ---: | ---: | --- |
| `production-control` 租户 | 1 | 1 | 未改变 |
| `production-control` 菜品 | 1 | 1 | 未改变 |
| `perf_test_only_v1` 租户 | 0 | 0 | 已清理 |

另有反向保护测试：若固定 tenant_id 已被一个没有精确测试 marker 的现有租户占用，`create` 和 `cleanup` 都必须拒绝执行，不能收编或删除该租户。

本证明来自独立 SQLite 测试数据库。工具没有连接或修改生产数据库，不能将此结果描述为真实生产数据检查。

## 5. 测试结果

| 测试范围 | 数量 | 通过 | 失败 |
| --- | ---: | ---: | ---: |
| Phase-04E 专项测试 | 18 | 18 | 0 |
| 默认 500/10000/10000 生命周期 | 1 | 1 | 0 |
| 相关性能/菜单/账户/员工安全回归 | 37 | 37 | 0 |

专项测试覆盖：

1. create；
2. verify；
3. cleanup；
4. 默认规模合同；
5. 重复执行与语义 checksum；
6. 跨租户隔离；
7. 强制异常后的事务恢复；
8. 数据破坏检测；
9. CLI、原子 manifest 与敏感字段排除；
10. 非 test/staging 环境、错误数据库后缀和错误确认值的 fail-closed 行为。

相关性能、菜单、租户账户及员工安全门禁回归结果：

```text
37 passed, 12 warnings in 108.67s
```

回归 warning 均为项目已有的 Pydantic、SQLAlchemy 与 FastAPI 弃用提示，没有测试失败。

## 6. 风险说明

- 本工具是数据库测试基础设施，不是业务 API，不会被 admin-h5 自动调用。
- 没有使用 `random`；同版本数据可重现。
- 没有建立新表、修改字段或创建 migration。
- 没有网络上报、第三方监控或新的性能事件。
- manifest 只包含聚合规模、环境、版本、时间和 checksum，不包含密码、密码哈希、token、cookie、连接串、请求体、响应体或商家数据。
- 图片字段当前使用固定测试 URL 模式，但没有部署受控图片资源；图片资源性能仍不能验证。
- 当前测试运行于独立 SQLite 内存数据库，不构成 MySQL 兼容性或真实 staging 运行证明。
- 尚未登录 staging 的四个页面读取 Phase-03C 事件，因此尚未证明 Source B 页面/API 性能事件链路。

## 7. 下一阶段

验收问题：

| 问题 | 当前回答 |
| --- | --- |
| 是否存在独立性能测试租户？ | 已实现固定独立租户能力，并在隔离测试数据库验证；真实 staging 尚未创建。 |
| 是否可以生成 500+ 菜品？ | 是，精确生成并验证 500 条。 |
| 是否可以生成 10000+ 会员？ | 是，精确生成并验证 10000 Customer + 10000 MemberAccount。 |
| 是否可以生成 10000+ 订单？ | 是，精确生成并验证 10000 订单 + 30000 明细。 |
| 是否可以重复执行？ | 是，采用同事务清理后重建，语义 checksum 保持一致。 |
| 是否可以安全清理？ | 是，固定 marker 防护且控制租户保持不变。 |
| 是否与生产隔离？ | 工具强制 test/staging 环境与数据库后缀；本阶段未触达生产。 |
| 是否可以产生性能事件？ | 尚未证明；必须在真实 staging 登录四个页面验证 Phase-03C 事件。 |

最终决定：

```text
RESULT B
Local/test dataset infrastructure complete.
Real staging tenant, MySQL runtime proof and admin-h5 event proof remain pending.
Continue Phase-04E; do not enter Phase-04F.
```

下一步不是性能优化。应先在专用 MySQL staging 数据库使用同一脚本完成 `create → verify`，再访问 Dashboard、OrderManage、DishManage、MemberManage，确认现有页面事件和 API 事件的 `environment=staging`、目标 version 与 `source=test` 外部清单隔离成立。全部通过后，才允许进入 Phase-04F 双数据源采样。
