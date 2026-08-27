# 清空一个商户的经营数据，保留菜品

场景：用自己的号在后台给客户录了菜品，现在要保留菜品、清掉其余所有数据，
把商户交给客户。

## 为什么只能原地清、不能"新建商户搬菜品"

菜品「规格」不在 menu_items 表里，而在 tenant_config.business_info.menu_item_specs，
**key 是菜品 id**。换商户 = 菜品 id 变 = 规格全丢。所以必须原地清、保留
menu_items + tenant_config。

## 保留

- menu_items      菜品本体（名称/价格/图片/标签/库存/划线价/排序）
- tenant_config   ★ 菜品规格在这里，必须留
- tenant          商户本身（4-handoff.sql 会改手机号等字段）
- tenant_plugin / subscriptions / plans / billing_*   平台侧订阅账单

## 执行顺序（生产库，一步都不能跳）

```bash
TID=真实的32位tenant_id
cd /www/wwwroot/xiao

# 0. 备份 + 验证（末行必须是 "-- Dump completed"，menu_items INSERT 数 >= 1）
mysqldump --no-tablespaces --single-transaction --routines --triggers saas_base > /root/backup-$(date +%Y%m%d-%H%M).sql
tail -n 2 /root/backup-*.sql

# 1. 预演：只数数，确认 menu_items 数对、其余数字不离谱
sed "s/PUT_TENANT_ID_HERE/$TID/g" scripts/tenant-reset/1-dryrun.sql | mysql saas_base

# 2. 删除预演：真删一遍再 ROLLBACK，确认没有外键报错、SELECT 结果全对
sed "s/PUT_TENANT_ID_HERE/$TID/g" scripts/tenant-reset/2-delete-rehearsal.sql | mysql saas_base ; echo "exit=$?"

# 3. 正式删除：跟 2 一样但结尾 COMMIT
sed "s/PUT_TENANT_ID_HERE/$TID/g" scripts/tenant-reset/3-delete-commit.sql | mysql saas_base ; echo "exit=$?"

# 4. 交接：改 tenant 表（手机号 / 微信支付 / 打印机）。先看清里面的注释再跑
sed "s/PUT_TENANT_ID_HERE/$TID/g" scripts/tenant-reset/4-handoff.sql
#   确认无误后再执行

# 收尾
rm -f /root/.my.cnf   # 如果这次为了免密建过
```

## 外键注意

库里没有任何 ON DELETE CASCADE。2/3 号脚本用 SET FOREIGN_KEY_CHECKS=0 包住
整个事务，因为删的是一个完整的、自包含的商户子树（1-dryrun 已枚举全部相关表），
不存在删完还有别的表指进来的孤儿行。orders 有自引用外键 parent_order_id，
关掉 FK 检查同时也解决了它。
