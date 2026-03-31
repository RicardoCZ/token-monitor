"""
Token Monitor - 数据库模型
定义用户、账号、用量历史等表结构
"""

from sqlalchemy import Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey
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
    icon = Column(String(10))  # 🍊, 🔵
    login_url = Column(String(255))
    cookie_domains = Column(String(255))  # 逗号分隔的域名列表
    created_at = Column(DateTime, server_default=func.now())

    # 关联
    accounts = relationship("Account", back_populates="service", cascade="all, delete-orphan")


class Account(Base):
    """账号表（用户的服务账号）"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    service_id = Column(String(20), ForeignKey("services.id"), nullable=False)
    name = Column(String(100))  # 账号别名（如"工作号"）
    cookies_encrypted = Column(Text)  # 加密后的 Cookie
    group_id = Column(String(100))  # MiniMax 专用
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)  # 最后同步时间
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    user = relationship("User", back_populates="accounts")
    service = relationship("Service", back_populates="accounts")
    usage_history = relationship("UsageHistory", back_populates="account", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="account", cascade="all, delete-orphan")


class UsageHistory(Base):
    """用量历史表"""
    __tablename__ = "usage_history"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    used = Column(Float)  # 已用
    total = Column(Float)  # 总量
    percent = Column(Float)  # 百分比
    expires_at = Column(String(20))  # 截止日期
    reset_hours = Column(Integer)
    reset_minutes = Column(Integer)
    recorded_at = Column(DateTime, server_default=func.now(), index=True)

    # 关联
    account = relationship("Account", back_populates="usage_history")


class Alert(Base):
    """告警配置表"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    threshold = Column(Float, default=80)  # 告警阈值（%）
    notify_channels = Column(String(255))  # 通知渠道（JSON）
    is_enabled = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    # 关联
    account = relationship("Account", back_populates="alerts")


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
