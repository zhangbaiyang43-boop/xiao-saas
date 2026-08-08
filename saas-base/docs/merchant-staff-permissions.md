# 商家员工权限（V1）

【权限决定“能不能做”，岗位工作台决定“现在该做什么”。】

【前端隐藏不是安全，后端 Permission 才是安全边界。】

【员工默认无权限，只开放岗位履约真正需要的能力。】

- Role 固定：`owner` / `frontdesk` / `waiter` / `kitchen`
- Permission 原子化，写在 `app/core/permissions.py`
- 业务 API 使用 `require_permission(...)`，禁止散落 `if role == "waiter"`
- 老板账号 = 现有 `Tenant` 短信登录，自动视为 `owner`
- 员工账号 = `merchant_accounts` 表（店内唯一用户名 + 密码）
- Owner 是超级身份（`permission="*"`），不是普通岗位
- 前台负责发/换桌牌；后厨负责接单→完成；服务员 Phase R1 只读履约
