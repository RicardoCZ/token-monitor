"""
用户机器人密钥：使用 APP_SECRET_KEY 派生 Fernet 密钥后对称加密，仅存密文到 notify_webhooks JSON。
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.app_secret_key.encode("utf-8")).digest()
    )
    return Fernet(key)


def encrypt_credential(plain: str) -> str:
    """明文 -> Fernet token 字符串（可写入 JSON 列）。"""
    if not plain or not plain.strip():
        raise ValueError("empty secret")
    return _fernet().encrypt(plain.strip().encode("utf-8")).decode("ascii")


def decrypt_credential(token: str | None) -> str | None:
    """解密失败返回 None（旧数据、换过 APP_SECRET_KEY 等）。"""
    if token is None:
        return None
    s = str(token).strip()
    if not s:
        return None
    try:
        return _fernet().decrypt(s.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.warning("机器人密钥解密失败（可重配 Secret）: %s", exc, exc_info=False)
        return None
