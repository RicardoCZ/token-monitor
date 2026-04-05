"""
Token Monitor - MiniMax 服务
MiniMax 平台的用量查询业务逻辑
"""

import json
import os
from typing import Optional

from .base_service import BaseHTTPService


from datetime import datetime, timezone

def _log(msg):
    """带时间戳的日志输出"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


class MiniMaxService(BaseHTTPService):
    """MiniMax 平台服务"""
    
    def __init__(self):
        super().__init__(timeout=10)
    
    async def get_usage(self, cookies: str = None, group_id: str = None) -> dict:
        """
        获取 MiniMax 用量
        
        Args:
            cookies: Cookie 字符串（必填，由账号库解密后传入）
            group_id: MiniMax GroupId；不传则根据 Cookie 向平台拉取
        
        Returns:
            包含 page_info 的响应字典
        """
        if not cookies:
            return {"error": "Cookie not found", "code": "NO_COOKIE"}
        
        # 获取 GroupId
        if not group_id:
            group_id = self._fetch_group_id(cookies)
        if not group_id:
            return {"error": "GroupId not found", "code": "NO_GROUP_ID"}
        
        # 调用 API
        url = "https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://platform.minimaxi.com/user-center/basic-info/interface-key"
        }
        params = {"group_id": group_id}
        
        try:
            resp = await self.async_get(url, cookies=cookies, headers=headers, params=params)
            data = json.loads(resp)
            parsed = self._parse_response(data)
            if "error" not in parsed and isinstance(parsed.get("page_info"), dict):
                expires = (parsed["page_info"].get("expiresAt") or "").strip()
                if not expires:
                    expires = self._fetch_subscription_expires_from_api(cookies, group_id)
                    if expires:
                        parsed["page_info"]["expiresAt"] = expires
            return parsed
        except Exception as e:
            return {"error": str(e), "code": "API_ERROR"}
    
    def _parse_response(self, data: dict) -> dict:
        """解析 API 响应"""
        try:
            base_resp = data.get("base_resp", {})
            
            if base_resp.get("status_code") != 0:
                return {"error": "API error: " + str(base_resp), "code": "API_ERROR"}
            
            model_remains = data.get("model_remains", [])
            
            # 找到 MiniMax-M* 模型
            main_model = None
            for m in model_remains:
                if m.get("model_name") == "MiniMax-M*":
                    main_model = m
                    break
            
            if not main_model:
                return {"error": "MiniMax-M* model not found", "code": "MODEL_NOT_FOUND"}
            
            total = main_model.get("current_interval_total_count", 0)
            # current_interval_usage_count 实际上是剩余次数，不是已用次数
            remain = main_model.get("current_interval_usage_count", 0)
            remains_time_ms = main_model.get("remains_time", 0)
            
            # 已使用 = 总量 - 剩余
            used = total - remain if total > 0 else 0
            percent = round((used / total) * 100, 1) if total > 0 else 0
            
            # remains_time 是毫秒，转换为小时+分钟
            remains_time_sec = remains_time_ms // 1000
            reset_hours = remains_time_sec // 3600
            reset_minutes = (remains_time_sec % 3600) // 60
            
            return {
                "page_info": {
                    "used": used,
                    "total": total,
                    "percent": percent,
                    # remains 接口中的 end_time 是额度窗口结束时间，不是订阅到期时间
                    "expiresAt": "",
                    "resetHours": reset_hours,
                    "resetMinutes": reset_minutes
                },
                "models": data
            }
        except Exception as e:
            return {"error": f"Parse error: {str(e)}", "code": "PARSE_ERROR"}

    def _normalize_expires_value(self, value) -> Optional[str]:
        """将多种日期/时间戳格式标准化为 'YYYY-MM-DD HH:MM:SS'。"""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            ts = float(value)
            # 毫秒级时间戳
            if ts > 10_000_000_000:
                ts = ts / 1000.0
            try:
                return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

        if not isinstance(value, str):
            return None

        text = value.strip()
        if not text:
            return None

        # 纯时间戳字符串
        if text.isdigit() and len(text) in (10, 13):
            return self._normalize_expires_value(int(text))

        # ISO8601 / 兼容格式
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

        # 常见日期字符串：YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]
        normalized = text.replace("/", "-")
        for fmt in (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%m-%d-%Y",
            "%m-%d-%Y %H:%M",
            "%m-%d-%Y %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(normalized, fmt)
                if fmt in ("%Y-%m-%d", "%m-%d-%Y"):
                    return dt.strftime("%Y-%m-%d")
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

        return None

    def _find_expires_in_payload(self, payload) -> Optional[str]:
        """在嵌套 JSON 中递归查找订阅到期相关字段。"""
        candidate_keys = {
            "expiresat",
            "expires_at",
            "expireat",
            "expire_at",
            "expiredat",
            "expired_at",
            "endtime",
            "end_time",
            "validuntil",
            "valid_until",
            "validto",
            "valid_to",
            "subscribe_end_time",
            "subscription_end_time",
            "current_subscribe_end_time",
            "current_credit_reload_time",
        }

        if isinstance(payload, dict):
            # 先检查当前层的候选字段
            for key, value in payload.items():
                key_normalized = str(key).strip().lower()
                if key_normalized in candidate_keys:
                    normalized = self._normalize_expires_value(value)
                    if normalized:
                        return normalized
            # 再递归检查子结构
            for value in payload.values():
                found = self._find_expires_in_payload(value)
                if found:
                    return found
            return None

        if isinstance(payload, list):
            for item in payload:
                found = self._find_expires_in_payload(item)
                if found:
                    return found
            return None

        return None

    def _extract_expires_from_remains_payload(self, data: dict, main_model: dict) -> Optional[str]:
        """优先从 remains 接口响应中提取到期时间。"""
        # 优先模型级字段
        expires = self._find_expires_in_payload(main_model)
        if expires:
            return expires

        # 兜底：全量 payload 递归查找
        return self._find_expires_in_payload(data)

    def _fetch_subscription_expires_from_api(self, cookies: str, group_id: str) -> str:
        """
        通过已确认接口获取 MiniMax 订阅到期时间。
        仅依赖 Cookie + GroupId，不依赖页面/CDP。
        """
        import httpx

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookies,
            "Referer": "https://platform.minimaxi.com/user-center/basic-info/interface-key"
        }

        try:
            combo_url = "https://www.minimaxi.com/v1/api/openplatform/charge/combo/cycle_audio_resource_package"
            resp = httpx.get(
                combo_url,
                headers=headers,
                params={
                    "biz_line": 2,
                    "cycle_type": 3,
                    "resource_package_type": 7,
                    "GroupId": group_id,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return ""

            payload = resp.json()
            current_subscribe = payload.get("current_subscribe", {})
            if not isinstance(current_subscribe, dict):
                return ""

            raw_end_time = current_subscribe.get("current_subscribe_end_time")
            normalized = self._normalize_expires_value(raw_end_time)
            return normalized or ""
        except Exception as e:
            _log(f"[MiniMax] 订阅到期时间获取失败: {e}")
            return ""
    
    def _fetch_group_id(self, cookies: str) -> str:
        """从 MiniMax API 获取用户的 GroupId"""
        import httpx
        import os
        
        # 清除代理环境变量，直连 MiniMax API
        old_proxy = {}
        for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            old_proxy[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]
        
        url = "https://www.minimaxi.com/v1/api/openplatform/current_user_info"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookies,
            "Referer": "https://platform.minimaxi.com/user-center/basic-info/interface-key"
        }
        
        try:
            _log(f"[MiniMax] 正在获取 GroupId, Cookie 长度: {len(cookies)}")
            resp = httpx.get(url, headers=headers, timeout=10)
            
            _log(f"[MiniMax] GroupId API 响应状态: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                _log(f"[MiniMax] GroupId API 响应: {data}")
                if data.get("base_resp", {}).get("status_code") == 0:
                    group_id = data.get("group_id", "")
                    _log(f"[MiniMax] 获取到 GroupId: {group_id}")
                    return group_id
                else:
                    _log(f"[MiniMax] API 返回错误: {data.get('base_resp')}")
            else:
                _log(f"[MiniMax] HTTP 错误: {resp.text[:200]}")
        except Exception as e:
            _log(f"获取 GroupId 失败: {e}")
        finally:
            # 恢复代理环境变量
            for var, val in old_proxy.items():
                if val:
                    os.environ[var] = val
        return ""
