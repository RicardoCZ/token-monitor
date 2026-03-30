"""
Token Monitor - 认证 API 路由
用户注册、登录、邀请码管理
"""

import os
import secrets
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import get_db
from models.db_models import User, InviteCode
from core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    get_current_admin
)

router = APIRouter(prefix="/auth", tags=["认证"])

# 项目根目录下的 data/（与 backend 同级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ADMIN_SECRET_FILE = _PROJECT_ROOT / "data" / "admin_secret.txt"
_ADMIN_PASSWORD_MIN_LEN = 12


def _resolve_bootstrap_admin_password() -> tuple[str, str]:
    """
    解析首任管理员初始口令：ADMIN_PASSWORD 环境变量 > data/admin_secret.txt > 新生成并写入文件。
    返回 (plain_password, hint_message) — plain 仅用于写入密码哈希，绝不放进 API 响应。
    """
    env_pw = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    if env_pw:
        if len(env_pw) < _ADMIN_PASSWORD_MIN_LEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ADMIN_PASSWORD 长度至少 {_ADMIN_PASSWORD_MIN_LEN} 字符",
            )
        return (
            env_pw,
            "请使用环境变量 ADMIN_PASSWORD 中的口令登录，登录后请尽快修改密码。",
        )

    data_dir = _PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if _ADMIN_SECRET_FILE.exists():
        pw = _ADMIN_SECRET_FILE.read_text(encoding="utf-8").strip()
        if not pw:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="data/admin_secret.txt 为空，请删除后重试或设置 ADMIN_PASSWORD",
            )
        return (
            pw,
            "请从 data/admin_secret.txt 读取初始口令登录，登录后请尽快修改密码。",
        )

    pw = secrets.token_urlsafe(24)
    _ADMIN_SECRET_FILE.write_text(pw + "\n", encoding="utf-8")
    try:
        os.chmod(_ADMIN_SECRET_FILE, 0o600)
    except OSError:
        pass
    return (
        pw,
        "初始口令已写入 data/admin_secret.txt（未在响应中返回），请登录后尽快修改密码。",
    )


# ============ 请求/响应模型 ============

class RegisterRequest(BaseModel):
    username: str
    password: str
    invite_code: str

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        import re
        if len(v) < 3:
            raise ValueError('用户名至少3字符')
        if len(v) > 20:
            raise ValueError('用户名最多20字符')
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{2,19}$', v):
            raise ValueError('用户名只能包含字母、数字和下划线，且首字符须为字母')
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        import re
        if len(v) < 8:
            raise ValueError('密码至少8位')
        if not re.search(r'[A-Z]', v):
            raise ValueError('密码须包含大写字母')
        if not re.search(r'[a-z]', v):
            raise ValueError('密码须包含小写字母')
        if not re.search(r'\d', v):
            raise ValueError('密码须包含数字')
        return v

    @field_validator('invite_code')
    @classmethod
    def validate_invite_code(cls, v):
        s = (v or '').strip()
        if not s:
            raise ValueError('邀请码不能为空')
        return s.upper()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class InviteCodeCreate(BaseModel):
    max_uses: Optional[int] = 1  # 最大使用次数，None/0 表示无限


class InviteCodeResponse(BaseModel):
    code: str
    max_uses: int
    used_count: int
    remaining: int  # 剩余次数，-1 表示无限
    created_at: datetime


# ============ API 路由 ============

@router.post("/register", response_model=TokenResponse)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    用户注册（需要邀请码）
    """
    # 1. 验证邀请码
    result = await db.execute(
        select(InviteCode).where(InviteCode.code == req.invite_code)
    )
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邀请码无效"
        )
    
    if invite.is_used_up:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邀请码已用完"
        )
    
    # 2. 检查用户名是否已存在
    result = await db.execute(
        select(User).where(User.username == req.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 3. 创建用户
    user = User(
        username=req.username,
        password_hash=get_password_hash(req.password),
        role="user"
    )
    db.add(user)
    await db.flush()
    
    # 4. 增加邀请码使用次数
    invite.used_count += 1
    
    await db.commit()
    
    # 5. 生成 Token
    access_token = create_access_token(data={"sub": user.username})
    
    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username,
        role=user.role
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    用户登录
    """
    # 查询用户
    result = await db.execute(
        select(User).where(User.username == req.username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )
    
    # 生成 Token
    access_token = create_access_token(data={"sub": user.username})
    
    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username,
        role=user.role
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return current_user


@router.post("/invite-codes", response_model=InviteCodeResponse)
async def create_invite_code(
    req: InviteCodeCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    创建邀请码（仅管理员）
    """
    # 生成随机邀请码：TM-XXXXXXXX
    code_chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(code_chars) for _ in range(8))
    code = f"TM-{random_part}"
    
    # 使用次数
    max_uses = req.max_uses if req.max_uses else 0  # 0 表示无限
    
    invite = InviteCode(
        code=code,
        created_by=current_user.id,
        max_uses=max_uses
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    
    return InviteCodeResponse(
        code=invite.code,
        max_uses=invite.max_uses,
        used_count=invite.used_count,
        remaining=-1 if invite.max_uses == 0 else invite.max_uses - invite.used_count,
        created_at=invite.created_at
    )


@router.get("/invite-codes", response_model=list[InviteCodeResponse])
async def list_invite_codes(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    列出所有邀请码（仅管理员）
    """
    result = await db.execute(
        select(InviteCode).order_by(InviteCode.created_at.desc())
    )
    codes = result.scalars().all()
    
    return [
        InviteCodeResponse(
            code=c.code,
            max_uses=c.max_uses,
            used_count=c.used_count,
            remaining=-1 if c.max_uses == 0 else c.max_uses - c.used_count,
            created_at=c.created_at
        )
        for c in codes
    ]


@router.post("/create-admin")
async def create_first_admin(
    db: AsyncSession = Depends(get_db)
):
    """
    创建第一个管理员账号（仅在没有用户时可用）。
    初始口令：优先环境变量 ADMIN_PASSWORD；否则使用或生成 data/admin_secret.txt。
    响应中绝不包含明文密码。
    """
    # 检查是否已有用户
    result = await db.execute(select(User))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已存在用户，无法使用此接口"
        )

    plain_password, hint = _resolve_bootstrap_admin_password()

    admin = User(
        username="admin",
        password_hash=get_password_hash(plain_password),
        role="admin"
    )
    db.add(admin)
    await db.commit()

    return {
        "message": "管理员账号创建成功",
        "username": "admin",
        "password_hint": hint,
    }
