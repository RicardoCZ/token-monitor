"""
Token Monitor - Cookie 管理 API 路由
Cookie 的设置、读取、删除等接口
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.security import AuthContext, require_scope
from models.schemas import MessageResponse
import json
import os

router = APIRouter(prefix="/api/cookie", tags=["Cookie管理"])


class SetCookieRequest(BaseModel):
    """设置 Cookie 请求模型"""
    service: str  # minimax / xfyun
    cookies: str


def get_cookie_file(service: str) -> str:
    """获取 Cookie 文件路径
    
    统一使用项目根目录下的 data/ 目录
    路径: ~/share/new/data/{service}_cookies.json
    """
    # 从 api/cookie.py 向上跳 3 级到达项目根目录
    # api/ -> backend/ -> new/ -> data/
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data"
    )
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, f"{service}_cookies.json")


@router.post("/set", response_model=MessageResponse)
async def set_cookie(
    req: SetCookieRequest,
    auth: AuthContext = Depends(require_scope("cookie:write")),
):
    """
    设置 Cookie
    
    Args:
        service: 服务名称 (minimax / xfyun)
        cookies: Cookie 字符串
    
    Returns:
        操作结果
    """
    valid_services = ["minimax", "xfyun"]
    if req.service not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service. Must be one of: {valid_services}"
        )
    
    cookie_file = get_cookie_file(req.service)
    
    try:
        with open(cookie_file, "w") as f:
            json.dump({
                "service": req.service,
                "cookies": req.cookies
            }, f)
        
        return {"message": f"{req.service} Cookie 设置成功", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{service}", response_model=MessageResponse)
async def get_cookie(
    service: str,
    auth: AuthContext = Depends(require_scope("cookie:read")),
):
    """
    获取 Cookie 状态
    
    Args:
        service: 服务名称
    
    Returns:
        Cookie 是否已配置
    """
    valid_services = ["minimax", "xfyun"]
    if service not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service. Must be one of: {valid_services}"
        )
    
    cookie_file = get_cookie_file(service)
    
    if os.path.exists(cookie_file):
        with open(cookie_file, "r") as f:
            data = json.load(f)
            has_cookie = bool(data.get("cookies"))
        return {
            "message": f"{service} Cookie {'已配置' if has_cookie else '未配置'}",
            "success": has_cookie
        }
    else:
        return {"message": f"{service} Cookie 未配置", "success": False}


@router.delete("/{service}", response_model=MessageResponse)
async def delete_cookie(
    service: str,
    auth: AuthContext = Depends(require_scope("cookie:write")),
):
    """
    删除 Cookie
    
    Args:
        service: 服务名称
    
    Returns:
        操作结果
    """
    valid_services = ["minimax", "xfyun"]
    if service not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service. Must be one of: {valid_services}"
        )
    
    cookie_file = get_cookie_file(service)
    
    try:
        if os.path.exists(cookie_file):
            os.remove(cookie_file)
            return {"message": f"{service} Cookie 已删除", "success": True}
        else:
            return {"message": f"{service} Cookie 不存在", "success": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
