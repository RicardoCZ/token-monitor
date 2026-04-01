#!/usr/bin/env python3
"""
历史数据清理脚本（P2-5）

能力：
- 默认按 90 天保留策略清理历史数据
- 支持 dry-run（仅预览，不落库）
- 支持按账号维度选择性清理（--account-id）
- 支持按账号回滚检查预览（--rollback-check）

示例：
  python3 -m utils.cleanup_history_data --dry-run
  python3 -m utils.cleanup_history_data --retention-days 90 --account-id 12 --account-id 18 --dry-run
  python3 -m utils.cleanup_history_data --rollback-check
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import async_session_maker, engine
from models.db_models import AlertEvent, UsageSnapshot


@dataclass
class TableSpec:
    name: str
    model: Any
    time_column: Any
    account_column: Any


TABLE_SPECS: list[TableSpec] = [
    TableSpec(
        name="usage_snapshots",
        model=UsageSnapshot,
        time_column=UsageSnapshot.collected_at,
        account_column=UsageSnapshot.account_id,
    ),
    TableSpec(
        name="alert_events",
        model=AlertEvent,
        time_column=AlertEvent.created_at,
        account_column=AlertEvent.account_id,
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清理历史数据（支持 dry-run 与按账号筛选）")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=90,
        help="保留天数，默认 90",
    )
    parser.add_argument(
        "--account-id",
        type=int,
        action="append",
        default=[],
        help="按账号维度清理，可重复传入多个账号 ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览，不执行删除",
    )
    parser.add_argument(
        "--rollback-check",
        action="store_true",
        help="输出按账号的清理前/后数量检查，便于回滚评估",
    )
    parser.add_argument(
        "--tables",
        choices=["all", "usage_snapshots", "alert_events"],
        default="all",
        help="选择清理范围，默认 all",
    )
    return parser.parse_args()


def pick_specs(table_name: str) -> list[TableSpec]:
    if table_name == "all":
        return TABLE_SPECS
    return [spec for spec in TABLE_SPECS if spec.name == table_name]


def build_conditions(spec: TableSpec, cutoff: datetime, account_ids: list[int]) -> list[Any]:
    conditions = [spec.time_column < cutoff]
    if account_ids:
        conditions.append(spec.account_column.in_(account_ids))
    return conditions


async def collect_delete_preview(
    db: AsyncSession,
    spec: TableSpec,
    cutoff: datetime,
    account_ids: list[int],
) -> dict[str, Any]:
    conditions = build_conditions(spec, cutoff, account_ids)
    total_result = await db.execute(
        select(func.count()).select_from(spec.model).where(and_(*conditions))
    )
    total = int(total_result.scalar() or 0)

    if total == 0:
        return {
            "table": spec.name,
            "delete_count": 0,
            "oldest_at": None,
            "newest_at": None,
            "accounts_count": 0,
        }

    range_result = await db.execute(
        select(
            func.min(spec.time_column),
            func.max(spec.time_column),
            func.count(func.distinct(spec.account_column)),
        ).where(and_(*conditions))
    )
    oldest_at, newest_at, accounts_count = range_result.one()

    return {
        "table": spec.name,
        "delete_count": total,
        "oldest_at": oldest_at,
        "newest_at": newest_at,
        "accounts_count": int(accounts_count or 0),
    }


async def rollback_check(
    db: AsyncSession,
    spec: TableSpec,
    cutoff: datetime,
    account_ids: list[int],
) -> list[dict[str, Any]]:
    if account_ids:
        targets = sorted(set(account_ids))
    else:
        target_result = await db.execute(
            select(spec.account_column)
            .where(spec.time_column < cutoff)
            .group_by(spec.account_column)
            .order_by(spec.account_column.asc())
        )
        targets = [int(value) for value in target_result.scalars().all()]

    report: list[dict[str, Any]] = []
    for account_id in targets:
        total_result = await db.execute(
            select(func.count())
            .select_from(spec.model)
            .where(spec.account_column == account_id)
        )
        total = int(total_result.scalar() or 0)

        delete_result = await db.execute(
            select(func.count())
            .select_from(spec.model)
            .where(and_(spec.account_column == account_id, spec.time_column < cutoff))
        )
        delete_count = int(delete_result.scalar() or 0)
        retain_count = max(0, total - delete_count)

        latest_retained_result = await db.execute(
            select(func.max(spec.time_column))
            .where(and_(spec.account_column == account_id, spec.time_column >= cutoff))
        )
        latest_retained = latest_retained_result.scalar()

        report.append(
            {
                "account_id": account_id,
                "total_before": total,
                "to_delete": delete_count,
                "retain_after": retain_count,
                "latest_retained_at": latest_retained,
            }
        )
    return report


async def execute_cleanup(
    db: AsyncSession,
    spec: TableSpec,
    cutoff: datetime,
    account_ids: list[int],
) -> int:
    stmt = delete(spec.model).where(and_(*build_conditions(spec, cutoff, account_ids)))
    result = await db.execute(stmt)
    return int(result.rowcount or 0)


async def main() -> None:
    args = parse_args()
    if args.retention_days < 1:
        raise SystemExit("retention-days 必须 >= 1")

    cutoff = datetime.utcnow() - timedelta(days=args.retention_days)
    target_accounts = sorted(set(int(a) for a in args.account_id))
    specs = pick_specs(args.tables)

    print("=== Token Monitor 历史数据清理 ===")
    print(f"保留策略: 最近 {args.retention_days} 天")
    print(f"截止时间: {cutoff.isoformat()} (UTC)")
    print(f"目标表: {', '.join(spec.name for spec in specs)}")
    if target_accounts:
        print(f"账号过滤: {target_accounts}")
    else:
        print("账号过滤: 全部账号")
    print(f"执行模式: {'dry-run' if args.dry_run else 'delete'}")
    print("")

    try:
        async with async_session_maker() as db:
            previews = []
            for spec in specs:
                preview = await collect_delete_preview(db, spec, cutoff, target_accounts)
                previews.append(preview)
                print(
                    f"[预览] {spec.name}: 将删除 {preview['delete_count']} 条 "
                    f"(账号数 {preview['accounts_count']}, 时间范围 {preview['oldest_at']} ~ {preview['newest_at']})"
                )
            print("")

            if args.rollback_check:
                print("=== 回滚检查（按账号）===")
                for spec in specs:
                    rows = await rollback_check(db, spec, cutoff, target_accounts)
                    if not rows:
                        print(f"[{spec.name}] 无需清理账号")
                        continue
                    print(f"[{spec.name}]")
                    for item in rows:
                        warning = " ⚠️ 清理后无保留数据" if item["retain_after"] == 0 and item["to_delete"] > 0 else ""
                        print(
                            "  - account_id={account_id} before={total_before} delete={to_delete} "
                            "after={retain_after} latest_retained={latest_retained_at}{warning}".format(
                                **item,
                                warning=warning,
                            )
                        )
                print("")

            if args.dry_run:
                print("dry-run 完成：未执行删除。")
                return

            deleted_total = 0
            for spec in specs:
                deleted = await execute_cleanup(db, spec, cutoff, target_accounts)
                deleted_total += deleted
                print(f"[执行] {spec.name}: 已删除 {deleted} 条")
            await db.commit()
            print("")
            print(f"清理完成：总删除 {deleted_total} 条。")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
