"""
Token Monitor - 通用 API 路由
状态检查、健康监控等通用接口
"""

from fastapi import APIRouter, Depends
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.security import AuthContext, require_scope

router = APIRouter(prefix="/api", tags=["通用"])


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
