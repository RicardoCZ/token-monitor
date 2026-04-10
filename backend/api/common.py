"""
Token Monitor - 通用 API 路由
状态检查、健康监控等通用接口
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.security import AuthContext, require_scope

router = APIRouter(prefix="/api", tags=["通用"])

# 与 frontend、backend 同级的 android-apk 目录，放置供下载的 .apk
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ANDROID_APK_DIR = _PROJECT_ROOT / "android-apk"


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "service": "token-monitor"}


@router.get("/latest-android-apk")
async def download_latest_android_apk():
    """
    下载 android-apk 目录下修改时间最新的 .apk（无需登录）。
    将构建产物放入与 frontend、backend 平级的 android-apk/ 即可。
    """
    if not ANDROID_APK_DIR.is_dir():
        raise HTTPException(status_code=404, detail="未找到 android-apk 目录（应与 frontend、backend 同级）")
    apks = [p for p in ANDROID_APK_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".apk"]
    if not apks:
        raise HTTPException(status_code=404, detail="android-apk 目录内暂无 .apk 文件")
    latest = max(apks, key=lambda p: p.stat().st_mtime)
    return FileResponse(
        path=str(latest),
        filename=latest.name,
        media_type="application/vnd.android.package-archive",
    )


@router.post("/clear-cache")
async def clear_cache(
    auth: AuthContext = Depends(require_scope("cookie:write")),
):
    """清除缓存（如果实现了缓存的话）"""
    return {"message": "Cache cleared", "success": True}
