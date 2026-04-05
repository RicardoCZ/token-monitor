"""告警通知渠道：合法取值与归一化（与前端、告警投递共用）"""

from __future__ import annotations

import json
from typing import Any

ALLOWED_NOTIFY_CHANNELS = frozenset({"log", "feishu", "qq"})


def normalize_notify_channels(raw: Any) -> list[str]:
    """返回去重后的渠道列表，非法项丢弃；空则默认为 log。"""
    items: list[str] = []
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
    elif isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    items = [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                items = [x.strip() for x in text.split(",") if x.strip()]
        else:
            items = [x.strip() for x in text.split(",") if x.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for c in items:
        k = c.lower()
        if k in ALLOWED_NOTIFY_CHANNELS and k not in seen:
            seen.add(k)
            out.append(k)
    return out if out else ["log"]
