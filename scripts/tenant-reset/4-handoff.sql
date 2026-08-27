-- 交接：把商户从"你"改成"客户"。上面 3-delete-commit 成功后再跑。
-- ⚠ 先只看不执行。里面 4c 需要你手工填客户手机号。
SET @tid = 'PUT_TENANT_ID_HERE';

-- 4a. 清微信支付商户号（不清 = 客户的营业款进你的账户）。
--     本次 0MBBU 的 wx_mchid 本来就是 NULL，这段是 NULL->NULL 的空操作，跑不跑都行；
--     换商户如果 wx_mchid 有值，这段必须跑。
UPDATE tenant SET
    wx_pay_enabled    = 0,
    wx_mchid          = NULL,
    wx_api_key_v3     = NULL,
    wx_cert_serial    = NULL,
    wx_private_key    = NULL,
    wx_public_key_id  = NULL,
    wx_public_key     = NULL,
    receiver_name     = NULL,
    receiver_type     = NULL,
    receiver_verified = 0,
    payment_locked    = 1,
    verified_time     = NULL
  WHERE tenant_id = @tid;

-- 4b. 清飞鹅云打印机（客户绑自己的）
UPDATE tenant SET feieyun_sn = NULL, feieyun_key = NULL WHERE tenant_id = @tid;

-- 4c. 换登录手机号。老板端 = 手机号 + 短信验证码 登录，phone 有唯一索引。
--     ★ 先查客户手机号有没有被别的商户占用，占用了 UPDATE 会直接失败：
--         SELECT tenant_id, name FROM tenant WHERE phone = '客户手机号';
--     没占用再执行（把号填进去、去掉行首的两个减号）：
-- UPDATE tenant SET phone = '客户手机号' WHERE tenant_id = @tid;

-- 4d. password_hash 不要在 SQL 里改。老板端走短信验证码，换完手机号客户就能登。
--     确需重置密码时用后台的重置流程。
