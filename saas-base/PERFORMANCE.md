# 数据与性能约定

## 响应耗时口径

平台的 `<100ms` 目标先按**后端服务端处理耗时**统计：

- 起点：请求进入 FastAPI `LoggingMiddleware`。
- 终点：接口响应对象返回给 ASGI 层。
- 包含：鉴权、中间件、数据库查询、缓存读写、业务处理、序列化。
- 不包含：浏览器到本机的网络耗时、小程序真实公网链路、CDN、运营商网络。

每个响应会带：

```text
X-Process-Time-Ms: 12.34
```

当服务端处理耗时超过 `SLOW_REQUEST_MS`，日志级别会从 `INFO` 提升为 `WARNING`。

## 默认性能参数

配置来源：`.env` 或 `app/config.py`。

```text
SLOW_REQUEST_MS=100
PAGE_DEFAULT_LIMIT=20
PAGE_MAX_LIMIT=200
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=50
DB_POOL_RECYCLE=1800
CACHE_DEFAULT_TTL=1800
```

## 分页约定

所有列表接口必须支持：

```text
skip=0
limit=20
```

并统一经过 `app.core.pagination.normalize_pagination()`，避免一次拉取过多数据。

## 索引约定

所有业务表必须继承 `BaseModel`，天然具备 `tenant_id` 单列索引。常用组合索引按查询模式补充：

- `tenant_id + customer_id`
- `tenant_id + status`
- `tenant_id + created_at`
- `tenant_id + phone`
- `tenant_id + channel + channel_user_id`

## 统计缓存

统计接口优先使用 Redis 缓存。Redis 不可用时降级为实时查询，并写 WARNING 日志，不影响主流程。

当前统计入口：

```text
GET /api/v1/stats/dashboard
```

缓存时间：60 秒。

## 后续监控

后续可以基于日志中的 `method`、`path`、`status_code`、`cost_ms` 做接口维度 P50/P95/P99 统计，再判断是否达到平均响应 `<100ms`。
