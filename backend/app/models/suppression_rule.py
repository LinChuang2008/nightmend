"""
屏蔽规则模型 (Suppression Rule Model)

定义统一的屏蔽/忽略规则表结构，支持对各种监控维度的告警进行屏蔽。
包括主机指标、服务监控、日志异常、AI洞察等，实现精细化的告警控制。

Defines the table structure for unified suppression/ignore rules,
supporting alert suppression across various monitoring dimensions.
Including host metrics, service monitoring, log anomalies, AI insights, etc.
"""
from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SuppressionRule(Base):
    """
    屏蔽规则表 (Suppression Rule Table)

    存储各种监控维度的屏蔽/忽略规则，用于控制告警和通知的发送。
    支持按资源类型、资源ID、告警规则、时间范围等多维度配置。

    Table for storing suppression/ignore rules for various monitoring dimensions,
    used to control alert and notification delivery.
    Supports multi-dimensional configuration by resource type, ID, alert rule, time range, etc.
    """
    __tablename__ = "suppression_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 ID (Primary Key ID)

    # 资源类型和标识 (Resource Type and Identifier)
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        default="general"
    )  # 资源类型：host/service/alert_rule/log_keyword/general (Resource Type)
    resource_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 资源 ID（如 host_id, service_id） (Resource ID)
    resource_pattern: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # 资源匹配模式（如日志关键词、服务名模式） (Resource Pattern)

    # 告警规则关联 (Alert Rule Association)
    alert_rule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("alert_rules.id"), nullable=True
    )  # 关联的告警规则 ID（可选，为空则屏蔽所有规则） (Associated Alert Rule ID)

    # 时间范围 (Time Range)
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # 屏蔽开始时间（为空则立即生效） (Suppression Start Time)
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # 屏蔽结束时间（为空则永久屏蔽） (Suppression End Time)

    # 屏蔽范围配置 (Suppression Scope Configuration)
    suppress_alerts: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )  # 是否屏蔽告警创建 (Suppress Alert Creation)
    suppress_notifications: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )  # 是否屏蔽通知发送 (Suppress Notification Sending)
    suppress_ai_analysis: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )  # 是否屏蔽 AI 分析 (Suppress AI Analysis)
    suppress_log_scan: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # 是否屏蔽日志异常扫描 (Suppress Log Anomaly Scan)

    # 元数据 (Metadata)
    reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # 屏蔽原因 (Suppression Reason)
    created_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # 创建人（用户名） (Creator Username)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )  # 是否激活 (Is Active)
    match_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # 已匹配次数（用于统计） (Match Count)

    # 时间戳 (Timestamps)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 创建时间 (Creation Time)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )  # 更新时间 (Update Time)
