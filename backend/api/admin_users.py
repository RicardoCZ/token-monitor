"""
管理后台：平台用户列表与维护（角色、启用、重置密码）
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import delete as sql_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import get_current_admin, get_password_hash, verify_password
from models.database import get_db
from models.db_models import InviteCode, User

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


class AdminUserRow(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRow]
    total: int
    page: int
    page_size: int


class AdminUserPatchRequest(BaseModel):
    role: Optional[Literal["user", "admin"]] = None
    is_active: Optional[bool] = None
    new_password: Optional[str] = None
    # 重置他人密码时必填：当前登录管理员的密码（二次确认）
    actor_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if len(v) < 8:
            raise ValueError("密码至少8位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码须包含大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码须包含小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码须包含数字")
        return v


class AdminCreateUserRequest(BaseModel):
    """POST /api/admin/users — 管理员直接创建用户（无需邀请码），非系统账号"""

    username: str
    password: str
    role: Literal["user", "admin"] = "user"
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        s = (v or "").strip()
        if len(s) < 3:
            raise ValueError("用户名至少3字符")
        if len(s) > 20:
            raise ValueError("用户名最多20字符")
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]{2,19}$", s):
            raise ValueError("用户名只能包含字母、数字和下划线，且首字符须为字母")
        return s

    @field_validator("password")
    @classmethod
    def validate_password_create(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少8位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码须包含大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码须包含小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码须包含数字")
        return v


def _is_super_admin(user: User) -> bool:
    """系统账号（setup-first 首个管理员）：可创建/提拔其他管理员。"""
    return user.role == "admin" and bool(getattr(user, "is_system_account", False))


async def _active_admin_count(db: AsyncSession) -> int:
    r = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == "admin")
        .where(User.is_active.is_(True))
    )
    return int(r.scalar() or 0)


@router.get("/users", response_model=AdminUserListResponse)
async def admin_list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    not_system = User.is_system_account.is_(False)
    count_r = await db.execute(select(func.count()).select_from(User).where(not_system))
    total = int(count_r.scalar() or 0)
    r = await db.execute(
        select(User)
        .where(not_system)
        .order_by(User.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    rows = r.scalars().all()
    return AdminUserListResponse(
        items=[AdminUserRow.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=AdminUserRow)
async def admin_create_user(
    body: AdminCreateUserRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.role == "admin" and not _is_super_admin(current_admin):
        raise HTTPException(
            status_code=403,
            detail="仅超级管理员可创建管理员账号",
        )
    r = await db.execute(select(User).where(User.username == body.username))
    if r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=body.username,
        password_hash=get_password_hash(body.password),
        role=body.role,
        is_active=bool(body.is_active),
        is_system_account=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return AdminUserRow.model_validate(user)


@router.patch("/users/{user_id}")
async def admin_patch_user(
    user_id: int,
    body: AdminUserPatchRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(User).where(User.id == user_id))
    target = r.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    if target.is_system_account:
        raise HTTPException(
            status_code=403,
            detail="系统账号不可通过本接口修改角色、启用状态或密码；登录密码请在 Web 页顶栏点击用户名自助修改",
        )

    fs = body.model_fields_set
    if not fs:
        raise HTTPException(status_code=400, detail="无更新字段")

    active_admins = await _active_admin_count(db)

    if "is_active" in fs and body.is_active is False and target.role == "admin":
        if active_admins <= 1 and target.is_active:
            raise HTTPException(status_code=400, detail="不能禁用最后一个活跃管理员")

    if "role" in fs and body.role == "user" and target.role == "admin":
        if active_admins <= 1 and target.is_active:
            raise HTTPException(status_code=400, detail="不能将最后一个活跃管理员降级为普通用户")

    if "role" in fs and body.role == "admin" and target.role != "admin":
        if not _is_super_admin(current_admin):
            raise HTTPException(
                status_code=403,
                detail="仅超级管理员可将用户设为管理员",
            )

    if "role" in fs:
        target.role = body.role
    if "is_active" in fs:
        target.is_active = bool(body.is_active)
    if body.new_password:
        raw = (body.actor_password or "").strip()
        if not raw:
            raise HTTPException(
                status_code=400, detail="重置密码须填写当前登录账号的密码以确认"
            )
        if not verify_password(raw, current_admin.password_hash):
            raise HTTPException(status_code=400, detail="当前登录密码不正确")
        target.password_hash = get_password_hash(body.new_password)

    await db.commit()
    return {"success": True, "message": "已更新用户"}


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")

    r = await db.execute(select(User).where(User.id == user_id))
    target = r.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    if target.is_system_account:
        raise HTTPException(status_code=403, detail="系统账号不可删除")

    if target.role == "admin" and not _is_super_admin(current_admin):
        raise HTTPException(
            status_code=403,
            detail="仅超级管理员可删除管理员账号",
        )

    if target.role == "admin" and target.is_active:
        active_admins = await _active_admin_count(db)
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="不能删除最后一个活跃管理员")

    await db.execute(sql_delete(InviteCode).where(InviteCode.created_by == user_id))
    await db.delete(target)
    await db.commit()
    return {"success": True, "message": "已删除用户"}
