"""
Token Monitor - 认证 API 路由
用户注册、登录、邀请码管理
"""

import secrets
import string
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import get_db
from models.db_models import ApiKey, User, InviteCode
from core.api_keys import generate_api_key, get_api_key_prefix, hash_api_key
from core.config import settings
from core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    get_current_admin
)

router = APIRouter(prefix="/auth", tags=["认证"])


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


class SetupStatusResponse(BaseModel):
    """GET /auth/setup-status — 是否已有管理员（用于首次引导）"""
    hasAdmin: bool


class SetupFirstRequest(BaseModel):
    """POST /auth/setup-first — 仅无任何用户时可创建首个管理员"""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        import re

        if len(v) < 3:
            raise ValueError("用户名至少3字符")
        if len(v) > 20:
            raise ValueError("用户名最多20字符")
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]{2,19}$", v):
            raise ValueError("用户名只能包含字母、数字和下划线，且首字符须为字母")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        import re

        if len(v) < 8:
            raise ValueError("密码至少8位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码须包含大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码须包含小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码须包含数字")
        return v


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


class ApiKeyCreateRequest(BaseModel):
    name: str
    scopes: list[str] = []
    expires_at: Optional[datetime] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        value = (v or "").strip()
        if not value:
            raise ValueError("名称不能为空")
        if len(value) > 100:
            raise ValueError("名称长度不能超过 100")
        return value


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ApiKeyCreateResponse(ApiKeyResponse):
    api_key: str


def _parse_api_key_scopes(raw_scopes: str) -> list[str]:
    """解析 API Key scopes（JSON 文本 -> list[str]）"""
    if not raw_scopes:
        return []
    try:
        parsed = json.loads(raw_scopes)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        if isinstance(parsed, str):
            return [parsed]
        return []
    except json.JSONDecodeError:
        return []


def _normalize_scopes(scopes: list[str]) -> list[str]:
    """清洗 scopes，去重并保持稳定顺序"""
    normalized = []
    seen = set()
    for scope in scopes:
        item = (scope or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _to_api_key_response(row: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=_parse_api_key_scopes(row.scopes),
        is_active=row.is_active,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get_visible_api_key(
    api_key_id: int,
    current_user: User,
    db: AsyncSession,
) -> ApiKey:
    """获取当前用户可访问的 API Key（管理员可访问全部）"""
    result = await db.execute(select(ApiKey).where(ApiKey.id == api_key_id))
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    if current_user.role != "admin" and api_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该 API Key")

    return api_key


# ============ API 路由 ============

@router.get("/setup-status", response_model=SetupStatusResponse)
async def setup_status(db: AsyncSession = Depends(get_db)):
    """返回是否已有管理员账号（用于前端决定是否展示首次引导页）"""
    result = await db.execute(select(User.id).where(User.role == "admin").limit(1))
    has_admin = result.scalar_one_or_none() is not None
    return SetupStatusResponse(hasAdmin=has_admin)


@router.post("/setup-first", response_model=TokenResponse)
async def setup_first_admin(
    req: SetupFirstRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    仅在数据库中没有任何用户时创建首个管理员，并直接返回登录令牌。
    若已有任一用户或已有管理员，返回 400。
    """
    result = await db.execute(select(User.id).limit(1))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="系统已初始化，无法再次创建首个管理员",
        )

    user = User(
        username=req.username,
        password_hash=get_password_hash(req.password),
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(data={"sub": user.username})
    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


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


@router.delete("/invite-codes/{code}")
async def delete_invite_code(
    code: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    删除邀请码（仅管理员）
    删除后该邀请码立即失效且不可恢复。
    """
    normalized_code = (code or "").strip()
    if not normalized_code:
        raise HTTPException(status_code=400, detail="邀请码不能为空")

    result = await db.execute(
        select(InviteCode).where(InviteCode.code == normalized_code)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    await db.delete(invite)
    await db.commit()
    return {"success": True, "message": "邀请码已删除"}


@router.post("/invite-codes/{code}/delete")
async def delete_invite_code_compat(
    code: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    兼容删除入口（某些环境可能限制 DELETE 方法）。
    """
    normalized_code = (code or "").strip()
    if not normalized_code:
        raise HTTPException(status_code=400, detail="邀请码不能为空")

    result = await db.execute(
        select(InviteCode).where(InviteCode.code == normalized_code)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    await db.delete(invite)
    await db.commit()
    return {"success": True, "message": "邀请码已删除"}


@router.post("/api-keys", response_model=ApiKeyCreateResponse)
async def create_api_key(
    req: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建 API Key（明文仅本次返回）"""
    scopes = _normalize_scopes(req.scopes)

    # 极小概率哈希冲突时重试
    for _ in range(3):
        plain_key = generate_api_key()
        key_hash = hash_api_key(plain_key, pepper=settings.app_secret_key)
        key_prefix = get_api_key_prefix(plain_key)

        row = ApiKey(
            user_id=current_user.id,
            name=req.name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=json.dumps(scopes, ensure_ascii=False),
            is_active=True,
            expires_at=req.expires_at,
        )
        db.add(row)

        try:
            await db.commit()
            await db.refresh(row)
            data = _to_api_key_response(row).model_dump()
            data["api_key"] = plain_key
            return ApiKeyCreateResponse(**data)
        except Exception:
            await db.rollback()

    raise HTTPException(status_code=500, detail="创建 API Key 失败，请重试")


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出 API Key（不返回明文）"""
    query = select(ApiKey)
    if current_user.role != "admin":
        query = query.where(ApiKey.user_id == current_user.id)
    query = query.order_by(ApiKey.created_at.desc())

    result = await db.execute(query)
    rows = result.scalars().all()
    return [_to_api_key_response(row) for row in rows]


@router.delete("/api-keys/{api_key_id}")
async def revoke_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销 API Key（软删除：置为 inactive）"""
    row = await _get_visible_api_key(api_key_id, current_user, db)
    row.is_active = False
    await db.commit()
    return {"message": "API Key 已撤销", "success": True}


@router.post("/api-keys/{api_key_id}/rotate", response_model=ApiKeyCreateResponse)
async def rotate_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """轮换 API Key（返回新明文；旧明文立即失效）"""
    row = await _get_visible_api_key(api_key_id, current_user, db)

    for _ in range(3):
        plain_key = generate_api_key()
        key_hash = hash_api_key(plain_key, pepper=settings.app_secret_key)
        key_prefix = get_api_key_prefix(plain_key)

        row.key_hash = key_hash
        row.key_prefix = key_prefix
        row.is_active = True
        row.last_used_at = None

        try:
            await db.commit()
            await db.refresh(row)
            data = _to_api_key_response(row).model_dump()
            data["api_key"] = plain_key
            return ApiKeyCreateResponse(**data)
        except Exception:
            await db.rollback()

    raise HTTPException(status_code=500, detail="轮换 API Key 失败，请重试")
