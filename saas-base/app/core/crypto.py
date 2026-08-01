"""
商户敏感字段（微信支付私钥/APIv3密钥）的应用层加密。

密钥来自环境变量 SECRET_ENCRYPTION_KEY，不入库、不进 git，用
scripts/generate_encryption_key.py 生成一次即可。

兼容旧数据：解密时如果这个值根本不是本机制加密过的（历史明文），会解密失败，
这时原样返回明文而不是报错——避免还没重新保存过的旧商户配置读取时直接炸掉。
下次保存/复制配置会自动把它换成密文。
"""
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet | None:
    key = (settings.SECRET_ENCRYPTION_KEY or "").strip()
    if not key:
        return None
    return Fernet(key.encode())


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return value
    fernet = _get_fernet()
    if fernet is None:
        return value
    return fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return value
    fernet = _get_fernet()
    if fernet is None:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return value
