"""
Token Monitor - 通用 API 路由
状态检查、健康监控等通用接口
"""

from fastapi import APIRouter, Depends
import sys
from pathlib import Path
import json
import os
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import StatusResponse, MessageResponse
from core.security import AuthContext, require_scope
from services.minimax_service import MiniMaxService
from services.xunfei_service import XunFeiService

router = APIRouter(prefix="/api", tags=["通用"])

# Cookie 文件目录（项目根目录下的 data/）
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data"
)


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """
    获取所有服务的状态和用量
    
    Returns:
        包含所有平台用量的状态响应
    """
    minimax_service = MiniMaxService()
    xunfei_service = XunFeiService()
    
    minimax_data = await minimax_service.get_usage()
    xunfei_data = await xunfei_service.get_usage()
    
    return {
        "minimax": minimax_data.get("page_info"),
        "xfyun": xunfei_data.get("page_info"),
        "status": "ok"
    }


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "service": "token-monitor"}


@router.post("/clear-cache")
async def clear_cache(
    auth: AuthContext = Depends(require_scope("cookie:write")),
):
    """清除缓存（如果实现了缓存的话）"""
    return {"message": "Cache cleared", "success": True}


@router.get("/current-cookies")
async def get_current_cookies(
    auth: AuthContext = Depends(require_scope("cookie:read")),
):
    """
    获取所有服务的 Cookie 配置状态
    
    Returns:
        各服务的 Cookie 配置状态（是否已配置、预览）
    """
    services = ["minimax", "xfyun"]
    result = {}
    
    for service in services:
        cookie_file = os.path.join(DATA_DIR, f"{service}_cookies.json")
        
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, "r") as f:
                    data = json.load(f)
                cookies = data.get("cookies", "")
                
                if cookies:
                    # 生成预览（前 50 个字符）
                    preview = cookies[:50] + "..." if len(cookies) > 50 else cookies
                    result[service] = {"has": True, "preview": preview}
                else:
                    result[service] = {"has": False, "preview": ""}
            except:
                result[service] = {"has": False, "preview": ""}
        else:
            result[service] = {"has": False, "preview": ""}
    
    return result
