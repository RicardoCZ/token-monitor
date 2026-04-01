"""
Token Monitor - 服务注册表 API
统一输出可用服务元数据，供前端/移动端动态渲染。
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import AuthContext, require_scope
from models.database import get_db
from models.db_models import Service

router = APIRouter(prefix="/api/services", tags=["服务注册表"])

def _normalize_cookie_domains(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in text.split(",") if part.strip()]
    return []


def _normalize_json_field(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return default
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, type(default)) else default
        except json.JSONDecodeError:
            return default
    return default


def _serialize_service(item: Service) -> dict[str, Any]:
    raw_metric_defs = _normalize_json_field(item.metric_defs, [])
    normalized_metric_defs: list[dict[str, Any]] = []
    seen_metric_keys: set[str] = set()
    if isinstance(raw_metric_defs, list):
        for metric in raw_metric_defs:
            if not isinstance(metric, dict):
                continue
            key = str(metric.get("key") or "").strip()
            if not key or key in seen_metric_keys:
                continue
            seen_metric_keys.add(key)
            normalized_metric_defs.append(
                {
                    **metric,
                    "key": key,
                }
            )

    return {
        "id": item.id,
        "name": item.name,
        "icon": item.icon,
        "login_url": item.login_url,
        "cookie_domains": _normalize_cookie_domains(item.cookie_domains),
        "adapter_key": item.adapter_key or f"{item.id}_adapter",
        "capabilities": _normalize_json_field(
            item.capabilities,
            {
                "supports_cdp": True,
                "supports_manual_cookie": True,
                "requires_group_id": False,
                "supports_history": True,
                "supports_alert": True,
            },
        ),
        "metric_defs": normalized_metric_defs,
        "is_enabled": bool(item.is_enabled),
    }


@router.get("")
async def list_services(
    auth: AuthContext = Depends(require_scope("cookie:read")),
    db: AsyncSession = Depends(get_db),
):
    """列出启用状态的服务注册表"""
    result = await db.execute(
        select(Service).where(Service.is_enabled.is_(True)).order_by(Service.id.asc())
    )
    services = result.scalars().all()
    return [_serialize_service(item) for item in services]


@router.get("/{service_id}")
async def get_service(
    service_id: str,
    auth: AuthContext = Depends(require_scope("cookie:read")),
    db: AsyncSession = Depends(get_db),
):
    """获取单个服务元数据"""
    result = await db.execute(
        select(Service)
        .where(Service.id == service_id)
        .where(Service.is_enabled.is_(True))
    )
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="服务不存在或未启用")
    return _serialize_service(service)
