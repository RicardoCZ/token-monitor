"""
Token Monitor - 讯飞服务
讯飞星辰 MaaS 平台的用量查询业务逻辑
"""

import json
import os
from typing import Optional
from .base_service import BaseHTTPService


class XunFeiService(BaseHTTPService):
    """讯飞星辰 MaaS 平台服务"""
    
    def __init__(self):
        super().__init__(timeout=10)
        # 项目根目录是 backend 的上两级 (services/ -> backend/ -> new/)
        self.cookie_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "xfyun_cookies.json"
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
    
    async def get_usage(self, cookies: str = None) -> dict:
        """
        获取讯飞用量
        
        Args:
            cookies: Cookie 字符串，如果不传则从文件读取
        
        Returns:
            包含 page_info 的响应字典
        """
        # 获取 Cookie
        if not cookies:
            cookies = self.get_cookies()
        if not cookies:
            return {"error": "Cookie not found", "code": "NO_COOKIE"}
        
        # 调用 API
        url = "https://maas.xfyun.cn/api/v1/gpt-finetune/coding-plan/list"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Cookie": cookies,
            "Referer": "https://maas.xfyun.cn/console/home"
        }
        
        try:
            resp = await self.async_get(url, cookies=cookies, headers=headers)
            data = json.loads(resp)
            return self._parse_response(data)
        except Exception as e:
            return {"error": str(e), "code": "API_ERROR"}
    
    def _parse_response(self, data: dict) -> dict:
        """解析 API 响应"""
        try:
            code = data.get("code", -1)
            if code != 0:
                return {"error": f"API error, code: {code}", "code": "API_ERROR"}
            
            rows = data.get("data", {}).get("rows", [])
            if not rows:
                return {"error": "No data found", "code": "NO_DATA"}
            
            # 取第一个（主要）的记录
            main_record = rows[0]
            usage_dto = main_record.get("codingPlanUsageDTO", {})
            
            raw_limit = usage_dto.get("dailyLimit", 0)  # 分
            raw_usage = usage_dto.get("dailyUsage", 0)  # 分
            
            # 计算（转换为人 民币分 to 万 tokens，假设比例是 1:1）
            total = raw_limit / 10000  # 转换为万
            used = raw_usage / 10000
            remain = max(0, total - used)
            percent = (used / total * 100) if total > 0 else 0
            
            # 到期时间
            expires_at = main_record.get("expiresAt", "")
            
            return {
                "page_info": {
                    "used": round(used, 2),
                    "total": round(total, 2),
                    "remain": round(remain, 2),
                    "percent": round(min(percent, 100), 1),
                    "expiresAt": expires_at
                },
                "percent": round(min(percent, 100), 1)
            }
        except Exception as e:
            return {"error": f"Parse error: {str(e)}", "code": "PARSE_ERROR"}
