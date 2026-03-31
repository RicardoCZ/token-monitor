"""
Token Monitor - MiniMax 服务
MiniMax 平台的用量查询业务逻辑
"""

import json
import os
from pathlib import Path
from typing import Optional

import anyio
from dotenv import dotenv_values

from .base_service import BaseHTTPService


from datetime import datetime

def _log(msg):
    """带时间戳的日志输出"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def _cdp_host_port() -> tuple[str, int]:
    """
    读取 CDP 调试地址：优先使用 backend/.env 中非空项，再读 os.environ（避免空串占位导致 getenv 拿不到默认值）。
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    file_vals: dict = {}
    if env_path.is_file():
        file_vals = dotenv_values(env_path) or {}

    def _nonempty(v) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    host = _nonempty(file_vals.get("CDP_HOST"))
    if not host:
        host = _nonempty(os.environ.get("CDP_HOST")) or "127.0.0.1"

    port_raw = _nonempty(file_vals.get("CDP_PORT"))
    if not port_raw:
        port_raw = _nonempty(os.environ.get("CDP_PORT")) or "9223"
    try:
        port = int(port_raw)
    except ValueError:
        port = 9223
    return host, port


class MiniMaxService(BaseHTTPService):
    """MiniMax 平台服务"""
    
    def __init__(self):
        super().__init__(timeout=10)
        # 项目根目录是 backend 的上两级 (services/ -> backend/ -> new/)
        self.cookie_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "minimax_cookies.json"
        )
    
    def get_cookies(self) -> Optional[str]:
        """从文件读取 Cookie（兼容旧版本）"""
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, "r") as f:
                    data = json.load(f)
                return data.get("cookies", "")
            except:
                return None
        return None
    
    async def get_usage(self, cookies: str = None, group_id: str = None) -> dict:
        """
        获取 MiniMax 用量
        
        Args:
            cookies: Cookie 字符串，如果不传则从文件读取
            group_id: MiniMax GroupId，如果不传则从文件读取
        
        Returns:
            包含 page_info 的响应字典
        """
        # 获取 Cookie
        if not cookies:
            cookies = self.get_cookies()
        if not cookies:
            return {"error": "Cookie not found", "code": "NO_COOKIE"}
        
        # 获取 GroupId
        if not group_id:
            group_id = self._get_group_id(cookies)
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
                try:
                    # anyio 线程池与 uvicorn/async 主机兼容性优于 asyncio.to_thread（后者在部分环境下与子线程 CDP 行为不一致）
                    expires = await anyio.to_thread.run_sync(self.get_subscription_info)
                    if expires:
                        parsed["page_info"]["expiresAt"] = str(expires).strip()
                except Exception as ex:
                    _log(f"[MiniMax] CDP 订阅日期抓取跳过: {ex}")
            return parsed
        except Exception as e:
            return {"error": str(e), "code": "API_ERROR"}

    def get_subscription_info(self) -> str:
        """
        通过已连接的 Chrome CDP，在 MiniMax Token Plan 等页面提取「截止日期」，返回 YYYY-MM-DD；无法提取时返回 ""。
        """
        from services.cdp_service import cdp_service

        host, port = _cdp_host_port()
        try:
            targets = cdp_service.get_targets(host=host, port=port)
        except Exception as e:
            _log(f"[MiniMax] CDP get_targets 失败: {e}")
            return ""

        ws_url = self._pick_minimax_cdp_target(targets)
        if not ws_url:
            _log("[MiniMax] 未找到 MiniMax 相关调试页，跳过订阅截止日期")
            return ""

        try:
            return cdp_service.extract_minimax_subscription_expires(ws_url)
        except Exception as e:
            _log(f"[MiniMax] extract_minimax_subscription_expires: {e}")
            return ""

    def _pick_minimax_cdp_target(self, targets: list) -> Optional[str]:
        """选取最可能展示 Token Plan / 截止日期的 MiniMax 页面 WebSocket URL。"""
        path_hints = ("token-plan", "payment", "user-center", "minimaxi.com", "minimax.com")
        scored: list[tuple[int, str]] = []
        for t in targets:
            url = (t.get("url") or "").lower()
            ws = t.get("websocketUrl") or ""
            if not ws:
                continue
            if "minimaxi.com" not in url and "minimax.com" not in url:
                continue
            score = 0
            if "token-plan" in url or "/payment/" in url:
                score += 10
            for h in path_hints:
                if h in url:
                    score += 1
            scored.append((score, ws))
        if not scored:
            return None
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]
    
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
                    "expiresAt": "",
                    "resetHours": reset_hours,
                    "resetMinutes": reset_minutes
                },
                "models": data
            }
        except Exception as e:
            return {"error": f"Parse error: {str(e)}", "code": "PARSE_ERROR"}
    
    def _get_group_id(self, cookies: str = None) -> Optional[str]:
        """获取 GroupId，优先从文件读取，否则自动从 API 获取"""
        # 先尝试从文件读取
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, "r") as f:
                    data = json.load(f)
                group_id = data.get("group_id", "")
                if group_id:
                    return group_id
            except:
                pass
        
        # 文件没有或为空，自动从 API 获取
        if not cookies:
            cookies = self.get_cookies()
        if not cookies:
            return ""
        
        return self._fetch_group_id(cookies)
    
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
                    # 保存到文件
                    if group_id and os.path.exists(self.cookie_file):
                        with open(self.cookie_file, "r") as f:
                            file_data = json.load(f)
                        file_data["group_id"] = group_id
                        with open(self.cookie_file, "w") as f:
                            json.dump(file_data, f)
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
