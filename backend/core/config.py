"""
Token Monitor - 配置管理
使用 Pydantic Settings 进行配置管理，支持 .env 文件

敏感信息（JWT、加密密钥、数据库密码等）不得硬编码在仓库中，
必须通过 backend/.env 或环境变量提供；复制 .env.example 后填写。
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 预留字段（当前代码未用作 HTTP 鉴权）；勿在仓库中写入真实 Key
    api_key: str = ""

    app_secret_key: str = Field(
        ...,
        min_length=16,
        description="Cookie 加密等；生成: python -c \"import secrets; print(secrets.token_urlsafe(32))\"",
    )
    jwt_secret_key: str = Field(
        ...,
        min_length=16,
        description="JWT 签名密钥，须为强随机字符串",
    )

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 天

    host: str = "0.0.0.0"
    port: int = 5188
    debug: bool = False

    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "token_monitor"
    db_user: str = "tm_user"
    db_password: str = Field(
        ...,
        min_length=1,
        description="MySQL 密码，仅放在 .env 中",
    )

    cookie_dir: str = "data"
    cache_ttl: int = 60  # 秒

    # 自动采集（P2-2）
    auto_collect_enabled: bool = True
    auto_collect_interval_seconds: int = 300
    auto_collect_max_concurrency: int = 3
    auto_collect_retry_attempts: int = 2
    auto_collect_retry_delay_seconds: float = 1.0

    # 告警评估（P2-3）
    alert_eval_enabled: bool = True
    alert_default_threshold: float = 80.0


settings = Settings()
