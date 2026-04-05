"""
Token Monitor - 数据库模型
定义用户、账号、用量历史等表结构
"""

from sqlalchemy import Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from models.database import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # admin / user
    is_active = Column(Boolean, default=True)
    # 告警外发 JSON：收件人 feishu_open_id、qq_openid；每人机器人 feishu_app_id/feishu_app_secret_enc、qq_bot_app_id/qq_bot_app_secret_enc
    notify_webhooks = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    invite_codes = relationship("InviteCode", back_populates="creator", foreign_keys="InviteCode.created_by")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")


class InviteCode(Base):
    """邀请码表"""
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False, index=True)  # TM-ABC123
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    max_uses = Column(Integer, default=1)  # 最大使用次数，0 表示无限
    used_count = Column(Integer, default=0)  # 已使用次数
    created_at = Column(DateTime, server_default=func.now())

    # 关联
    creator = relationship("User", back_populates="invite_codes", foreign_keys=[created_by])

    @property
    def is_used_up(self):
        """是否已用完"""
        if self.max_uses == 0:
            return False  # 无限次
        return self.used_count >= self.max_uses


class Service(Base):
    """服务/平台表"""
    __tablename__ = "services"

    id = Column(String(20), primary_key=True)  # minimax, xfyun
    name = Column(String(50), nullable=False)  # MiniMax, 讯飞星辰
    icon = Column(String(128))  # emoji 或静态路径，如 /icons/minimax.ico
    login_url = Column(String(255))
    cookie_domains = Column(String(255))  # 逗号分隔的域名列表
    adapter_key = Column(String(100))  # 服务适配器标识
    capabilities = Column(JSON)  # 服务能力声明
    metric_defs = Column(JSON)  # 指标定义
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    accounts = relationship("Account", back_populates="service", cascade="all, delete-orphan")


class Account(Base):
    """账号表（用户的服务账号）"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    service_id = Column(String(20), ForeignKey("services.id"), nullable=False)
    name = Column(String(50))  # 配置名称（如"工作号"）
    cookies_encrypted = Column(Text)  # 加密后的 Cookie
    group_id = Column(String(100))  # MiniMax 专用
    service_meta = Column(JSON)  # 服务扩展参数（通用）
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)  # 最后同步时间
    last_collect_status = Column(String(32))  # 最近采集状态
    last_collect_error = Column(Text)  # 最近采集错误
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    user = relationship("User", back_populates="accounts")
    service = relationship("Service", back_populates="accounts")
    usage_snapshots = relationship("UsageSnapshot", back_populates="account", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="account", cascade="all, delete-orphan")


class UsageSnapshot(Base):
    """标准化用量快照表（注册表重构）"""
    __tablename__ = "usage_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    service_id = Column(String(50), nullable=False, index=True)
    metric_key = Column(String(64), nullable=False, index=True)
    used_value = Column(Float)
    total_value = Column(Float)
    percent_value = Column(Float)
    expires_at = Column(DateTime)
    reset_at = Column(DateTime)
    raw_payload = Column(JSON)
    normalized_payload = Column(JSON)
    collected_at = Column(DateTime, server_default=func.now(), index=True)

    # 关联
    account = relationship("Account", back_populates="usage_snapshots")


class Alert(Base):
    """告警配置表"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    metric_key = Column(String(64), nullable=False, default="percent", index=True)
    threshold = Column(Float, default=80)  # 告警阈值（%）
    notify_channels = Column(String(255))  # 通知渠道（JSON）
    is_enabled = Column(Boolean, default=True)
    is_firing = Column(Boolean, default=False)  # 当前是否处于告警中
    last_triggered_at = Column(DateTime)
    last_recovered_at = Column(DateTime)
    muted_until = Column(DateTime, nullable=True)  # 静默截止（UTC naive），到期后自动恢复判定
    mute_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # 关联
    account = relationship("Account", back_populates="alerts")
    events = relationship("AlertEvent", back_populates="alert", cascade="all, delete-orphan")


class AlertEvent(Base):
    """告警事件表（P2-3）"""
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    service_id = Column(String(50), nullable=False, index=True)
    metric_key = Column(String(64), nullable=False, index=True)
    snapshot_id = Column(Integer, ForeignKey("usage_snapshots.id"), index=True)
    threshold_value = Column(Float, nullable=False)
    observed_percent = Column(Float)
    status = Column(String(16), nullable=False, default="triggered")  # triggered / recovered
    notify_channel = Column(String(64), nullable=False, default="log")
    message = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    # 关联
    alert = relationship("Alert", back_populates="events")


class ApiKey(Base):
    """API Key 表（仅存哈希，不存明文）"""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(32), nullable=False, index=True)
    key_hash = Column(String(255), nullable=False, unique=True)
    scopes = Column(Text, nullable=False, default="[]")  # JSON 字符串
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime)
    last_used_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    user = relationship("User", back_populates="api_keys")
