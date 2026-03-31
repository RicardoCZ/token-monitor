"""
Token Monitor - 基础 HTTP 服务
封装异步 HTTP 请求逻辑
"""

import httpx
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from typing import Optional, Dict


class BaseHTTPService:
    """异步 HTTP 客户端封装"""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
    
    async def async_get(
        self,
        url: str,
        cookies: Optional[str] = None,
        headers: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> str:
        """
        异步 GET 请求
        
        Args:
            url: 请求 URL
            cookies: Cookie 字符串 (格式: "key1=value1; key2=value2")
            headers: 请求头
            params: URL 查询参数
        
        Returns:
            响应文本
        """
        cookie_dict = self._parse_cookies(cookies)
        
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(
                url,
                cookies=cookie_dict,
                headers=headers,
                params=params
            )
            response.raise_for_status()
            return response.text
    
    async def async_post(
        self,
        url: str,
        cookies: Optional[str] = None,
        headers: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> str:
        """
        异步 POST 请求
        
        Args:
            url: 请求 URL
            cookies: Cookie 字符串
            headers: 请求头
            json_data: JSON 请求体
        
        Returns:
            响应文本
        """
        cookie_dict = self._parse_cookies(cookies)
        
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.post(
                url,
                cookies=cookie_dict,
                headers=headers,
                json=json_data
            )
            response.raise_for_status()
            return response.text
    
    def _parse_cookies(self, cookies: Optional[str]) -> Dict[str, str]:
        """将 Cookie 字符串解析为字典"""
        cookie_dict = {}
        if cookies:
            for item in cookies.split(';'):
                if '=' in item:
                    key, value = item.strip().split('=', 1)
                    cookie_dict[key] = value
        return cookie_dict
