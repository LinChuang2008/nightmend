"""
用户模型 (User Model)

定义系统用户表结构，包括邮箱、密码哈希、角色权限等字段。
为系统提供用户认证、权限管理和账户管理功能。

Defines the system user table structure, including email, password hash,
role permissions, and other fields. Provides user authentication,
permission management, and account management functions for the system.
"""
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    """
    用户表 (User Table)
    
    存储系统中所有用户的账户信息，包括登录凭证、角色权限和基本资料。
    支持基于角色的访问控制（RBAC），为系统安全和用户管理提供基础数据。
    
    Table for storing account information for all users in the system,
    including login credentials, role permissions, and basic profile data.
    Supports Role-Based Access Control (RBAC) for system security and user management.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # 主键 ID (Primary Key ID)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)  # 用户邮箱（登录名） (User Email, Login Name)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 用户姓名 (User Name)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)  # 哈希后的密码 (Hashed Password)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # 用户角色：管理员/普通用户 (User Role: admin/user)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 账户是否激活 (Account Active Status)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 账户创建时间 (Account Creation Time)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )  # 账户更新时间 (Account Update Time)

    # 关联关系 (Relationships)
    dashboard_layouts = relationship("DashboardLayout", back_populates="user", cascade="all, delete-orphan")
    ai_feedback = relationship("AIFeedback", back_populates="user", cascade="all, delete-orphan")
