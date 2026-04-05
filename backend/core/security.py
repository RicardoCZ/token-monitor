"""
Token Monitor - 安全模块
密码哈希、JWT 与 API Key 鉴权
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Set
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api_keys import get_api_key_prefix, verify_api_key
from core.config import settings
from models.database import get_db
from models.db_models import ApiKey, User

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 密码流（必填/可选 两种）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
oauth2_scheme_required = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=True)


@dataclass
class AuthContext:
    """统一身份上下文（JWT 用户或 API Key 调用）"""
    auth_type: str  # user / apikey
    user: User
    scopes: Set[str]
    api_key_id: Optional[int] = None


def _raise_unauthorized(detail: str = "无法验证凭据") -> None:
    """统一 401 响应"""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer, ApiKey"},
    )


def _raise_forbidden(detail: str = "权限不足") -> None:
    """统一 403 响应"""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT Token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.jwt_secret_key, 
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def create_user_access_token(user: User) -> str:
    """登录/注册用户访问令牌，含 tv 与库中 token_version 对齐（logout 递增后旧令牌失效）。"""
    ver = int(user.token_version or 0)
    return create_access_token(data={"sub": user.username, "tv": ver})


def jwt_payload_matches_user_token_version(payload: dict, user: User) -> bool:
    """校验 JWT 的 tv 是否与用户当前 token_version 一致；兼容无 tv 的旧令牌（仅当用户从未 logout 过）。"""
    claim = payload.get("tv")
    uver = int(user.token_version or 0)
    if claim is None:
        return uver == 0
    try:
        return int(claim) == uver
    except (TypeError, ValueError):
        return False


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT Token"""
    try:
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None


async def get_current_user(
    token: str = Depends(oauth2_scheme_required),
    db: AsyncSession = Depends(get_db)
) -> User:
    """获取当前用户（依赖注入）"""
    payload = decode_token(token)
    if payload is None:
        _raise_unauthorized()

    username: str = payload.get("sub")
    if username is None:
        _raise_unauthorized()

    # 查询用户
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        _raise_unauthorized()

    if not user.is_active:
        _raise_forbidden("用户已被禁用")

    if not jwt_payload_matches_user_token_version(payload, user):
        _raise_unauthorized("登录已失效，请重新登录")

    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """获取当前管理员用户（依赖注入）"""
    if current_user.role != "admin":
        _raise_forbidden("需要管理员权限")
    return current_user


def _extract_api_key(request: Request) -> Optional[str]:
    """解析请求中的 API Key（X-API-Key 或 Authorization: ApiKey xxx）"""
    x_api_key = request.headers.get("X-API-Key")
    if x_api_key:
        return x_api_key.strip()

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("ApiKey "):
        return authorization[7:].strip()

    return None


def _parse_scopes(raw_scopes: str) -> Set[str]:
    """将数据库中的 scopes 文本解析为集合"""
    if not raw_scopes:
        return set()
    try:
        parsed = json.loads(raw_scopes)
        if isinstance(parsed, list):
            return {str(item) for item in parsed}
        if isinstance(parsed, str):
            return {parsed}
        return set()
    except json.JSONDecodeError:
        return set()


async def get_auth_context(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """
    统一鉴权入口：
    1) 优先 Bearer JWT
    2) 否则尝试 API Key
    """
    if token:
        payload = decode_token(token)
        if payload is None:
            _raise_unauthorized()

        username: str = payload.get("sub")
        if not username:
            _raise_unauthorized()

        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None:
            _raise_unauthorized()
        if not user.is_active:
            _raise_forbidden("用户已被禁用")

        if not jwt_payload_matches_user_token_version(payload, user):
            _raise_unauthorized("登录已失效，请重新登录")

        # JWT 请求保持与现有行为一致：不做 scope 限制
        return AuthContext(auth_type="user", user=user, scopes={"*"})

    api_key_value = _extract_api_key(request)
    if not api_key_value:
        _raise_unauthorized()

    key_prefix = get_api_key_prefix(api_key_value)
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.key_prefix == key_prefix)
        .where(ApiKey.is_active.is_(True))
    )
    candidates = result.scalars().all()

    matched_key: Optional[ApiKey] = None
    for candidate in candidates:
        if verify_api_key(
            api_key_value,
            candidate.key_hash,
            pepper=settings.app_secret_key,
        ) or verify_api_key(api_key_value, candidate.key_hash):
            matched_key = candidate
            break

    if matched_key is None:
        _raise_unauthorized()

    if matched_key.expires_at and matched_key.expires_at <= datetime.utcnow():
        _raise_unauthorized("API Key 已过期")

    user_result = await db.execute(select(User).where(User.id == matched_key.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        _raise_unauthorized()
    if not user.is_active:
        _raise_forbidden("用户已被禁用")

    # 记录最后使用时间（最佳努力，不阻断主流程）
    try:
        matched_key.last_used_at = datetime.utcnow()
        await db.commit()
    except Exception:
        await db.rollback()

    return AuthContext(
        auth_type="apikey",
        user=user,
        scopes=_parse_scopes(matched_key.scopes),
        api_key_id=matched_key.id,
    )


def require_scope(scope: str) -> Callable:
    """API Key 请求的 scope 校验器（JWT 调用默认放行）"""

    async def _checker(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if auth.auth_type == "user":
            return auth
        if "*" in auth.scopes or scope in auth.scopes:
            return auth
        _raise_forbidden(f"缺少必要 scope: {scope}")

    return _checker
