"""
告警触发时的外发通知：飞书私聊（Open API）、QQ 官方单聊（OpenAPI v2）。
仅使用各用户在 notify_webhooks 中配置的机器人 AppId+Secret；未配齐则不发送。
仅处理「首次触发」路径；恢复时不调用。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.credential_crypto import decrypt_credential
from models.db_models import Account, Alert, UsageSnapshot, User
from services.feishu_open_api import send_text_to_feishu_open_id
from services.qq_bot_open_api import send_c2c_text

logger = logging.getLogger(__name__)


def _coerce_notify_webhooks_dict(raw: Any) -> dict | None:
    """与 auth 路由一致：列可能是 dict 或 JSON 字符串。"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def parse_qq_user_openid(raw: Any) -> str | None:
    """QQ 单聊用户 openid（OpenAPI /v2/users/{openid}/messages）。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(raw, dict):
        v = raw.get("qq_openid")
        if v is None:
            return None
        s = str(v).strip()
        return s or None
    return None


def parse_feishu_open_id(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(raw, dict):
        v = raw.get("feishu_open_id")
        if v is None:
            return None
        s = str(v).strip()
        return s or None
    return None


def _resolve_feishu_app_credentials(wh: dict | None) -> tuple[str | None, str | None]:
    if not wh:
        return None, None
    ua = (wh.get("feishu_app_id") or "").strip() or None
    enc = wh.get("feishu_app_secret_enc")
    us = decrypt_credential(enc) if isinstance(enc, str) else None
    if ua and us:
        return ua, us
    return None, None


def _resolve_qq_app_credentials(wh: dict | None) -> tuple[str | None, str | None]:
    if not wh:
        return None, None
    ua = (wh.get("qq_bot_app_id") or "").strip() or None
    enc = wh.get("qq_bot_app_secret_enc")
    us = decrypt_credential(enc) if isinstance(enc, str) else None
    if ua and us:
        return ua, us
    return None, None


def format_alert_notification_text(
    *,
    account_label: str,
    service_id: str,
    metric_key: str,
    observed_pct: float | None,
    threshold_pct: float | None,
    account_id: int | None = None,
    footer_note: str | None = None,
) -> str:
    """
    飞书 / QQ 共用纯文本模板（msg_type=text）。
    时间统一为 UTC，与告警评估用的 utcnow 一致。
    """
    obs = f"{float(observed_pct):.2f}" if observed_pct is not None else "—"
    th = f"{float(threshold_pct):.2f}" if threshold_pct is not None else "—"
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    id_line = f"\n🆔 账号 ID：{account_id}" if account_id is not None else ""
    foot = f"\n\n{footer_note}" if footer_note else ""
    label = (account_label or "").strip() or "（未命名）"
    svc = (service_id or "").strip() or "—"
    mkey = (metric_key or "").strip() or "—"
    return (
        "🚨 Token Monitor · 告警\n"
        "────────────────────\n"
        f"🏷️ 账号：{label}\n"
        f"☁️ 服务：{svc}\n"
        f"📈 指标：{mkey}\n"
        f"📍 当前值：{obs}%\n"
        f"⚖️ 阈值：{th}%\n"
        f"⏰ 时间：{when}"
        f"{id_line}"
        f"{foot}"
    )


async def dispatch_alert_trigger_notifications(
    db: AsyncSession,
    *,
    rule: Alert,
    snapshot: UsageSnapshot,
    plain_message: str,
    channels: list[str],
    observed_percent: float | None = None,
    threshold_percent: float | None = None,
) -> None:
    """按规则渠道发送文本（触发告警时）。"""
    need = {c.lower() for c in channels if c and c.lower() in ("feishu", "qq")}
    if not need:
        return

    result = await db.execute(select(Account).where(Account.id == rule.account_id))
    account = result.scalar_one_or_none()
    if not account:
        return

    result = await db.execute(select(User).where(User.id == account.user_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    wh = _coerce_notify_webhooks_dict(user.notify_webhooks)
    qq_openid = parse_qq_user_openid(wh)
    feishu_open_id = parse_feishu_open_id(wh)

    body = format_alert_notification_text(
        account_label=account.name or "",
        service_id=str(snapshot.service_id or ""),
        metric_key=str(rule.metric_key or ""),
        observed_pct=observed_percent,
        threshold_pct=threshold_percent,
        account_id=int(rule.account_id),
        footer_note=None,
    )

    if "feishu" in need:
        fid, fsec = _resolve_feishu_app_credentials(wh)
        if feishu_open_id:
            if fid and fsec:
                if not await send_text_to_feishu_open_id(
                    feishu_open_id, body, app_id=fid, app_secret=fsec
                ):
                    logger.warning(
                        "飞书私聊发送失败 user_id=%s open_id=%s",
                        user.id,
                        feishu_open_id,
                    )
            else:
                logger.warning(
                    "告警渠道 feishu 已选但无完整应用凭证：请在通知设置填写飞书 App ID 与已保存的 App Secret（user_id=%s）",
                    user.id,
                )
        else:
            logger.warning(
                "告警渠道 feishu 已选但用户未配置飞书私聊 Open ID: user_id=%s",
                user.id,
            )

    if "qq" in need:
        qid, qsec = _resolve_qq_app_credentials(wh)
        if qq_openid:
            if qid and qsec:
                if not await send_c2c_text(qq_openid, body, app_id=qid, app_secret=qsec):
                    logger.warning("QQ 单聊发送失败 user_id=%s", user.id)
            else:
                logger.warning(
                    "告警渠道 qq 已选但无完整应用凭证：请在通知设置填写 QQ App ID 与已保存的 App Secret（user_id=%s）",
                    user.id,
                )
        else:
            logger.warning(
                "告警渠道 qq 已选但用户未配置 qq_openid: user_id=%s",
                user.id,
            )
