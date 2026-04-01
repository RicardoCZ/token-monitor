#!/usr/bin/env python3
"""
P2-3 告警链路迁移：
- alerts 扩展 metric_key/cooldown_seconds/is_firing/last_recovered_at
- 新增 alert_events 表
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


CREATE_ALERT_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS alert_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    alert_id INT NOT NULL,
    account_id INT NOT NULL,
    service_id VARCHAR(50) NOT NULL,
    metric_key VARCHAR(64) NOT NULL,
    snapshot_id INT NULL,
    threshold_value DOUBLE NOT NULL,
    observed_percent DOUBLE NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'triggered',
    notify_channel VARCHAR(64) NOT NULL DEFAULT 'log',
    message TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_alert_events_alert
      FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE,
    CONSTRAINT fk_alert_events_account
      FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    CONSTRAINT fk_alert_events_snapshot
      FOREIGN KEY (snapshot_id) REFERENCES usage_snapshots(id) ON DELETE SET NULL
)
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX idx_alerts_metric_key ON alerts (metric_key)",
    "CREATE INDEX idx_alert_events_alert_id ON alert_events (alert_id)",
    "CREATE INDEX idx_alert_events_account_id ON alert_events (account_id)",
    "CREATE INDEX idx_alert_events_metric_key ON alert_events (metric_key)",
    "CREATE INDEX idx_alert_events_created_at ON alert_events (created_at)",
]


async def run_migration() -> None:
    async with engine.begin() as conn:
        await _add_column_if_missing(conn, "alerts", "metric_key", "metric_key VARCHAR(64) NOT NULL DEFAULT 'percent'")
        await _add_column_if_missing(conn, "alerts", "cooldown_seconds", "cooldown_seconds INT NOT NULL DEFAULT 1800")
        await _add_column_if_missing(conn, "alerts", "is_firing", "is_firing BOOLEAN NOT NULL DEFAULT FALSE")
        await _add_column_if_missing(conn, "alerts", "last_recovered_at", "last_recovered_at DATETIME NULL")

        await conn.execute(text(CREATE_ALERT_EVENTS_SQL))

        for sql in CREATE_INDEXES_SQL:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass

    print("✅ P2-3 告警迁移完成")


if __name__ == "__main__":
    asyncio.run(run_migration())
