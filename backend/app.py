#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Monitor Backend - FastAPI 版本 ✨
监控 MiniMax 和讯飞语音的 token 使用量

架构：分层 + 插件化
- 路由层: api/
- 服务层: services/
- 模型层: models/
- 核心层: core/

依赖: fastapi, uvicorn, httpx, pydantic, sqlalchemy, aiomysql
运行: uvicorn app:app --reload --host 0.0.0.0 --port 5188
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 导入路由
from api import common, minimax, xfyun, cdp, auth, accounts, services, admin_users, bookmarklet

# 导入数据库
from models.database import init_db
from core.config import settings
from services.account_collector import AccountAutoCollector
from utils.service_registry_seed import seed_service_registry


# ============ 生命周期管理 ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的操作"""
    collector: AccountAutoCollector | None = None

    # 启动时：初始化数据库
    await init_db()
    print("✅ 数据库初始化完成")

    # 初始化默认服务数据（增量幂等）
    from models.database import async_session_maker

    async with async_session_maker() as db:
        created, updated = await seed_service_registry(db)
        if created or updated:
            print(f"✅ 默认服务数据初始化完成（新增 {created}，补齐 {updated}）")
        else:
            print("ℹ️ 默认服务数据已是最新状态（无变更）")

    if settings.auto_collect_enabled:
        collector = AccountAutoCollector(
            session_factory=async_session_maker,
            interval_seconds=settings.auto_collect_interval_seconds,
            max_concurrency=settings.auto_collect_max_concurrency,
            retry_attempts=settings.auto_collect_retry_attempts,
            retry_delay_seconds=settings.auto_collect_retry_delay_seconds,
        )
        await collector.start()
    else:
        print("ℹ️ 自动采集任务已关闭（AUTO_COLLECT_ENABLED=false）")
    
    yield
    
    # 关闭时的清理操作（如有需要）
    if collector is not None:
        await collector.stop()
    print("👋 应用关闭")


# ============ FastAPI 应用初始化 ============

app = FastAPI(
    title="Token Monitor API",
    description="监控 MiniMax 和讯飞语音的 token 使用量",
    version="2.0.0",
    lifespan=lifespan
)

# ============ CORS 配置 ============
# 允许所有来源（生产环境应限制为具体域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ 页面路由 (必须在静态文件之前) ============
from fastapi.responses import RedirectResponse

@app.get("/setup")
async def redirect_to_setup():
    """将 /setup 重定向到 /setup.html"""
    return RedirectResponse(url="/setup.html")


@app.get("/first-setup")
async def redirect_to_first_setup():
    """首次创建管理员引导页"""
    return RedirectResponse(url="/first-setup.html")

# ============ 注册路由 ============

# 认证接口
app.include_router(auth.router)

app.include_router(admin_users.router)

# 账号管理接口
app.include_router(accounts.router)

# 通用接口
app.include_router(common.router)

# 服务注册表接口
app.include_router(services.router)

# 平台专用接口
app.include_router(minimax.router)
app.include_router(xfyun.router)

# CDP 浏览器连接接口
app.include_router(cdp.router)

# 书签采集（免 CDP）
app.include_router(bookmarklet.router)

# ============ 静态文件服务 (保留原有功能) ============

from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5188)
