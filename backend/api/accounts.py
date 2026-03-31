"""
Token Monitor - 账号管理 API 路由
用户的平台账号管理（增删改查）
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime, timezone
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from models.database import get_db
from models.db_models import User, Account, Service, UsageSnapshot, Alert, AlertEvent
from core.security import get_current_user
from core.encryption import encrypt_data
from services.account_collector import collect_account_usage

router = APIRouter(prefix="/api/accounts", tags=["账号管理"])


# ============ 请求/响应模型 ============

class AccountCreate(BaseModel):
    service_id: str  # minimax / xfyun
    name: Optional[str] = None  # 账号别名
    cookies: str
    group_id: Optional[str] = None  # MiniMax 专用


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    cookies: Optional[str] = None
    group_id: Optional[str] = None
    is_active: Optional[bool] = None


class AccountResponse(BaseModel):
    id: int
    service_id: str
    service_name: str
    service_icon: str
    name: Optional[str]
    has_cookies: bool
    is_active: bool
    last_sync_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class AccountDetail(AccountResponse):
    """账号详情（包含用量信息）"""
    usage: Optional[dict] = None


class UsageHistoryResponse(BaseModel):
    source: str
    pagination: dict
    filters: dict
    items: List[dict]


class AlertRuleUpsertRequest(BaseModel):
    threshold: float = 80.0
    cooldown_seconds: int = 1800
    is_enabled: bool = True
    notify_channels: List[str] = ["log"]


class AlertRuleResponse(BaseModel):
    id: int
    metric_key: str
    threshold: float
    cooldown_seconds: int
    is_enabled: bool
    is_firing: bool
    notify_channels: List[str]
    last_triggered_at: Optional[datetime]
    last_recovered_at: Optional[datetime]


# ============ API 路由 ============


def _parse_history_datetime(value: Optional[str], field_name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} 格式错误，需为 ISO8601（如 2026-03-31T10:00:00Z）",
        )
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _normalize_notify_channels(raw: Any) -> list[str]:
    if isinstance(raw, list):
        channels = [str(item).strip() for item in raw if str(item).strip()]
        return channels or ["log"]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ["log"]
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    channels = [str(item).strip() for item in parsed if str(item).strip()]
                    return channels or ["log"]
            except json.JSONDecodeError:
                pass
        channels = [item.strip() for item in text.split(",") if item.strip()]
        return channels or ["log"]
    return ["log"]


def _serialize_alert_rule(rule: Alert) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=rule.id,
        metric_key=rule.metric_key,
        threshold=float(rule.threshold or 0),
        cooldown_seconds=int(rule.cooldown_seconds or 0),
        is_enabled=bool(rule.is_enabled),
        is_firing=bool(rule.is_firing),
        notify_channels=_normalize_notify_channels(rule.notify_channels),
        last_triggered_at=rule.last_triggered_at,
        last_recovered_at=rule.last_recovered_at,
    )

@router.get("", response_model=List[AccountResponse])
async def list_accounts(
    service_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的所有账号
    """
    # 构建查询
    query = select(Account).where(Account.user_id == current_user.id)
    
    if service_id:
        query = query.where(Account.service_id == service_id)
    
    query = query.order_by(Account.created_at.desc())
    
    result = await db.execute(query)
    accounts = result.scalars().all()
    
    # 获取服务信息
    service_result = await db.execute(select(Service))
    services = {s.id: s for s in service_result.scalars().all()}
    
    return [
        AccountResponse(
            id=a.id,
            service_id=a.service_id,
            service_name=services.get(a.service_id, Service(name="未知")).name,
            service_icon=services.get(a.service_id, Service(icon="❓")).icon,
            name=a.name,
            has_cookies=bool(a.cookies_encrypted),
            is_active=a.is_active,
            last_sync_at=a.last_sync_at,
            created_at=a.created_at
        )
        for a in accounts
    ]


@router.post("", response_model=AccountResponse)
async def create_account(
    req: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    创建或更新账号（保存 Cookie）
    如果该用户已有该服务的账号，则更新；否则创建新账号
    """
    # 验证服务是否存在
    result = await db.execute(select(Service).where(Service.id == req.service_id))
    service = result.scalar_one_or_none()
    
    if not service:
        raise HTTPException(status_code=400, detail="无效的服务 ID")
    
    # 检查是否已存在该服务的账号
    result = await db.execute(
        select(Account).where(
            and_(Account.user_id == current_user.id, Account.service_id == req.service_id)
        )
    )
    existing_account = result.scalar_one_or_none()
    
    # 加密 Cookie
    cookies_encrypted = encrypt_data(req.cookies)
    
    # 如果是 MiniMax 且没有 group_id，自动获取
    group_id = req.group_id
    if req.service_id == "minimax" and not group_id:
        from services.minimax_service import MiniMaxService
        minimax_service = MiniMaxService()
        group_id = minimax_service._fetch_group_id(req.cookies)
        print(f"自动获取 MiniMax GroupId: {group_id}")
    
    if existing_account:
        # 更新现有账号
        existing_account.cookies_encrypted = cookies_encrypted
        existing_account.group_id = group_id
        if req.name:
            existing_account.name = req.name
        await db.commit()
        await db.refresh(existing_account)
        account = existing_account
    else:
        # 创建新账号
        account = Account(
            user_id=current_user.id,
            service_id=req.service_id,
            name=req.name or service.name,
            cookies_encrypted=cookies_encrypted,
            group_id=group_id
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
    
    return AccountResponse(
        id=account.id,
        service_id=account.service_id,
        service_name=service.name,
        service_icon=service.icon,
        name=account.name,
        has_cookies=True,
        is_active=account.is_active,
        last_sync_at=account.last_sync_at,
        created_at=account.created_at
    )


@router.get("/{account_id}", response_model=AccountDetail)
async def get_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取账号详情
    """
    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    
    # 获取服务信息
    service_result = await db.execute(select(Service).where(Service.id == account.service_id))
    service = service_result.scalar_one_or_none()
    
    # 获取最新用量（usage_snapshots 单轨）
    usage_data = None
    snapshot_result = await db.execute(
        select(UsageSnapshot)
        .where(UsageSnapshot.account_id == account_id)
        .order_by(UsageSnapshot.collected_at.desc(), UsageSnapshot.id.desc())
        .limit(1)
    )
    latest_snapshot = snapshot_result.scalar_one_or_none()
    if latest_snapshot:
        normalized_payload = latest_snapshot.normalized_payload or {}
        usage_data = {
            "used": latest_snapshot.used_value,
            "total": latest_snapshot.total_value,
            "percent": latest_snapshot.percent_value,
            "expires_at": (
                latest_snapshot.expires_at.isoformat()
                if latest_snapshot.expires_at
                else normalized_payload.get("expires_at", "")
            ),
            "reset_hours": normalized_payload.get("reset_hours", 0),
            "reset_minutes": normalized_payload.get("reset_minutes", 0),
            "source": "usage_snapshots",
        }
    
    return AccountDetail(
        id=account.id,
        service_id=account.service_id,
        service_name=service.name if service else "未知",
        service_icon=service.icon if service else "❓",
        name=account.name,
        has_cookies=bool(account.cookies_encrypted),
        is_active=account.is_active,
        last_sync_at=account.last_sync_at,
        created_at=account.created_at,
        usage=usage_data
    )


@router.get("/{account_id}/history", response_model=UsageHistoryResponse)
async def get_account_usage_history(
    account_id: int,
    limit: int = 20,
    offset: int = 0,
    metric_key: Optional[str] = None,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取账号用量历史（usage_snapshots 单轨，支持分页与过滤）
    """
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    normalized_metric_key = metric_key.strip() if metric_key else None
    if normalized_metric_key == "":
        normalized_metric_key = None
    start_dt = _parse_history_datetime(start_at, "start_at")
    end_dt = _parse_history_datetime(end_at, "end_at")
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start_at 不能晚于 end_at")

    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    conditions = [UsageSnapshot.account_id == account_id]
    if normalized_metric_key:
        conditions.append(UsageSnapshot.metric_key == normalized_metric_key)
    if start_dt:
        conditions.append(UsageSnapshot.collected_at >= start_dt)
    if end_dt:
        conditions.append(UsageSnapshot.collected_at <= end_dt)

    total_result = await db.execute(
        select(func.count())
        .select_from(UsageSnapshot)
        .where(and_(*conditions))
    )
    total = int(total_result.scalar() or 0)

    snapshot_result = await db.execute(
        select(UsageSnapshot)
        .where(and_(*conditions))
        .order_by(UsageSnapshot.collected_at.desc(), UsageSnapshot.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    )
    snapshots = snapshot_result.scalars().all()
    items = [
        {
            "metric_key": row.metric_key,
            "used": row.used_value,
            "total": row.total_value,
            "percent": row.percent_value,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "reset_at": row.reset_at.isoformat() if row.reset_at else None,
            "collected_at": row.collected_at.isoformat() if row.collected_at else None,
            "normalized_payload": row.normalized_payload,
        }
        for row in snapshots
    ]
    return UsageHistoryResponse(
        source="usage_snapshots",
        pagination={
            "limit": safe_limit,
            "offset": safe_offset,
            "returned": len(items),
            "total": total,
            "has_more": (safe_offset + len(items)) < total,
        },
        filters={
            "metric_key": normalized_metric_key,
            "start_at": start_at,
            "end_at": end_at,
        },
        items=items,
    )


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    req: AccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新账号信息
    """
    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    
    # 更新字段
    if req.name is not None:
        account.name = req.name
    if req.cookies is not None:
        # 加密 Cookie
        account.cookies_encrypted = encrypt_data(req.cookies)
        
        # 如果是 MiniMax 且更新了 Cookie，重新获取 group_id
        if account.service_id == "minimax" and not req.group_id:
            from services.minimax_service import MiniMaxService
            minimax_service = MiniMaxService()
            new_group_id = minimax_service._fetch_group_id(req.cookies)
            if new_group_id:
                account.group_id = new_group_id
                print(f"更新 MiniMax GroupId: {new_group_id}")
    if req.group_id is not None:
        account.group_id = req.group_id
    if req.is_active is not None:
        account.is_active = req.is_active
    
    await db.commit()
    await db.refresh(account)
    
    # 获取服务信息
    service_result = await db.execute(select(Service).where(Service.id == account.service_id))
    service = service_result.scalar_one_or_none()
    
    return AccountResponse(
        id=account.id,
        service_id=account.service_id,
        service_name=service.name if service else "未知",
        service_icon=service.icon if service else "❓",
        name=account.name,
        has_cookies=bool(account.cookies_encrypted),
        is_active=account.is_active,
        last_sync_at=account.last_sync_at,
        created_at=account.created_at
    )


@router.get("/{account_id}/alerts", response_model=List[AlertRuleResponse])
async def list_account_alert_rules(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取账号告警规则（按 metric_key）"""
    account_result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = account_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    result = await db.execute(
        select(Alert)
        .where(Alert.account_id == account_id)
        .order_by(Alert.metric_key.asc())
    )
    rules = result.scalars().all()
    return [_serialize_alert_rule(item) for item in rules]


@router.put("/{account_id}/alerts/{metric_key}", response_model=AlertRuleResponse)
async def upsert_account_alert_rule(
    account_id: int,
    metric_key: str,
    req: AlertRuleUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """按 account_id + metric_key 新增/更新告警规则"""
    normalized_metric_key = metric_key.strip()
    if not normalized_metric_key:
        raise HTTPException(status_code=400, detail="metric_key 不能为空")

    account_result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = account_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    result = await db.execute(
        select(Alert).where(
            and_(
                Alert.account_id == account_id,
                Alert.metric_key == normalized_metric_key,
            )
        )
    )
    rule = result.scalar_one_or_none()
    channels = _normalize_notify_channels(req.notify_channels)

    if rule is None:
        rule = Alert(
            account_id=account_id,
            metric_key=normalized_metric_key,
            threshold=float(req.threshold),
            cooldown_seconds=max(0, int(req.cooldown_seconds)),
            notify_channels=json.dumps(channels, ensure_ascii=False),
            is_enabled=bool(req.is_enabled),
            is_firing=False,
        )
        db.add(rule)
    else:
        rule.threshold = float(req.threshold)
        rule.cooldown_seconds = max(0, int(req.cooldown_seconds))
        rule.notify_channels = json.dumps(channels, ensure_ascii=False)
        rule.is_enabled = bool(req.is_enabled)

    await db.commit()
    await db.refresh(rule)
    return _serialize_alert_rule(rule)


@router.get("/{account_id}/alerts/events")
async def list_account_alert_events(
    account_id: int,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取账号告警事件（数据库事件流）"""
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)

    account_result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = account_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    total_result = await db.execute(
        select(func.count())
        .select_from(AlertEvent)
        .where(AlertEvent.account_id == account_id)
    )
    total = int(total_result.scalar() or 0)

    result = await db.execute(
        select(AlertEvent)
        .where(AlertEvent.account_id == account_id)
        .order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    )
    events = result.scalars().all()
    items = [
        {
            "id": item.id,
            "alert_id": item.alert_id,
            "service_id": item.service_id,
            "metric_key": item.metric_key,
            "snapshot_id": item.snapshot_id,
            "threshold_value": item.threshold_value,
            "observed_percent": item.observed_percent,
            "status": item.status,
            "notify_channel": item.notify_channel,
            "message": item.message,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in events
    ]
    return {
        "pagination": {
            "limit": safe_limit,
            "offset": safe_offset,
            "returned": len(items),
            "total": total,
            "has_more": (safe_offset + len(items)) < total,
        },
        "items": items,
    }


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    删除账号
    """
    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    
    await db.delete(account)
    await db.commit()
    
    return {"message": "账号已删除", "success": True}


@router.post("/{account_id}/sync")
async def sync_account_usage(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    同步账号用量（从平台 API 获取最新数据）
    """
    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    
    try:
        page_info = await collect_account_usage(db, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "message": "同步成功",
        "success": True,
        "usage": page_info
    }
