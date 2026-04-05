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
from sqlalchemy.orm.attributes import flag_modified

from models.database import get_db
from models.db_models import ApiKey, InviteCode, User
from core.api_keys import generate_api_key, get_api_key_prefix, hash_api_key
from core.config import settings
from core.credential_crypto import encrypt_credential
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


class NotifyWebhooksPayload(BaseModel):
    """
    仅出现在 body 的字段会更新。
    App Secret 仅写入：不要在 GET 中回显；更新时若省略字段则不改密文，传 null 则清除密文。
    """

    qq_openid: Optional[str] = None
    feishu_open_id: Optional[str] = None
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    qq_bot_app_id: Optional[str] = None
    qq_bot_app_secret: Optional[str] = None


class NotifyWebhooksResponse(BaseModel):
    qq_openid: Optional[str] = None
    feishu_open_id: Optional[str] = None
    feishu_app_id: Optional[str] = None
    feishu_app_secret_configured: bool = False
    qq_bot_app_id: Optional[str] = None
    qq_bot_app_secret_configured: bool = False


_NOTIFY_WEBHOOKS_STORAGE_KEYS = frozenset(
    {
        "qq_openid",
        "feishu_open_id",
        "feishu_app_id",
        "feishu_app_secret_enc",
        "qq_bot_app_id",
        "qq_bot_app_secret_enc",
    }
)


def _coerce_notify_webhooks_storage_val(v: object) -> Optional[str]:
    """JSON 列中值可能非 str（驱动/历史数据）；统一成可入库的非空字符串。"""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, bytes):
        try:
            s = v.decode("utf-8").strip()
        except Exception:
            return None
        return s if s else None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not v.is_integer():
            return None
        return str(int(v))
    return None


def _normalize_qq_openid(value: Optional[str]) -> Optional[str]:
    """QQ 单聊用户 openid，来自官方机器人事件等；格式由平台分配，只做长度与空白校验。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return ""
    if len(s) > 128:
        raise HTTPException(status_code=400, detail="qq_openid 过长")
    if len(s) < 4:
        raise HTTPException(
            status_code=400,
            detail="qq_openid 过短，请从机器人事件或开放平台调试信息中复制完整 openid",
        )
    if any(c in s for c in (" ", "\n", "\r", "\t")):
        raise HTTPException(status_code=400, detail="qq_openid 不能包含空白字符")
    return s


def _normalize_feishu_open_id(value: Optional[str]) -> Optional[str]:
    """飞书用户 Open ID，用于应用机器人私聊；一般以 ou_ 开头。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return ""
    if len(s) > 128:
        raise HTTPException(status_code=400, detail="feishu_open_id 过长")
    if not s.startswith("ou_"):
        raise HTTPException(
            status_code=400,
            detail="feishu_open_id 须为飞书 Open ID（一般以 ou_ 开头），参见开放平台调试台复制成员 ID",
        )
    return s


def _normalize_feishu_app_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return ""
    if len(s) > 64:
        raise HTTPException(status_code=400, detail="feishu_app_id 过长")
    return s


def _normalize_qq_bot_app_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return ""
    if len(s) > 64:
        raise HTTPException(status_code=400, detail="qq_bot_app_id 过长")
    return s


def _clamp_integration_secret(plain: str, label: str) -> str:
    s = (plain or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail=f"{label} 不能为空")
    if len(s) > 512:
        raise HTTPException(status_code=400, detail=f"{label} 过长")
    return s


def _notify_response_from_raw(raw: dict) -> NotifyWebhooksResponse:
    def gs(key: str) -> Optional[str]:
        v = raw.get(key)
        return v if isinstance(v, str) else None

    fe = gs("feishu_app_secret_enc")
    qe = gs("qq_bot_app_secret_enc")
    return NotifyWebhooksResponse(
        qq_openid=gs("qq_openid"),
        feishu_open_id=gs("feishu_open_id"),
        feishu_app_id=gs("feishu_app_id"),
        feishu_app_secret_configured=bool(fe and fe.strip()),
        qq_bot_app_id=gs("qq_bot_app_id"),
        qq_bot_app_secret_configured=bool(qe and qe.strip()),
    )


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


_ALLOWED_API_KEY_SCOPES: tuple[str, ...] = ("cookie:read", "cookie:write")


def _normalize_scopes(scopes: list[str]) -> list[str]:
    """仅保留系统支持的 scope，固定为 read → write 顺序。"""
    allowed = set(_ALLOWED_API_KEY_SCOPES)
    picked: set[str] = set()
    for scope in scopes:
        item = (scope or "").strip()
        if item in allowed:
            picked.add(item)
    return [s for s in _ALLOWED_API_KEY_SCOPES if s in picked]


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


def _notify_webhooks_as_dict(raw: object) -> Optional[dict]:
    """
    MySQL JSON + 部分驱动下，列可能被读成 str；统一解析为 dict，避免 GET/合并失效导致前端回显为空。
    """
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


@router.get("/notify-webhooks", response_model=NotifyWebhooksResponse)
async def get_notify_webhooks(current_user: User = Depends(get_current_user)):
    """飞书/QQ 机器人：每人自用 AppId + 密文 Secret；Open ID / openid 收件人。"""
    raw = _notify_webhooks_as_dict(current_user.notify_webhooks)
    if not raw:
        return NotifyWebhooksResponse()
    return _notify_response_from_raw(raw)


@router.put("/notify-webhooks", response_model=NotifyWebhooksResponse)
async def put_notify_webhooks(
    body: NotifyWebhooksPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新每人自用飞书/QQ 机器人凭证（Secret 加密存储）及收件人 ID。"""
    raw: dict[str, str] = {}
    prev = _notify_webhooks_as_dict(current_user.notify_webhooks)
    # 勿用 `if prev:`：空 dict 在 Python 中为假，会跳过合并导致已有密文丢失。
    if isinstance(prev, dict):
        for k, v in prev.items():
            if k not in _NOTIFY_WEBHOOKS_STORAGE_KEYS:
                continue
            coerced = _coerce_notify_webhooks_storage_val(v)
            if coerced:
                raw[k] = coerced

    fs = body.model_fields_set
    if "qq_openid" in fs:
        if body.qq_openid is None:
            raw.pop("qq_openid", None)
        else:
            u = _normalize_qq_openid(body.qq_openid)
            if u == "":
                raw.pop("qq_openid", None)
            elif u is not None:
                raw["qq_openid"] = u
    if "feishu_open_id" in fs:
        if body.feishu_open_id is None:
            raw.pop("feishu_open_id", None)
        else:
            u = _normalize_feishu_open_id(body.feishu_open_id)
            if u == "":
                raw.pop("feishu_open_id", None)
            elif u is not None:
                raw["feishu_open_id"] = u
    if "feishu_app_id" in fs:
        if body.feishu_app_id is None:
            raw.pop("feishu_app_id", None)
            raw.pop("feishu_app_secret_enc", None)
        else:
            u = _normalize_feishu_app_id(body.feishu_app_id)
            if u == "":
                raw.pop("feishu_app_id", None)
                raw.pop("feishu_app_secret_enc", None)
            elif u is not None:
                raw["feishu_app_id"] = u
    if "feishu_app_secret" in fs:
        if body.feishu_app_secret is None:
            raw.pop("feishu_app_secret_enc", None)
        elif (body.feishu_app_secret or "").strip():
            plain = _clamp_integration_secret(body.feishu_app_secret, "feishu_app_secret")
            try:
                raw["feishu_app_secret_enc"] = encrypt_credential(plain)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="飞书 App Secret 无法加密存储",
                ) from None
    if "qq_bot_app_id" in fs:
        if body.qq_bot_app_id is None:
            raw.pop("qq_bot_app_id", None)
            raw.pop("qq_bot_app_secret_enc", None)
        else:
            u = _normalize_qq_bot_app_id(body.qq_bot_app_id)
            if u == "":
                raw.pop("qq_bot_app_id", None)
                raw.pop("qq_bot_app_secret_enc", None)
            elif u is not None:
                raw["qq_bot_app_id"] = u
    if "qq_bot_app_secret" in fs:
        if body.qq_bot_app_secret is None:
            raw.pop("qq_bot_app_secret_enc", None)
        elif (body.qq_bot_app_secret or "").strip():
            plain = _clamp_integration_secret(body.qq_bot_app_secret, "qq_bot_app_secret")
            try:
                raw["qq_bot_app_secret_enc"] = encrypt_credential(plain)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="QQ App Secret 无法加密存储",
                ) from None

    current_user.notify_webhooks = raw if raw else None
    flag_modified(current_user, "notify_webhooks")
    await db.commit()
    await db.refresh(current_user)
    stored = _notify_webhooks_as_dict(current_user.notify_webhooks)
    if not isinstance(stored, dict):
        stored = {}
    return _notify_response_from_raw(stored)


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
    if not scopes:
        raise HTTPException(status_code=400, detail="请至少选择一个权限范围")

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


@router.delete("/api-keys/{api_key_id}/permanent")
async def delete_api_key_permanent(
    api_key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """永久删除 API Key 记录（不可恢复）"""
    row = await _get_visible_api_key(api_key_id, current_user, db)
    await db.delete(row)
    await db.commit()
    return {"message": "接口密钥已删除", "success": True}


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
