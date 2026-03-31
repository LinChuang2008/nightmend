"""
应用级对称加密工具 (Application-level symmetric encryption)

使用 AES-GCM 加密敏感字段（如数据库监控密码），密钥从 JWT_SECRET_KEY 派生。
格式: base64(nonce + ciphertext + tag)
"""
import base64
import hashlib
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@lru_cache(maxsize=1)
def _derive_key() -> bytes:
    """从 JWT_SECRET_KEY 派生 256-bit AES 密钥。"""
    from app.core.config import settings
    return hashlib.sha256(settings.jwt_secret_key.encode()).digest()


def encrypt_value(plaintext: str) -> str:
    """加密字符串，返回 base64 编码的密文。空字符串原样返回。"""
    if not plaintext:
        return plaintext
    key = _derive_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_value(encrypted: str) -> str:
    """解密 base64 编码的密文，返回明文。空或无效输入原样返回。"""
    if not encrypted:
        return encrypted
    try:
        raw = base64.b64decode(encrypted)
        if len(raw) < 13:  # nonce(12) + at least 1 byte
            return encrypted  # 未加密的旧数据，原样返回
        nonce = raw[:12]
        ciphertext = raw[12:]
        key = _derive_key()
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode()
    except Exception:
        return encrypted  # 解密失败（可能是未加密的旧数据），原样返回
