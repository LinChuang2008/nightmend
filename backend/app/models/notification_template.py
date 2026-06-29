"""
通知模板模型 (Notification Template Model)

定义通知模板表结构，支持不同渠道类型的消息模板管理和变量替换。
为告警通知、报告推送等场景提供灵活的消息格式定制能力，支持多种通知渠道。

Defines the notification template table structure, supporting message template management
and variable substitution for different channel types. Provides flexible message format
customization capabilities for alert notifications, report push, and other scenarios.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationTemplate(Base):
    """
    通知模板表 (Notification Template Table)
    
    存储各种通知渠道的消息模板，支持变量替换和自定义格式。
    为系统的通知功能提供灵活的模板管理，支持钉钉、飞书、企微、邮件、Webhook 等多种渠道。
    
    Table for storing message templates for various notification channels,
    supporting variable substitution and custom formats. Provides flexible template
    management for system notification functions across multiple channels.
    """
    __tablename__ = "notification_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # 主键 ID (Primary Key ID)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="模板名称")
    channel_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="渠道类型: webhook/email/dingtalk/feishu/wecom/all"
    )
    subject_template: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="邮件标题模板（仅 email 使用）"
    )
    body_template: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息体模板，支持变量 {title} {severity} {message} 等"
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否为默认模板")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 创建时间 (Creation Time)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )  # 更新时间 (Update Time)
