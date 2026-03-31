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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path

# 导入路由
from api import common, minimax, xfyun, cookie, cdp, auth, accounts

# 导入数据库
from models.database import init_db


# ============ 生命周期管理 ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的操作"""
    # 启动时：初始化数据库
    await init_db()
    print("✅ 数据库初始化完成")
    
    # 初始化默认服务数据
    from models.database import async_session_maker
    from models.db_models import Service
    from sqlalchemy import select
    
    async with async_session_maker() as db:
        # 检查是否已有服务数据
        result = await db.execute(select(Service))
        existing_services = result.scalars().all()
        if not existing_services:
            # 添加默认服务
            services = [
                Service(
                    id="minimax",
                    name="MiniMax",
                    icon="🍊",
                    login_url="https://platform.minimaxi.com/user-center/payment/token-plan",
                    cookie_domains="minimaxi.com,minimax.com"
                ),
                Service(
                    id="xfyun",
                    name="讯飞星辰",
                    icon="🔵",
                    login_url="https://maas.xfyun.cn/packageSubscription",
                    cookie_domains="xfyun.cn,xfyun.com"
                )
            ]
            db.add_all(services)
            await db.commit()
            print("✅ 默认服务数据初始化完成")
    
    yield
    
    # 关闭时的清理操作（如有需要）
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

# 账号管理接口
app.include_router(accounts.router)

# 通用接口
app.include_router(common.router)

# 平台专用接口
app.include_router(minimax.router)
app.include_router(xfyun.router)

# Cookie 管理接口
app.include_router(cookie.router)

# CDP 浏览器连接接口
app.include_router(cdp.router)

# ============ 静态文件服务 (保留原有功能) ============

from fastapi.staticfiles import StaticFiles
from pathlib import Path

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5188)
