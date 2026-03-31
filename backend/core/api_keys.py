"""
Token Monitor - API Key 工具
负责 API Key 生成、哈希与校验。
"""

import hashlib
import secrets

from passlib.exc import UnknownHashError
from passlib.hash import argon2


API_KEY_PREFIX = "tmk_"


def generate_api_key() -> str:
    """生成明文 API Key（仅在创建时返回给调用方）"""
    token = secrets.token_urlsafe(32)
    return f"{API_KEY_PREFIX}{token}"


def get_api_key_prefix(api_key: str) -> str:
    """提取 API Key 前缀（用于列表展示和快速识别）"""
    return api_key[:12]


def hash_api_key(api_key: str, pepper: str = "") -> str:
    """
    对 API Key 做哈希。
    - 优先使用 argon2（passlib）
    - 若 argon2 不可用，则回退到 sha256
    """
    material = f"{pepper}:{api_key}" if pepper else api_key
    try:
        return argon2.hash(material)
    except Exception:
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return f"sha256${digest}"


def verify_api_key(api_key: str, key_hash: str, pepper: str = "") -> bool:
    """校验 API Key 是否匹配哈希值"""
    material = f"{pepper}:{api_key}" if pepper else api_key

    if key_hash.startswith("sha256$"):
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return secrets.compare_digest(key_hash, f"sha256${digest}")

    try:
        return argon2.verify(material, key_hash)
    except (UnknownHashError, ValueError):
        return False
    except Exception:
        return False
