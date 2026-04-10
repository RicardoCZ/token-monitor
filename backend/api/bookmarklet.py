"""
书签（Bookmarklet）采集：用户在 MiniMax/讯飞已登录页执行书签，将 Cookie与页面文本 POST 到此；
设置页再轮询拉取并自动填充，无需 CDP/远程调试端口。
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.security import (
    create_access_token,
    get_current_user,
    jwt_payload_matches_user_token_version,
)
from models.database import get_db
from models.db_models import BookmarkletStash, User

router = APIRouter(prefix="/api/setup", tags=["Bookmarklet"])

BM_JWT_TYP = "bookmarklet_stash"
BM_TEXT_MAX = 400_000


class BookmarkletTokenResponse(BaseModel):
    token: str
    expires_in_sec: int = 900


class BookmarkletIngestBody(BaseModel):
    token: str
    cookies: str = ""
    local_storage: dict[str, Any] = Field(default_factory=dict)
    session_storage: dict[str, Any] = Field(default_factory=dict)
    page_url: str = ""
    page_title: str = ""
    body_text: str = ""


def _create_bookmarklet_token(user: User) -> str:
    ver = int(user.token_version or 0)
    return create_access_token(
        data={"sub": user.username, "tv": ver, "typ": BM_JWT_TYP},
        expires_delta=timedelta(minutes=15),
    )


async def _user_from_bookmarklet_token(token: str, db: AsyncSession) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    if payload.get("typ") != BM_JWT_TYP:
        raise HTTPException(status_code=401, detail="令牌类型错误")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="令牌无效")

    r = await db.execute(select(User).where(User.username == str(username)))
    user = r.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    if not jwt_payload_matches_user_token_version(payload, user):
        raise HTTPException(status_code=401, detail="令牌已失效，请在设置页重新生成书签")
    return user


def _detect_service_hint(page_url: str) -> str:
    u = (page_url or "").lower()
    if "minimaxi" in u or "minimax.com" in u or "minimax.io" in u:
        return "minimax"
    if "xfyun" in u:
        return "xfyun"
    return ""


def _parse_cookie_pairs(cookies: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (cookies or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, rest = part.partition("=")
        name = name.strip()
        if name:
            out[name] = rest.strip()
    return out


def _append_cookie_pair(cookies: str, name: str, value: str) -> str:
    pair = f"{name}={value}"
    base = (cookies or "").strip()
    if not base:
        return pair
    return f"{base}; {pair}"


def _try_json_obj(raw: str) -> Any | None:
    s = raw.strip()
    if len(s) < 2 or s[0] not in "{[":
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _hertz_session_from_obj(obj: Any, depth: int = 0) -> str | None:
    """在 JSON 结构中递归查找可能存放会话 id 的字段（站点若镜像到 localStorage 则可补全）。"""
    if depth > 24:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            kn = k.lower().replace("-", "_")
            if kn in ("hertz_session", "hertzsession") and isinstance(v, str) and v.strip():
                return v.strip()
            if "hertz" in kn and "session" in kn and isinstance(v, str) and v.strip():
                return v.strip()
            found = _hertz_session_from_obj(v, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _hertz_session_from_obj(item, depth + 1)
            if found:
                return found
    elif isinstance(obj, str):
        j = _try_json_obj(obj)
        if j is not None:
            return _hertz_session_from_obj(j, depth + 1)
    return None


def _hertz_session_from_kv_stores(*stores: dict[str, Any]) -> str | None:
    for store in stores:
        if not store:
            continue
        for raw in store.values():
            if not isinstance(raw, str) or not raw.strip():
                continue
            u = raw.strip()
            if u.upper().startswith("HERTZ-SESSION="):
                return u.split("=", 1)[1].strip().split(";", 1)[0].strip()
            m = re.search(r"(?i)hertz-session\s*[:=]\s*([^\s;,\"]+)", u)
            if m and m.group(1):
                return m.group(1).strip()
            found = _hertz_session_from_obj(u)
            if found:
                return found
    return None


def _augment_minimax_cookies_with_storages(
    cookies: str,
    local_storage: dict[str, Any],
    session_storage: dict[str, Any],
    page_url: str,
) -> str:
    """
    HERTZ-SESSION 常为 HttpOnly，document.cookie 拿不到；若页面把同源信息写在 storage JSON 里则尝试补全。
    """
    if _detect_service_hint(page_url or "") != "minimax":
        return cookies
    pairs = _parse_cookie_pairs(cookies)
    if (pairs.get("HERTZ-SESSION") or "").strip():
        return cookies
    found = _hertz_session_from_kv_stores(local_storage or {}, session_storage or {})
    if found:
        return _append_cookie_pair(cookies, "HERTZ-SESSION", found)
    return cookies


def _build_page_info(local_storage: dict[str, Any], body_text: str, page_url: str) -> dict[str, Any]:
    """从 localStorage 与页面正文提取与 CDP extract相近的 page_info 片段。"""
    out: dict[str, Any] = {}
    ud = local_storage.get("user_detail")
    if isinstance(ud, str) and ud.strip():
        try:
            j = json.loads(ud)
            groups = j.get("groups")
            if isinstance(groups, list) and len(groups) > 0:
                out["groupId"] = groups[0]
            if j.get("subject_id"):
                out["subject_id"] = j.get("subject_id")
        except (json.JSONDecodeError, TypeError):
            pass

    if not out.get("groupId") and page_url:
        m = re.search(r"groupId=([a-f0-9-]+)", page_url, re.I)
        if m:
            out["groupId"] = m.group(1)

    text = body_text or ""
    if "截止日期" in text:
        for line in text.splitlines():
            if "截止日期" in line:
                m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", line)
                if m:
                    out["expiresAt"] = m.group(1)
                break

    usage = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if usage:
        try:
            out["used"] = int(usage.group(1))
            out["total"] = int(usage.group(2))
        except ValueError:
            pass

    for line in text.splitlines():
        line = line.strip()
        if "重置时间" in line or "分钟" in line:
            mm = re.search(r"(\d+)\s*分钟", line)
            hh = re.search(r"(\d+)\s*小时", line)
            if mm:
                out["resetMinutes"] = int(mm.group(1))
            if hh:
                out["resetHours"] = int(hh.group(1))
            break

    return out


@router.post("/bookmarklet-token", response_model=BookmarkletTokenResponse)
async def bookmarklet_token(
    current_user: User = Depends(get_current_user),
):
    """已登录用户获取短时 JWT，嵌入书签用于 /bookmarklet-ingest。"""
    return BookmarkletTokenResponse(
        token=_create_bookmarklet_token(current_user),
        expires_in_sec=900,
    )


@router.post("/bookmarklet-ingest")
async def bookmarklet_ingest(
    body: BookmarkletIngestBody,
    db: AsyncSession = Depends(get_db),
):
    """
    由供应商页面上的书签调用；无需 Authorization 头，凭 body.token（短时 JWT）关联用户。
    依赖全局 CORS（如 allow_origins=*）以便从第三方域 POST。
    """
    user = await _user_from_bookmarklet_token(body.token.strip(), db)
    bt = body.body_text or ""
    if len(bt) > BM_TEXT_MAX:
        bt = bt[:BM_TEXT_MAX]

    page_info = _build_page_info(body.local_storage or {}, bt, body.page_url or "")
    service_hint = _detect_service_hint(body.page_url or "")
    cookies_out = _augment_minimax_cookies_with_storages(
        body.cookies or "",
        body.local_storage or {},
        body.session_storage or {},
        body.page_url or "",
    )

    payload = {
        "cookies": cookies_out,
        "local_storage": body.local_storage or {},
        "page_url": body.page_url or "",
        "page_title": body.page_title or "",
        "service_hint": service_hint,
        "page_info": page_info,
    }

    await db.execute(delete(BookmarkletStash).where(BookmarkletStash.user_id == user.id))
    db.add(BookmarkletStash(user_id=user.id, payload=payload))
    await db.commit()

    return {"ok": True, "message": "已保存，请回到凭证设置页点击「拉取采集结果」"}


@router.get("/bookmarklet-poll")
async def bookmarklet_poll(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """设置页拉取最近一次书签采集；成功后删除暂存（一次性）。"""
    r = await db.execute(
        select(BookmarkletStash)
        .where(BookmarkletStash.user_id == current_user.id)
        .order_by(BookmarkletStash.created_at.desc())
        .limit(1)
    )
    row = r.scalar_one_or_none()
    if not row:
        return {"ok": True, "has_data": False}

    data = dict(row.payload) if isinstance(row.payload, dict) else {}
    await db.execute(delete(BookmarkletStash).where(BookmarkletStash.id == row.id))
    await db.commit()

    return {
        "ok": True,
        "has_data": True,
        "service_hint": data.get("service_hint") or "",
        "cookies": data.get("cookies") or "",
        "page_info": data.get("page_info") or {},
        "page_url": data.get("page_url") or "",
        "page_title": data.get("page_title") or "",
    }
