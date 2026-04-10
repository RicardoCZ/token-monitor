"""
Token Monitor - 数据库配置
使用 SQLAlchemy 异步连接 MySQL
"""

import logging
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from core.config import settings

# 异步数据库连接 URL（密码中的 @ : / 等特殊字符须编码）
DATABASE_URL = (
    f"mysql+aiomysql://{quote_plus(settings.db_user)}:{quote_plus(settings.db_password)}"
    f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
)

# 创建异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=settings.debug,  # 开发模式打印 SQL
    pool_pre_ping=True,   # 连接池健康检查
    pool_size=5,
    max_overflow=10,
    connect_args={"init_command": "SET time_zone='+00:00'"},
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    """SQLAlchemy 基类"""
    pass


async def get_db() -> AsyncSession:
    """获取数据库会话（依赖注入）"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库（创建所有表；对已存在库做必须的列宽补丁）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不会加宽已有列；icon 已改为 URL 路径（如 /icons/minimax.ico），超出历史 VARCHAR(10)
        await conn.execute(
            text("ALTER TABLE services MODIFY COLUMN icon VARCHAR(128) NULL")
        )
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN notify_webhooks JSON NULL"))
        except Exception:
            pass
        try:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN token_version INT NOT NULL DEFAULT 0")
            )
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE alerts DROP COLUMN mute_reason"))
        except Exception:
            pass
        try:
            await conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN is_system_account TINYINT(1) NOT NULL DEFAULT 0"
                )
            )
        except Exception:
            pass
        # 尚无系统账号时，将 id 最小的管理员标为系统账号（与 setup-first 一致；避免复杂 UPDATE 在 MySQL 下失败却被静默吞掉）
        try:
            r = await conn.execute(
                text("SELECT COUNT(*) FROM users WHERE is_system_account = 1")
            )
            sys_count = int(r.scalar() or 0)
            if sys_count == 0:
                r2 = await conn.execute(
                    text("SELECT MIN(id) FROM users WHERE role = 'admin'")
                )
                mid = r2.scalar_one_or_none()
                if mid is not None:
                    await conn.execute(
                        text(
                            "UPDATE users SET is_system_account = 1 WHERE id = :mid AND role = 'admin'"
                        ),
                        {"mid": int(mid)},
                    )
        except Exception as e:
            logging.getLogger(__name__).warning(
                "is_system_account 回填失败（平台用户列表可能仍含系统管理员）: %s",
                e,
                exc_info=settings.debug,
            )
