"""
Token Monitor - 数据模型
使用 Pydantic 进行请求/响应数据验证
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any


# ============ MiniMax 相关模型 ============

class MiniMaxPageInfo(BaseModel):
    """MiniMax 页面信息"""
    used: float = 0
    total: float = 0
    percent: float = 0
    expiresAt: str = ""
    resetHours: int = 0
    resetMinutes: int = 0


class MiniMaxResponse(BaseModel):
    """MiniMax API 响应"""
    page_info: MiniMaxPageInfo
    models: Optional[Dict[str, Any]] = None


# ============ 讯飞相关模型 ============

class XunFeiPageInfo(BaseModel):
    """讯飞页面信息"""
    # 统一标准 key
    used: float = 0
    total: float = 0
    remain: float = 0
    percent: float = 0
    # 兼容旧 key（后续可移除）
    dailyQuota: float = 0
    dailyUsed: float = 0
    dailyRemain: float = 0
    expiresAt: str = ""


class XunFeiResponse(BaseModel):
    """讯飞 API 响应"""
    page_info: XunFeiPageInfo


# ============ 通用响应模型 ============

class StatusResponse(BaseModel):
    """状态查询响应"""
    minimax: Optional[MiniMaxPageInfo] = None
    xfyun: Optional[XunFeiPageInfo] = None
    status: str = "ok"


class SetCookieRequest(BaseModel):
    """设置 Cookie 请求"""
    service: str  # minimax / xfyun
    cookies: str


class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str
    success: bool


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    code: Optional[str] = None
