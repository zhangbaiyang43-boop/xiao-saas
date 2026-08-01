"""
生成中控台动态口令（TOTP）的密钥。

运行一次：
    python scripts/generate_totp_secret.py

把打印出的 Secret 粘贴进 .env 的 SUPER_ADMIN_TOTP_SECRET，重启后端；
再用手机上的认证器 App（Google Authenticator / Microsoft Authenticator / 腾讯身份验证器 / Authy 都行，
微信本身没有这个功能，需要单独装一个）「手动输入密钥」的方式添加一个账户，
把同一个 Secret 输进去就行，不需要扫二维码。
"""
import sys

import pyotp

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    secret = pyotp.random_base32()
    print(f"Secret（写进 .env 的 SUPER_ADMIN_TOTP_SECRET）：{secret}")
    print()
    print("在认证器 App 里手动添加账户时：")
    print("  账户名：随便填，比如「中控台」")
    print(f"  密钥：{secret}")
    print("  类型：基于时间（TOTP）")
