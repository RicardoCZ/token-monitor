"""
管理后台：平台用户列表与维护（角色、启用、重置密码）
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import get_current_admin, get_password_hash
from models.database import get_db
from models.db_models import User

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
    count_r = await db.execute(select(func.count()).select_from(User))
    total = int(count_r.scalar() or 0)
    r = await db.execute(
        select(User).order_by(User.id.asc()).offset(offset).limit(page_size)
    )
    rows = r.scalars().all()
    return AdminUserListResponse(
        items=[AdminUserRow.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/users/{user_id}")
async def admin_patch_user(
    user_id: int,
    body: AdminUserPatchRequest,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(User).where(User.id == user_id))
    target = r.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

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

    if "role" in fs:
        target.role = body.role
    if "is_active" in fs:
        target.is_active = bool(body.is_active)
    if body.new_password:
        target.password_hash = get_password_hash(body.new_password)

    await db.commit()
    return {"success": True, "message": "已更新用户"}
