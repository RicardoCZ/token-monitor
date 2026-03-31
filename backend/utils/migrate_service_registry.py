#!/usr/bin/env python3
"""
一次性迁移脚本：服务注册表 + 历史快照（Phase T1）

用法：
    cd backend
    python -m utils.migrate_service_registry
"""

import asyncio

from sqlalchemy import text

from models.database import engine


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    query = text(
        """
        SELECT COUNT(1)
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND column_name = :column_name
        """
    )
    result = await conn.execute(
        query,
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(result.scalar())


async def _add_column_if_missing(conn, table_name: str, column_name: str, ddl: str) -> None:
    if await _column_exists(conn, table_name, column_name):
        return
    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


CREATE_USAGE_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS usage_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NOT NULL,
    service_id VARCHAR(50) NOT NULL,
    metric_key VARCHAR(64) NOT NULL,
    used_value DOUBLE NULL,
    total_value DOUBLE NULL,
    percent_value DOUBLE NULL,
    expires_at DATETIME NULL,
    reset_at DATETIME NULL,
    raw_payload JSON NULL,
    normalized_payload JSON NULL,
    collected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_usage_snapshots_account
      FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
)
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX idx_services_is_enabled ON services (is_enabled)",
    "CREATE INDEX idx_accounts_service_id ON accounts (service_id)",
    "CREATE INDEX idx_usage_snapshots_account_id ON usage_snapshots (account_id)",
    "CREATE INDEX idx_usage_snapshots_service_id ON usage_snapshots (service_id)",
    "CREATE INDEX idx_usage_snapshots_metric_key ON usage_snapshots (metric_key)",
    "CREATE INDEX idx_usage_snapshots_collected_at ON usage_snapshots (collected_at)",
    "CREATE INDEX idx_usage_snapshots_service_metric_time ON usage_snapshots (service_id, metric_key, collected_at)",
]


async def run_migration() -> None:
    async with engine.begin() as conn:
        # services 扩展
        await _add_column_if_missing(conn, "services", "adapter_key", "adapter_key VARCHAR(100) NULL")
        await _add_column_if_missing(conn, "services", "capabilities", "capabilities JSON NULL")
        await _add_column_if_missing(conn, "services", "metric_defs", "metric_defs JSON NULL")
        await _add_column_if_missing(conn, "services", "is_enabled", "is_enabled BOOLEAN NOT NULL DEFAULT TRUE")
        await _add_column_if_missing(
            conn,
            "services",
            "updated_at",
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
        )

        # accounts 扩展
        await _add_column_if_missing(conn, "accounts", "service_meta", "service_meta JSON NULL")
        await _add_column_if_missing(conn, "accounts", "last_collect_status", "last_collect_status VARCHAR(32) NULL")
        await _add_column_if_missing(conn, "accounts", "last_collect_error", "last_collect_error TEXT NULL")

        # usage_snapshots 新表
        await conn.execute(text(CREATE_USAGE_SNAPSHOTS_TABLE_SQL))

        # 索引（重复执行时跳过）
        for sql in CREATE_INDEXES_SQL:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass

    print("✅ 服务注册表迁移完成")


if __name__ == "__main__":
    asyncio.run(run_migration())
