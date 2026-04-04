"""
T6: 用量采集统一写入工具
- 支持写 usage_snapshots
- 统一维护 account 采集状态字段
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import Account, UsageSnapshot


def _parse_datetime(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        candidate = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None
    return None


def build_usage_snapshots(account: Account, data: dict) -> list[UsageSnapshot]:
    page_info = data.get("page_info", {}) or {}
    # 与历史查询窗口（前端 ISO Z / 后端按 UTC 解析）一致，避免依赖 MySQL session 时区
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    snapshots: list[UsageSnapshot] = []

    if account.service_id == "minimax":
        reset_hours = int(page_info.get("resetHours") or 0)
        reset_minutes = int(page_info.get("resetMinutes") or 0)
        reset_at = now + timedelta(hours=reset_hours, minutes=reset_minutes)
        expires_at = _parse_datetime(page_info.get("expiresAt"))
        snapshots.append(
            UsageSnapshot(
                account_id=account.id,
                service_id=account.service_id,
                metric_key="percent",
                used_value=float(page_info.get("used") or 0),
                total_value=float(page_info.get("total") or 0),
                percent_value=float(page_info.get("percent") or 0),
                expires_at=expires_at,
                reset_at=reset_at,
                collected_at=now,
                raw_payload=data,
                normalized_payload={
                    "used": float(page_info.get("used") or 0),
                    "total": float(page_info.get("total") or 0),
                    "percent": float(page_info.get("percent") or 0),
                    "expires_at": page_info.get("expiresAt") or "",
                    "reset_hours": reset_hours,
                    "reset_minutes": reset_minutes,
                },
            )
        )
        return snapshots

    if account.service_id == "xfyun":
        expires_at = _parse_datetime(page_info.get("expiresAt"))
        snapshots.append(
            UsageSnapshot(
                account_id=account.id,
                service_id=account.service_id,
                metric_key="percent",
                used_value=float(page_info.get("used") or 0),
                total_value=float(page_info.get("total") or 0),
                percent_value=float(page_info.get("percent") or data.get("percent") or 0),
                expires_at=expires_at,
                collected_at=now,
                raw_payload=data,
                normalized_payload={
                    "used": float(page_info.get("used") or 0),
                    "total": float(page_info.get("total") or 0),
                    "percent": float(page_info.get("percent") or data.get("percent") or 0),
                    "remain": float(page_info.get("remain") or 0),
                    "expires_at": page_info.get("expiresAt") or "",
                },
            )
        )
        return snapshots

    return snapshots


async def persist_usage_collection(
    db: AsyncSession,
    account: Account,
    data: dict,
) -> dict:
    """
    将采集结果持久化到标准快照
    返回 page_info；失败时抛 ValueError
    """
    if "error" in data:
        message = str(data.get("error", "unknown error"))
        account.last_collect_status = "failed"
        account.last_collect_error = message
        await db.commit()
        raise ValueError(message)

    page_info = data.get("page_info", {}) or {}
    if not page_info:
        account.last_collect_status = "failed"
        account.last_collect_error = "采集结果缺少 page_info"
        await db.commit()
        raise ValueError(account.last_collect_error)

    snapshots = build_usage_snapshots(account, data)
    if snapshots:
        db.add_all(snapshots)

    account.last_sync_at = datetime.now(timezone.utc).replace(tzinfo=None)
    account.last_collect_status = "success"
    account.last_collect_error = None
    await db.commit()
    return page_info
