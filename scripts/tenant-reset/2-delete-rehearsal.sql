-- 结尾 ROLLBACK：真删一遍看结果，然后整体回滚，库里不变。
-- FOREIGN_KEY_CHECKS=0：删的是一个完整自包含的商户子树，关掉 FK 检查
-- 免去删除顺序问题，也解决 orders.parent_order_id 的自引用外键。
SET @tid = 'PUT_TENANT_ID_HERE';
SET FOREIGN_KEY_CHECKS = 0;
START TRANSACTION;

DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE tenant_id = @tid);
DELETE FROM order_reviews                    WHERE tenant_id = @tid;
DELETE FROM orders                           WHERE tenant_id = @tid;
DELETE FROM dining_participants              WHERE tenant_id = @tid;
DELETE FROM dining_sessions                  WHERE tenant_id = @tid;
DELETE FROM pickup_no_assignments            WHERE tenant_id = @tid;
DELETE FROM staff_assisted_payment_handoffs  WHERE tenant_id = @tid;
DELETE FROM entrance_scan_log                WHERE tenant_id = @tid;
DELETE FROM channel_entry_visit_log          WHERE tenant_id = @tid;
DELETE FROM consumption                      WHERE tenant_id = @tid;
DELETE FROM point_ledger                     WHERE tenant_id = @tid;
DELETE FROM coupon                           WHERE tenant_id = @tid;
DELETE FROM member_account                   WHERE tenant_id = @tid;
DELETE FROM customer_identity                WHERE tenant_id = @tid;
DELETE FROM customer_operation_log           WHERE tenant_id = @tid;
DELETE FROM customer                         WHERE tenant_id = @tid;
DELETE FROM entrance_code                    WHERE tenant_id = @tid;
DELETE FROM channel_entry                    WHERE tenant_id = @tid;
DELETE FROM coupon_template                  WHERE tenant_id = @tid;
DELETE FROM benefit_template                 WHERE tenant_id = @tid;
DELETE FROM queue_tickets                    WHERE tenant_id = @tid;
DELETE FROM staff                            WHERE tenant_id = @tid;
DELETE FROM perf_sample                      WHERE tenant_id = @tid;
DELETE FROM wework_contact_way               WHERE tenant_id = @tid;
DELETE FROM wework_event_log                 WHERE tenant_id = @tid;
DELETE FROM commission_record                WHERE tenant_id = @tid;
DELETE FROM merchant_account_trusted_devices WHERE tenant_id = @tid;
DELETE FROM merchant_account_wechat_bindings WHERE tenant_id = @tid;
DELETE FROM merchant_accounts                WHERE tenant_id = @tid;

SET FOREIGN_KEY_CHECKS = 1;

SELECT 'menu_items 应=录入数' AS check_, COUNT(*) AS n FROM menu_items WHERE tenant_id = @tid
UNION ALL SELECT 'tenant_config 应=1',   COUNT(*) FROM tenant_config WHERE tenant_id = @tid
UNION ALL SELECT 'orders 应=0',          COUNT(*) FROM orders WHERE tenant_id = @tid
UNION ALL SELECT 'order_items 应=0',     COUNT(*) FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE tenant_id = @tid)
UNION ALL SELECT 'customer 应=0',        COUNT(*) FROM customer WHERE tenant_id = @tid
UNION ALL SELECT 'member_account 应=0',  COUNT(*) FROM member_account WHERE tenant_id = @tid
UNION ALL SELECT 'coupon 应=0',          COUNT(*) FROM coupon WHERE tenant_id = @tid
UNION ALL SELECT 'coupon_template 应=0', COUNT(*) FROM coupon_template WHERE tenant_id = @tid
UNION ALL SELECT 'entrance_code 应=0',   COUNT(*) FROM entrance_code WHERE tenant_id = @tid
UNION ALL SELECT 'queue_tickets 应=0',   COUNT(*) FROM queue_tickets WHERE tenant_id = @tid
UNION ALL SELECT 'perf_sample 应=0',     COUNT(*) FROM perf_sample WHERE tenant_id = @tid
UNION ALL SELECT 'merchant_accounts 应=0', COUNT(*) FROM merchant_accounts WHERE tenant_id = @tid;

ROLLBACK;
