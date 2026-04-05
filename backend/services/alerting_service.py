"""
P2-3 告警服务（usage_snapshots 单轨）
- 基于 account_id + metric_key 规则判定
- 边沿触发：仅「非告警 → 告警」时产生一次 triggered；持续超标不再重复触发
- 记录日志通知 + 数据库告警事件
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.db_models import Alert, AlertEvent, UsageSnapshot
from services.notify_delivery import dispatch_alert_trigger_notifications
from utils.notify_channels import normalize_notify_channels


def _extract_percent(snapshot: UsageSnapshot) -> float | None:
    if snapshot.percent_value is not None:
        return float(snapshot.percent_value)
    payload = snapshot.normalized_payload
    if isinstance(payload, dict):
        value = payload.get("percent")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


async def _find_rule(
    db: AsyncSession,
    *,
    account_id: int,
    metric_key: str,
) -> Alert | None:
    """查找告警规则，不自动创建"""
    result = await db.execute(
        select(Alert).where(
            and_(
                Alert.account_id == account_id,
                Alert.metric_key == metric_key,
            )
        )
    )
    return result.scalar_one_or_none()


async def _create_event(
    db: AsyncSession,
    *,
    rule: Alert,
    snapshot: UsageSnapshot,
    observed_percent: float | None,
    status: str,
    message: str,
    notify_channel: str = "log",
) -> None:
    event = AlertEvent(
        alert_id=rule.id,
        account_id=rule.account_id,
        service_id=snapshot.service_id,
        metric_key=rule.metric_key,
        snapshot_id=snapshot.id,
        threshold_value=float(rule.threshold or 0),
        observed_percent=observed_percent,
        status=status,
        notify_channel=notify_channel,
        message=message,
    )
    db.add(event)
    await db.flush()


async def evaluate_alert_for_snapshot(
    db: AsyncSession,
    snapshot: UsageSnapshot,
) -> dict[str, Any]:
    """
    对单条最新快照执行告警判定并写事件。
    返回观测统计。
    """
    if not settings.alert_eval_enabled:
        return {"enabled": False, "status": "disabled"}

    metric_key = str(snapshot.metric_key or "").strip()
    if not metric_key:
        return {"enabled": True, "status": "no_metric"}

    rule = await _find_rule(db, account_id=int(snapshot.account_id), metric_key=metric_key)
    if not rule:
        return {"enabled": True, "status": "no_rule", "metric_key": metric_key}
    if not rule.is_enabled:
        return {"enabled": True, "status": "rule_disabled", "metric_key": metric_key}

    observed = _extract_percent(snapshot)
    if observed is None:
        return {"enabled": True, "status": "no_percent", "metric_key": metric_key}

    now = datetime.utcnow()
    if rule.muted_until is not None:
        if now < rule.muted_until:
            return {"enabled": True, "status": "muted", "metric_key": metric_key}
        rule.muted_until = None
        await db.commit()
    threshold = float(rule.threshold or 0)
    channels = normalize_notify_channels(rule.notify_channels)
    channel_label = ",".join(channels)

    if observed >= threshold:
        if not rule.is_firing:
            rule.is_firing = True
            rule.last_triggered_at = now
            message = (
                f"[ALERT] account={rule.account_id} service={snapshot.service_id} metric={metric_key} "
                f"percent={observed:.2f}% threshold={threshold:.2f}%"
            )
            print(message)
            await _create_event(
                db,
                rule=rule,
                snapshot=snapshot,
                observed_percent=observed,
                status="triggered",
                message=message,
                notify_channel=channel_label,
            )
            await db.commit()
            await dispatch_alert_trigger_notifications(
                db,
                rule=rule,
                snapshot=snapshot,
                plain_message=message,
                channels=channels,
                observed_percent=observed,
                threshold_percent=threshold,
            )
            return {"enabled": True, "status": "triggered", "metric_key": metric_key}

        return {"enabled": True, "status": "holding", "metric_key": metric_key}

    if rule.is_firing:
        rule.is_firing = False
        rule.last_recovered_at = now
        message = (
            f"[RECOVERED] account={rule.account_id} service={snapshot.service_id} metric={metric_key} "
            f"percent={observed:.2f}% threshold={threshold:.2f}%"
        )
        print(message)
        await _create_event(
            db,
            rule=rule,
            snapshot=snapshot,
            observed_percent=observed,
            status="recovered",
            message=message,
            notify_channel=channel_label,
        )
        await db.commit()
        return {"enabled": True, "status": "recovered", "metric_key": metric_key}

    return {"enabled": True, "status": "ok", "metric_key": metric_key}
