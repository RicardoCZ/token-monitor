"""
服务注册表默认数据 Seed（T5）
- 增量：新增服务自动插入，已有服务只补齐缺失字段
- 幂等：重复执行不会产生重复记录，也不会反复覆盖已有值
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import Service


DEFAULT_SERVICE_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "minimax",
        "name": "MiniMax",
        "icon": "🍊",
        "login_url": "https://platform.minimaxi.com/user-center/payment/token-plan",
        "cookie_domains": "minimaxi.com,minimax.com",
        "adapter_key": "minimax_adapter",
        "capabilities": {
            "supports_cdp": True,
            "supports_manual_cookie": True,
            "requires_group_id": True,
            "supports_history": True,
            "supports_alert": True,
        },
        "metric_defs": [
            {
                "key": "quota_used",
                "label": "已用额度",
                "unit": "count",
            },
            {
                "key": "quota_total",
                "label": "总额度",
                "unit": "count",
            },
            {
                "key": "usage_percent",
                "label": "使用率",
                "unit": "percent",
            },
        ],
        "is_enabled": True,
    },
    {
        "id": "xfyun",
        "name": "讯飞星辰",
        "icon": "🔵",
        "login_url": "https://maas.xfyun.cn/packageSubscription",
        "cookie_domains": "xfyun.cn,xfyun.com",
        "adapter_key": "xfyun_adapter",
        "capabilities": {
            "supports_cdp": False,
            "supports_manual_cookie": True,
            "requires_group_id": False,
            "supports_history": True,
            "supports_alert": True,
        },
        "metric_defs": [
            {
                "key": "daily_used",
                "label": "当日已用",
                "unit": "w",
            },
            {
                "key": "daily_quota",
                "label": "当日额度",
                "unit": "w",
            },
            {
                "key": "usage_percent",
                "label": "使用率",
                "unit": "percent",
            },
        ],
        "is_enabled": True,
    },
]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _merge_capabilities(existing: Any, default: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(existing, dict):
        return dict(default)
    merged = dict(existing)
    for key, value in default.items():
        merged.setdefault(key, value)
    return merged


def _merge_metric_defs(existing: Any, default: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(existing, list):
        return list(default)

    merged = [item for item in existing if isinstance(item, dict)]
    existing_keys = {str(item.get("key")) for item in merged if item.get("key")}

    for item in default:
        key = str(item.get("key") or "").strip()
        if key and key not in existing_keys:
            merged.append(item)
            existing_keys.add(key)
    return merged


async def seed_service_registry(db: AsyncSession) -> tuple[int, int]:
    """
    增量幂等 seed：
    - created: 新增的服务数量
    - updated: 被补齐字段/结构的服务数量
    """
    service_ids = [item["id"] for item in DEFAULT_SERVICE_REGISTRY]
    result = await db.execute(select(Service).where(Service.id.in_(service_ids)))
    existing_services = {item.id: item for item in result.scalars().all()}

    created = 0
    updated = 0

    for payload in DEFAULT_SERVICE_REGISTRY:
        service_id = payload["id"]
        service = existing_services.get(service_id)
        if service is None:
            db.add(Service(**payload))
            created += 1
            continue

        changed = False
        for field in ("name", "icon", "login_url", "cookie_domains", "adapter_key"):
            current_value = getattr(service, field)
            default_value = payload[field]
            if _is_blank(current_value) and not _is_blank(default_value):
                setattr(service, field, default_value)
                changed = True

        merged_capabilities = _merge_capabilities(service.capabilities, payload["capabilities"])
        if merged_capabilities != service.capabilities:
            service.capabilities = merged_capabilities
            changed = True

        merged_metric_defs = _merge_metric_defs(service.metric_defs, payload["metric_defs"])
        if merged_metric_defs != service.metric_defs:
            service.metric_defs = merged_metric_defs
            changed = True

        if service.is_enabled is None:
            service.is_enabled = bool(payload["is_enabled"])
            changed = True

        if changed:
            updated += 1

    if created or updated:
        await db.commit()

    return created, updated
