"""
Token Monitor - MiniMax API 路由
MiniMax 平台的专用接口
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import MiniMaxResponse
from models.database import get_db
from models.db_models import User, Account
from services.minimax_service import MiniMaxService
from core.security import get_current_user
from core.encryption import decrypt_data
from utils.usage_snapshot_writer import persist_usage_collection

router = APIRouter(prefix="/api/minimax", tags=["MiniMax"])


@router.get("/", response_model=MiniMaxResponse)
async def get_minimax_status(
    record: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取 MiniMax 用量状态
    
    Returns:
        MiniMax 平台的用量信息
    """
    # 查询用户的 MiniMax 账号
    result = await db.execute(
        select(Account).where(
            and_(Account.user_id == current_user.id, Account.service_id == "minimax")
        )
    )
    account = result.scalar_one_or_none()
    
    if not account or not account.cookies_encrypted:
        raise HTTPException(status_code=400, detail="请先设置 MiniMax Cookie")
    
    # 解密 Cookie
    cookies = decrypt_data(account.cookies_encrypted)
    if not cookies:
        raise HTTPException(status_code=400, detail="Cookie 解密失败")
    
    # 调用服务
    service = MiniMaxService()
    data = await service.get_usage(
        cookies=cookies,
        group_id=account.group_id
    )
    
    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"])

    if record:
        try:
            await persist_usage_collection(db, account, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return data


@router.get("/cookie")
async def check_minimax_cookie(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    检查 MiniMax Cookie 是否配置
    
    Returns:
        Cookie 状态信息
    """
    result = await db.execute(
        select(Account).where(
            and_(Account.user_id == current_user.id, Account.service_id == "minimax")
        )
    )
    account = result.scalar_one_or_none()
    
    if account and account.cookies_encrypted:
        return {"has_cookie": True, "message": "Cookie 已配置"}
    else:
        return {"has_cookie": False, "message": "Cookie 未配置"}
