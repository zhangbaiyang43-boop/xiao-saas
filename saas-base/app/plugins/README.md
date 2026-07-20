# 插件开发规范

本目录是 SaaS 平台的扩展层。核心代码放在 `app/core`、`app/api`、`app/services`、`app/models`，可选业务能力放在 `app/plugins/<plugin_code>`。核心升级时不改插件目录，插件升级时不改核心底座。

## 标准结构

```text
app/plugins/
├── registry.json
├── base_plugin.py
├── plugin_manager.py
├── coupon/
│   ├── plugin.json
│   ├── plugin.py
│   ├── api/
│   ├── services/
│   ├── models/
│   ├── schemas/
│   └── assets/
├── crm/
├── bargain/
└── points/
```

## plugin.json

`plugin.json` 是插件元数据入口，插件管理器只扫描带有这个文件的目录。

```json
{
  "code": "points",
  "name": "积分体系",
  "version": "0.1.0",
  "description": "会员积分、积分流水和积分兑换扩展能力",
  "entry": "plugin.py",
  "category": "member",
  "enabled_by_default": false,
  "dependencies": [],
  "routes": [],
  "permissions": []
}
```

## 事件接入

核心业务只发布标准事件，不直接依赖插件。插件通过 `get_event_handlers()` 声明自己监听哪些事件。

当前标准事件：

```text
consumption.created
```

事件载荷：

```json
{
  "consumption_id": "123",
  "customer_id": 456,
  "project": "消费项目",
  "amount": 99.0,
  "consume_time": "2026-04-29T10:00:00",
  "remark": "备注"
}
```

插件示例：

```python
from app.core.events import CONSUMPTION_CREATED
from app.plugins.base_plugin import BasePlugin


class PointsPlugin(BasePlugin):
    plugin_code = "points"

    async def install(self, tenant_id: str):
        pass

    async def uninstall(self, tenant_id: str):
        pass

    async def on_consumption_created(self, event):
        # event.db 可复用当前请求数据库会话
        # event.tenant_id 是当前租户
        # event.payload 是标准事件载荷
        return {"handled": True}

    def get_event_handlers(self):
        return {
            CONSUMPTION_CREATED: self.on_consumption_created
        }
```

## 租户隔离要求

插件自己的业务表也必须继承统一 `BaseModel`，确保包含 `tenant_id`。所有查询、更新、删除都必须从 `TenantContext` 或服务基类中获取租户，并带 `tenant_id` 条件。
