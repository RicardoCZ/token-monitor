"""
Token Monitor - 讯飞 API 路由
讯飞星辰 MaaS 平台的专用接口
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import XunFeiResponse, MessageResponse
from models.database import get_db
from models.db_models import User, Account
from services.xunfei_service import XunFeiService
from core.security import get_current_user
from core.encryption import decrypt_data
from utils.usage_snapshot_writer import persist_usage_collection

router = APIRouter(prefix="/api/xfyun", tags=["讯飞"])


@router.get("/", response_model=XunFeiResponse)
async def get_xfyun_status(
    record: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取讯飞星辰 MaaS 用量状态
    
    Returns:
        讯飞平台的用量信息
    """
    # 查询用户的讯飞账号
    result = await db.execute(
        select(Account).where(
            and_(Account.user_id == current_user.id, Account.service_id == "xfyun")
        )
    )
    account = result.scalar_one_or_none()
    
    if not account or not account.cookies_encrypted:
        raise HTTPException(status_code=400, detail="请先设置讯飞 Cookie")
    
    # 解密 Cookie
    cookies = decrypt_data(account.cookies_encrypted)
    if not cookies:
        raise HTTPException(status_code=400, detail="Cookie 解密失败")
    
    # 调用服务
    service = XunFeiService()
    data = await service.get_usage(cookies=cookies)
    
    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"])

    if record:
        try:
            await persist_usage_collection(db, account, data, write_history=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    
    return data


@router.get("/cookie")
async def check_xfyun_cookie(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    检查讯飞 Cookie 是否配置
    
    Returns:
        Cookie 状态信息
    """
    result = await db.execute(
        select(Account).where(
            and_(Account.user_id == current_user.id, Account.service_id == "xfyun")
        )
    )
    account = result.scalar_one_or_none()
    
    if account and account.cookies_encrypted:
        return {"has_cookie": True, "message": "Cookie 已配置"}
    else:
        return {"has_cookie": False, "message": "Cookie 未配置"}
