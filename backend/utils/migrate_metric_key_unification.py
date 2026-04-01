#!/usr/bin/env python3
"""
Metric Key 统一清理：
- usage_snapshots: quota/daily_quota/usage_percent -> percent
- alerts/alert_events: 同步清理历史旧 key（如存在）
"""

import asyncio

from sqlalchemy import text

from models.database import engine


async def run_migration() -> None:
    async with engine.begin() as conn:
        # usage_snapshots 存量修正
        quota_result = await conn.execute(
            text(
                """
                UPDATE usage_snapshots
                SET metric_key = 'percent'
                WHERE metric_key = 'quota'
                """
            )
        )
        daily_quota_result = await conn.execute(
            text(
                """
                UPDATE usage_snapshots
                SET metric_key = 'percent'
                WHERE metric_key = 'daily_quota'
                """
            )
        )
        usage_percent_result = await conn.execute(
            text(
                """
                UPDATE usage_snapshots
                SET metric_key = 'percent'
                WHERE metric_key = 'usage_percent'
                """
            )
        )

        # alerts / alert_events 历史容错修正（通常应为 0）
        alerts_quota_result = await conn.execute(
            text(
                """
                UPDATE alerts
                SET metric_key = 'percent'
                WHERE metric_key = 'quota'
                """
            )
        )
        alerts_daily_quota_result = await conn.execute(
            text(
                """
                UPDATE alerts
                SET metric_key = 'percent'
                WHERE metric_key IN ('daily_quota', 'usage_percent')
                """
            )
        )
        events_quota_result = await conn.execute(
            text(
                """
                UPDATE alert_events
                SET metric_key = 'percent'
                WHERE metric_key = 'quota'
                """
            )
        )
        events_daily_quota_result = await conn.execute(
            text(
                """
                UPDATE alert_events
                SET metric_key = 'percent'
                WHERE metric_key IN ('daily_quota', 'usage_percent')
                """
            )
        )

    print("✅ Metric Key 统一清理完成")
    print(
        "usage_snapshots: quota->percent={}, daily_quota->percent={}, usage_percent->percent={}".format(
            int(quota_result.rowcount or 0),
            int(daily_quota_result.rowcount or 0),
            int(usage_percent_result.rowcount or 0),
        )
    )
    print(
        "alerts: quota->percent={}, daily_quota/usage_percent->percent={}".format(
            int(alerts_quota_result.rowcount or 0),
            int(alerts_daily_quota_result.rowcount or 0),
        )
    )
    print(
        "alert_events: quota->percent={}, daily_quota/usage_percent->percent={}".format(
            int(events_quota_result.rowcount or 0),
            int(events_daily_quota_result.rowcount or 0),
        )
    )


if __name__ == "__main__":
    asyncio.run(run_migration())
