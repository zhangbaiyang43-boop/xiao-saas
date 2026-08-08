# 员工「小程序微信身份 + 可信设备」（退出主链，代码保留）

> **Phase 1 产品主路径已切回商家 H5 密码登录**（门店手机号 + 员工账号 + 密码 → Waiter/Kitchen）。
> 本文档描述的小程序 / handoff 链为历史实现，默认关闭，后续物理清理前勿当正式入口。

## 硬规则

【Role/Permission永远来自 merchant_account 数据库。】

【Authentication Provider 可以替换，但 Authorization 不允许跟着重写。】

## 历史链路（已非产品主路径）

老板生成小程序码 → 员工扫码绑定（wx.login → code2session）→ 一次性 Handoff → H5 `/staff-handoff#t=` → HttpOnly `staff_device` + 短 JWT → Waiter/Kitchen 工作台。

## Feature flags

- `STAFF_MINIPROGRAM_AUTH_ENABLED=false`（默认关闭；生产也应为 false）
- `STAFF_OFFICIAL_ACCOUNT_OAUTH_ENABLED=false`（旧公众号 OAuth，代码保留，默认关闭）

## 复用

- `WechatService.code2session` / `get_access_token` / `get_wxacode_unlimit`
- 表：`merchant_account_wechat_bindings`、`merchant_account_trusted_devices`（migration `20260808_0004`，无新 migration）

## TEMP_STAFF_SCAN_TEST

临时：开发版内「我的 → 扫一扫」扫普通码 `KXD_STAFF_BIND_V1:<scene>`，与正式小程序码共用同一 scene。

正式上线后 SEARCH `TEMP_STAFF_SCAN_TEST` 删除入口 / helper / 测试二维码 / `test_scan_payload`。

**不要删除**：`staff-bind`、`wx.login`、`code2session`、handoff、trusted device。
