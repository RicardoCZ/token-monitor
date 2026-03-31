"""
Token Monitor - 账号管理 API 路由
用户的平台账号管理（增删改查）
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.database import get_db
from models.db_models import User, Account, Service, UsageHistory, UsageSnapshot
from core.security import get_current_user
from core.config import settings
from core.encryption import encrypt_data, decrypt_data
from utils.usage_snapshot_writer import persist_usage_collection

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
    total: int
    items: List[dict]


# ============ API 路由 ============

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
    
    # 获取最新用量（优先 usage_snapshots，旧表兜底）
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
    else:
        usage_result = await db.execute(
            select(UsageHistory)
            .where(UsageHistory.account_id == account_id)
            .order_by(UsageHistory.recorded_at.desc())
            .limit(1)
        )
        latest_usage = usage_result.scalar_one_or_none()
        if latest_usage:
            usage_data = {
                "used": latest_usage.used,
                "total": latest_usage.total,
                "percent": latest_usage.percent,
                "expires_at": latest_usage.expires_at,
                "reset_hours": latest_usage.reset_hours,
                "reset_minutes": latest_usage.reset_minutes,
                "source": "usage_history",
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取账号用量历史（优先 usage_snapshots，旧表兜底）
    """
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)

    result = await db.execute(
        select(Account).where(
            and_(Account.id == account_id, Account.user_id == current_user.id)
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    snapshot_result = await db.execute(
        select(UsageSnapshot)
        .where(UsageSnapshot.account_id == account_id)
        .order_by(UsageSnapshot.collected_at.desc(), UsageSnapshot.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    )
    snapshots = snapshot_result.scalars().all()
    if snapshots:
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
            total=len(items),
            items=items,
        )

    history_result = await db.execute(
        select(UsageHistory)
        .where(UsageHistory.account_id == account_id)
        .order_by(UsageHistory.recorded_at.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    )
    history_rows = history_result.scalars().all()
    items = [
        {
            "used": row.used,
            "total": row.total,
            "percent": row.percent,
            "expires_at": row.expires_at,
            "reset_hours": row.reset_hours,
            "reset_minutes": row.reset_minutes,
            "collected_at": row.recorded_at.isoformat() if row.recorded_at else None,
        }
        for row in history_rows
    ]
    return UsageHistoryResponse(
        source="usage_history",
        total=len(items),
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
    
    if not account.cookies_encrypted:
        raise HTTPException(status_code=400, detail="账号未配置 Cookie")
    
    # 解密 Cookie
    cookies = decrypt_data(account.cookies_encrypted)
    if not cookies:
        raise HTTPException(status_code=400, detail="Cookie 解密失败")
    
    # 根据服务类型调用不同的服务
    if account.service_id == "minimax":
        from services.minimax_service import MiniMaxService
        service = MiniMaxService()
        data = await service.get_usage(cookies=cookies, group_id=account.group_id)
    elif account.service_id == "xfyun":
        from services.xunfei_service import XunFeiService
        service = XunFeiService()
        data = await service.get_usage(cookies=cookies)
    else:
        raise HTTPException(status_code=400, detail="不支持的服务类型")
    
    try:
        page_info = await persist_usage_collection(db, account, data, write_history=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "message": "同步成功",
        "success": True,
        "usage": page_info
    }
