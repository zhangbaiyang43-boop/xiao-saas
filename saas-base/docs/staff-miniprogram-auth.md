# 员工「小程序微信身份 + 可信设备」

## 硬规则

【微信只负责证明“你是谁”，Role/Permission永远来自 merchant_account 数据库。】

【员工微信身份统一由开心点单小程序提供，不依赖公众号网页 OAuth。】

【小程序身份和 H5 工作台通过短时、单次 Handoff 连接，不共享长期微信凭证。】

【长期可信凭证只存在 HttpOnly Cookie，openid、wx.login code、session_key 都不能成为 H5 权限凭证。】

【Authentication Provider 可以替换，但 Authorization 不允许跟着重写。】

## 主链路

老板生成小程序码 → 员工扫码绑定（wx.login → code2session）→ 一次性 Handoff → H5 `/staff-handoff#t=` → HttpOnly `staff_device` + 短 JWT → Waiter/Kitchen 工作台。

日常：小程序「员工工作台」→ wx.login → handoff → H5。

备用：admin-h5 账号密码登录。

## Feature flags

- `STAFF_MINIPROGRAM_AUTH_ENABLED=true`（主）
- `STAFF_OFFICIAL_ACCOUNT_OAUTH_ENABLED=false`（旧公众号 OAuth，代码保留，默认关闭）
- `STAFF_MINIPROGRAM_TEST_SCAN_ENABLED=false`（TEMP：开发版普通测试码 transport，默认关）

## 复用

- `WechatService.code2session` / `get_access_token` / `get_wxacode_unlimit`
- 表：`merchant_account_wechat_bindings`、`merchant_account_trusted_devices`（migration `20260808_0004`，无新 migration）

## TEMP Staff Bind Test Scanner

【测试入口只绕过“小程序如何获得 scene”，绝不能绕过员工真实微信身份认证。】

【扫一扫测试和正式小程序码必须共用同一个 bind scene、同一个 preview、同一个 wx.login、同一个 code2session、同一个 handoff。】

【release 小程序永远不展示测试扫一扫，即使服务器配置错误。】

正式上线后删除（SEARCH `TEMP_STAFF_BIND_TEST_SCAN`）：

1. 服务与设置「扫一扫测试」入口（`mine.vue`）
2. `utils/staffBindTestScanner.js` 及 `__tests__/staffBindTestScanner.test.js`
3. StaffManage 开发版测试二维码 UI
4. API `test_scan_payload` / `test_scan_enabled`
5. `STAFF_MINIPROGRAM_TEST_SCAN_ENABLED` 配置
6. 相关 TEMP 测试断言

**不要删除**：`staff-bind`、`wx.login`、`code2session`、handoff、trusted device。
