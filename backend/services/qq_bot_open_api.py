"""
QQ 机器人 OpenAPI v2：单聊（C2C）发文本。
文档：https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/api-use.html
发送：https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/send-receive/send.html

access_token 按 (appId, clientSecret) 分桶缓存，支持每用户独立机器人。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional
from urllib.parse import quote

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_APP_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

_token_lock = asyncio.Lock()
_token_cache: dict[tuple[str, str], tuple[str, float]] = {}


def _openapi_base() -> bool:
    """是否使用沙箱 API 根路径（与 settings 一致；可按调用方扩展参数）。"""
    return bool(getattr(settings, "qq_bot_use_sandbox", False))


def _api_base_url() -> str:
    if _openapi_base():
        return "https://sandbox.api.sgroup.qq.com"
    return "https://api.sgroup.qq.com"


async def _fetch_access_token(
    client: httpx.AsyncClient,
    app_id: str,
    client_secret: str,
) -> tuple[Optional[str], float]:
    aid = (app_id or "").strip()
    sec = (client_secret or "").strip()
    if not aid or not sec:
        return None, 0.0
    try:
        resp = await client.post(
            _APP_TOKEN_URL,
            json={"appId": aid, "clientSecret": sec},
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(15.0),
        )
    except Exception as exc:
        logger.warning("QQ getAppAccessToken 请求异常: %s", exc, exc_info=False)
        return None, 0.0
    if resp.status_code >= 300:
        logger.warning(
            "QQ getAppAccessToken HTTP %s: %s",
            resp.status_code,
            (resp.text or "")[:500],
        )
        return None, 0.0
    try:
        data = resp.json()
    except Exception:
        logger.warning("QQ getAppAccessToken 响应非 JSON: %s", (resp.text or "")[:300])
        return None, 0.0
    token = data.get("access_token")
    if not isinstance(token, str) or not token.strip():
        logger.warning("QQ getAppAccessToken 无 access_token: %s", str(data)[:400])
        return None, 0.0
    raw_exp = data.get("expires_in", 7200)
    try:
        exp_sec = int(raw_exp) if not isinstance(raw_exp, int) else raw_exp
    except (TypeError, ValueError):
        exp_sec = 7200
    deadline = time.monotonic() + float(max(60, exp_sec))
    return token.strip(), deadline


async def get_access_token(
    client: httpx.AsyncClient,
    app_id: str,
    client_secret: str,
) -> Optional[str]:
    """按机器人应用维度缓存 access_token。"""
    aid = (app_id or "").strip()
    sec = (client_secret or "").strip()
    if not aid or not sec:
        return None
    key = (aid, sec)
    async with _token_lock:
        now = time.monotonic()
        entry = _token_cache.get(key)
        if entry is not None:
            tok, dl = entry
            if now < dl - 90.0:
                return tok
    token, deadline = await _fetch_access_token(client, aid, sec)
    async with _token_lock:
        if token:
            _token_cache[key] = (token, deadline)
        else:
            _token_cache.pop(key, None)
    return token


async def send_c2c_text(
    user_openid: str,
    text: str,
    *,
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
) -> bool:
    """
    POST /v2/users/{openid}/messages，msg_type=0 文本。
    须传入该用户机器人应用的 app_id 与 app_secret。
    注意：官方对单聊「主动消息」有频次与策略限制（见文档）。
    """
    oid = (user_openid or "").strip()
    if not oid:
        return False
    aid = (app_id or "").strip()
    sec = (app_secret or "").strip()
    if not aid or not sec:
        return False
    payload = {"content": text, "msg_type": 0}
    base = _api_base_url().rstrip("/")
    path_oid = quote(oid, safe="")
    url = f"{base}/v2/users/{path_oid}/messages"
    timeout = httpx.Timeout(20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        token = await get_access_token(client, aid, sec)
        if not token:
            logger.warning("QQ 单聊跳过：无法获取 access_token app_id=%s", aid[:8] if aid else "")
            return False
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
        }
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except Exception as exc:
            logger.warning("QQ 单聊请求异常: %s", exc, exc_info=False)
            return False
        if resp.status_code < 300:
            return True
        logger.warning(
            "QQ 单聊发送失败 HTTP %s: %s",
            resp.status_code,
            (resp.text or "")[:500],
        )
        return False
