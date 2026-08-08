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

## 复用

- `WechatService.code2session` / `get_access_token` / `get_wxacode_unlimit`
- 表：`merchant_account_wechat_bindings`、`merchant_account_trusted_devices`（migration `20260808_0004`，无新 migration）

## TEMP_STAFF_SCAN_TEST

临时：开发版内「我的 → 扫一扫」扫普通码 `KXD_STAFF_BIND_V1:<scene>`，与正式小程序码共用同一 scene。

正式上线后 SEARCH `TEMP_STAFF_SCAN_TEST` 删除入口 / helper / 测试二维码 / `test_scan_payload`。

**不要删除**：`staff-bind`、`wx.login`、`code2session`、handoff、trusted device。
