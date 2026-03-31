"""
Token Monitor - CDP API 路由
通过 Chrome DevTools Protocol 连接浏览器并提取 Cookie
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from services.cdp_service import cdp_service

router = APIRouter(prefix="/api/cdp", tags=["CDP"])


class CDPConnectRequest(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9223


@router.post("/connect")
async def cdp_connect(req: CDPConnectRequest):
    """连接到 Chrome 调试浏览器"""
    # 保存连接参数到服务实例
    cdp_service.host = req.host
    cdp_service.port = req.port
    
    # 使用传入的 host 和 port 获取 targets
    targets = cdp_service.get_targets(host=req.host, port=req.port)
    
    if not targets:
        raise HTTPException(
            status_code=400,
            detail=f"无法连接到 Chrome ({req.host}:{req.port})，请确认 Chrome 已开启远程调试模式"
        )
    
    return {
        "success": True, 
        "message": f"已连接，找到 {len(targets)} 个页面",
        "targets": targets,
        "ws_url": targets[0].get("websocketUrl", "") if targets else ""
    }


@router.get("/targets")
async def cdp_get_targets():
    """获取可用页面列表（使用已保存的连接参数）"""
    targets = cdp_service.get_targets()
    
    return {
        "success": True,
        "targets": [
            {
                "id": t.get("id", ""),
                "title": t.get("title", "未知"),
                "url": t.get("url", ""),
                "type": t.get("type", "page")
            }
            for t in targets
        ]
    }


@router.get("/services")
async def cdp_get_services():
    """获取支持自动提取 Cookie 的服务列表"""
    return {
        "success": True,
        "services": [
            {
                "id": "minimax", 
                "name": "MiniMax", 
                "icon": "🍊",
                "domain": "minimaxi.com",
                "login_url": "https://platform.minimaxi.com/user-center/payment/token-plan",
                "cookie_domains": ["minimaxi.com", "minimax.com"]
            },
            {
                "id": "xfyun", 
                "name": "讯飞星辰", 
                "icon": "🔵",
                "domain": "xfyun.cn",
                "login_url": "https://maas.xfyun.cn/packageSubscription",
                "cookie_domains": ["xfyun.cn"]
            }
        ]
    }


@router.post("/get-cookies")
async def cdp_get_cookies(body: dict):
    """从指定页面获取 Cookie"""
    target_id = body.get("target_id", "")
    domain = body.get("domain", "")
    
    if not target_id:
        raise HTTPException(status_code=400, detail="需要 target_id")
    
    # 获取 targets
    targets = cdp_service.get_targets()
    target = None
    for t in targets:
        if t.get("id") == target_id:
            target = t
            break
    
    if not target:
        raise HTTPException(status_code=404, detail="未找到指定的页面")
    
    ws_url = target.get("websocketUrl", "")
    if not ws_url:
        raise HTTPException(status_code=400, detail="该页面不支持提取 Cookie")
    
    cookies = cdp_service.get_cookies_from_target(ws_url, domain)
    
    return {"success": True, "cookies": cookies}


@router.post("/get-page-info")
async def cdp_get_page_info(body: dict):
    """获取页面信息"""
    target_id = body.get("target_id", "")
    service_id = body.get("service_id", "")
    
    if not target_id:
        raise HTTPException(status_code=400, detail="需要 target_id")
    
    # 获取 targets
    targets = cdp_service.get_targets()
    target = None
    for t in targets:
        if t.get("id") == target_id:
            target = t
            break
    
    if not target:
        raise HTTPException(status_code=404, detail="未找到指定的页面")
    
    ws_url = target.get("websocketUrl", "")
    page_data = cdp_service.extract_page_data(ws_url)
    
    return {"success": True, "page_info": page_data}


@router.post("/extract")
async def cdp_extract_all(body: dict):
    """从指定页面提取所有信息（Cookie + 页面数据）"""
    target_id = body.get("target_id", "")
    service_id = body.get("service_id", "")
    domain = body.get("domain", "")
    
    if not target_id:
        raise HTTPException(status_code=400, detail="需要 target_id")
    
    # 获取 targets
    targets = cdp_service.get_targets()
    target = None
    for t in targets:
        if t.get("id") == target_id:
            target = t
            break
    
    if not target:
        raise HTTPException(status_code=404, detail="未找到指定的页面")
    
    ws_url = target.get("websocketUrl", "")
    if not ws_url:
        raise HTTPException(status_code=400, detail="该页面不支持提取 Cookie")
    
    cookies = cdp_service.get_cookies_from_target(ws_url, domain)
    page_data = cdp_service.extract_page_data(ws_url)
    
    if not cookies and not page_data.get("allText"):
        raise HTTPException(
            status_code=404,
            detail="未找到 Cookie 或页面数据，可能需要先登录"
        )
    
    return {
        "success": True,
        "cookies": cookies,
        "pageData": page_data,
        "url": target.get("url", "")
    }


@router.post("/disconnect")
async def cdp_disconnect():
    """断开 CDP 连接"""
    cdp_service.ws_url = None
    return {"success": True, "message": "已断开连接"}
