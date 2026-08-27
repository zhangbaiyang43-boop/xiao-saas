-- 预演：只数数，不改任何东西。
-- 期望：menu_items = 商户实际菜品数；tenant_config = 1；其余数字不离谱。
SET @tid = 'PUT_TENANT_ID_HERE';

SELECT '=== 保留（menu_items 必须 > 0）===' AS section;
SELECT 'menu_items' AS t, COUNT(*) AS n FROM menu_items WHERE tenant_id = @tid
UNION ALL SELECT 'tenant_config', COUNT(*) FROM tenant_config WHERE tenant_id = @tid;

SELECT '=== 将被清空 ===' AS section;
SELECT 'order_items' AS t, COUNT(*) AS n FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE tenant_id = @tid)
UNION ALL SELECT 'order_reviews',                    COUNT(*) FROM order_reviews                    WHERE tenant_id = @tid
UNION ALL SELECT 'orders',                           COUNT(*) FROM orders                           WHERE tenant_id = @tid
UNION ALL SELECT 'dining_participants',              COUNT(*) FROM dining_participants              WHERE tenant_id = @tid
UNION ALL SELECT 'dining_sessions',                  COUNT(*) FROM dining_sessions                  WHERE tenant_id = @tid
UNION ALL SELECT 'pickup_no_assignments',            COUNT(*) FROM pickup_no_assignments            WHERE tenant_id = @tid
UNION ALL SELECT 'staff_assisted_payment_handoffs',  COUNT(*) FROM staff_assisted_payment_handoffs  WHERE tenant_id = @tid
UNION ALL SELECT 'entrance_scan_log',                COUNT(*) FROM entrance_scan_log                WHERE tenant_id = @tid
UNION ALL SELECT 'channel_entry_visit_log',          COUNT(*) FROM channel_entry_visit_log          WHERE tenant_id = @tid
UNION ALL SELECT 'consumption',                      COUNT(*) FROM consumption                      WHERE tenant_id = @tid
UNION ALL SELECT 'point_ledger',                     COUNT(*) FROM point_ledger                     WHERE tenant_id = @tid
UNION ALL SELECT 'coupon',                           COUNT(*) FROM coupon                           WHERE tenant_id = @tid
UNION ALL SELECT 'member_account',                   COUNT(*) FROM member_account                   WHERE tenant_id = @tid
UNION ALL SELECT 'customer_identity',                COUNT(*) FROM customer_identity                WHERE tenant_id = @tid
UNION ALL SELECT 'customer_operation_log',           COUNT(*) FROM customer_operation_log           WHERE tenant_id = @tid
UNION ALL SELECT 'customer',                         COUNT(*) FROM customer                         WHERE tenant_id = @tid
UNION ALL SELECT 'entrance_code',                    COUNT(*) FROM entrance_code                    WHERE tenant_id = @tid
UNION ALL SELECT 'channel_entry',                    COUNT(*) FROM channel_entry                    WHERE tenant_id = @tid
UNION ALL SELECT 'coupon_template',                  COUNT(*) FROM coupon_template                  WHERE tenant_id = @tid
UNION ALL SELECT 'benefit_template',                 COUNT(*) FROM benefit_template                 WHERE tenant_id = @tid
UNION ALL SELECT 'queue_tickets',                    COUNT(*) FROM queue_tickets                    WHERE tenant_id = @tid
UNION ALL SELECT 'staff',                            COUNT(*) FROM staff                            WHERE tenant_id = @tid
UNION ALL SELECT 'perf_sample',                      COUNT(*) FROM perf_sample                      WHERE tenant_id = @tid
UNION ALL SELECT 'wework_contact_way',               COUNT(*) FROM wework_contact_way               WHERE tenant_id = @tid
UNION ALL SELECT 'wework_event_log',                 COUNT(*) FROM wework_event_log                 WHERE tenant_id = @tid
UNION ALL SELECT 'commission_record',                COUNT(*) FROM commission_record                WHERE tenant_id = @tid
UNION ALL SELECT 'merchant_account_trusted_devices', COUNT(*) FROM merchant_account_trusted_devices WHERE tenant_id = @tid
UNION ALL SELECT 'merchant_account_wechat_bindings', COUNT(*) FROM merchant_account_wechat_bindings WHERE tenant_id = @tid
UNION ALL SELECT 'merchant_accounts',                COUNT(*) FROM merchant_accounts                WHERE tenant_id = @tid;

SELECT tenant_id, name, phone, payment_mode, wx_pay_enabled, wx_mchid, receiver_name, feieyun_sn
  FROM tenant WHERE tenant_id = @tid;
