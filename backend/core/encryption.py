"""
Token Monitor - 加密工具
使用 Fernet (AES) 对称加密
"""

from cryptography.fernet import Fernet
from core.config import settings
import base64
import hashlib


def _get_encryption_key() -> bytes:
    """
    从配置的 secret_key 生成加密密钥
    
    Fernet 需要 32 字节的 base64 编码密钥
    """
    # 使用 SHA256 将 secret_key 转换为 32 字节
    key = hashlib.sha256(settings.app_secret_key.encode()).digest()
    # 转换为 base64 格式
    return base64.urlsafe_b64encode(key)


def encrypt_data(plain_text: str) -> str:
    """
    加密数据
    
    Args:
        plain_text: 明文字符串
    
    Returns:
        加密后的字符串（base64 编码）
    """
    if not plain_text:
        return ""
    
    key = _get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(plain_text.encode())
    return encrypted.decode()


def decrypt_data(encrypted_text: str) -> str:
    """
    解密数据
    
    Args:
        encrypted_text: 加密后的字符串
    
    Returns:
        解密后的明文字符串
    """
    if not encrypted_text:
        return ""
    
    try:
        key = _get_encryption_key()
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_text.encode())
        return decrypted.decode()
    except Exception as e:
        print(f"Decryption failed: {e}")
        return ""


def is_encrypted(value: str) -> bool:
    """
    判断字符串是否已加密
    
    Fernet 加密后的字符串以 'gAAAAA' 开头
    """
    if not value:
        return False
    return value.startswith('gAAAAA')
