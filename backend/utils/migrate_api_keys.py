#!/usr/bin/env python3
"""
一次性迁移脚本：新增 api_keys 表（Phase 1）

用法：
    cd backend
    python -m utils.migrate_api_keys
"""

import asyncio

from sqlalchemy import text

from models.database import engine


CREATE_API_KEYS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    key_prefix VARCHAR(32) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    scopes TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    expires_at DATETIME NULL,
    last_used_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_api_keys_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX idx_api_keys_user_id ON api_keys (user_id)",
    "CREATE INDEX idx_api_keys_key_prefix ON api_keys (key_prefix)",
    "CREATE UNIQUE INDEX uq_api_keys_key_hash ON api_keys (key_hash)",
]


async def run_migration() -> None:
    """执行迁移"""
    async with engine.begin() as conn:
        await conn.execute(text(CREATE_API_KEYS_TABLE_SQL))

        for sql in CREATE_INDEXES_SQL:
            try:
                await conn.execute(text(sql))
            except Exception:
                # 索引已存在时跳过，保证脚本可重复执行
                pass

    print("✅ api_keys 迁移完成")


if __name__ == "__main__":
    asyncio.run(run_migration())
