"""
飞书开放平台私聊发文本：使用官方 lark-oapi（与开放平台示例一致）。
文档：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development

支持按 (app_id, app_secret) 缓存多个 Client，便于每用户自建应用凭证。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, CreateMessageResponse

from core.config import settings

logger = logging.getLogger(__name__)

_client_lock = threading.Lock()
_clients: dict[tuple[str, str, str], lark.Client] = {}


def _feishu_domain() -> str:
    base = (settings.feishu_open_api_base or "").strip().rstrip("/")
    return base if base else "https://open.feishu.cn"


def _get_client(app_id: str, app_secret: str) -> Optional[lark.Client]:
    aid = (app_id or "").strip()
    sec = (app_secret or "").strip()
    if not aid or not sec:
        return None
    domain = _feishu_domain()
    fp = (aid, sec, domain)
    with _client_lock:
        c = _clients.get(fp)
        if c is not None:
            return c
        c = (
            lark.Client.builder()
            .app_id(aid)
            .app_secret(sec)
            .domain(domain)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )
        _clients[fp] = c
        return c


def invalidate_feishu_client_cache() -> None:
    with _client_lock:
        _clients.clear()


def _send_text_sync(open_id: str, text: str, app_id: str, app_secret: str) -> bool:
    client = _get_client(app_id, app_secret)
    if client is None:
        return False

    content_json = json.dumps({"text": text}, ensure_ascii=False)
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("open_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(open_id.strip())
            .msg_type("text")
            .content(content_json)
            .build()
        )
        .build()
    )
    try:
        response: CreateMessageResponse = client.im.v1.message.create(request)
    except Exception as exc:
        logger.warning("飞书 lark-oapi 请求异常（网络/代理/SSL 等）: %s", exc, exc_info=False)
        return False

    if not response.success():
        raw_snip = ""
        try:
            if response.raw and response.raw.content:
                raw_snip = json.dumps(
                    json.loads(response.raw.content),
                    ensure_ascii=False,
                )[:800]
        except Exception:
            raw_snip = (
                str(response.raw.content)[:800] if response.raw and response.raw.content else ""
            )
        logger.warning(
            "飞书 lark-oapi 发消息失败 code=%s msg=%s log_id=%s resp=%s",
            response.code,
            response.msg,
            response.get_log_id(),
            raw_snip,
        )
        return False
    return True


async def send_text_to_feishu_open_id(
    open_id: str,
    text: str,
    *,
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
) -> bool:
    """发私聊文本；须传入该用户自建应用的 app_id 与 app_secret。"""
    aid = (app_id or "").strip()
    sec = (app_secret or "").strip()
    if not aid or not sec:
        return False
    return await asyncio.to_thread(_send_text_sync, open_id, text, aid, sec)
