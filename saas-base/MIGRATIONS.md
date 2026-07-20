# 数据库迁移规范

## 原则

- 正式环境只允许通过 Alembic 迁移数据库结构。
- 运行后端时默认不再自动 `create_all` 建表。
- `AUTO_CREATE_TABLES=false` 是默认值；只有临时本地实验库才允许改成 `true`。
- 每次新增模型、字段、索引、约束，都必须生成一个新的 Alembic revision。

## 新数据库初始化

先确认 `.env` 里的 `DATABASE_URL` 指向目标库，然后执行：

```powershell
cd C:\Users\15936\Desktop\xiao\saas-base
.\scripts\db-upgrade.ps1
```

等价命令：

```powershell
python -m alembic upgrade head
```

## 已有老数据库接入 Alembic

如果数据库之前已经通过 `Base.metadata.create_all` 或手动 SQL 建好了表，并且结构与当前模型一致，先执行：

```powershell
cd C:\Users\15936\Desktop\xiao\saas-base
.\scripts\db-stamp-existing.ps1
```

这一步只写入 Alembic 版本号，不创建表。之后再有新结构变更，统一用 `db-upgrade.ps1`。

## 查看当前版本

```powershell
.\scripts\db-current.ps1
```

## 新增迁移

修改 SQLAlchemy 模型后，执行：

```powershell
.\scripts\db-revision.ps1 "add customer identity indexes"
```

生成文件后必须人工检查：

- 表名、字段名是否符合现有约定。
- 所有业务表是否包含 `tenant_id`。
- 常用查询是否有组合索引。
- `downgrade()` 是否可回滚。

确认无误后执行：

```powershell
.\scripts\db-upgrade.ps1
```

## 当前基线

首个基线迁移：

```text
alembic/versions/20260429_0001_initial_core_schema.py
```

包含核心商家后台 MVP 表：

- `tenant`
- `tenant_config`
- `tenant_plugin`
- `customer`
- `customer_identity`
- `consumption`
- `coupon_template`
- `coupon`
