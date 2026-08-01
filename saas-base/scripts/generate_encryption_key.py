"""
生成一把 SECRET_ENCRYPTION_KEY，用于加密商户微信支付私钥/APIv3密钥。
运行一次，把输出粘贴进 .env 的 SECRET_ENCRYPTION_KEY，然后重启后端。

用法：python scripts/generate_encryption_key.py
"""
import sys

from cryptography.fernet import Fernet

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    print(Fernet.generate_key().decode())
