"""
告警模型 (Alert Model)

定义告警规则和告警事件的表结构，支持指标告警、日志关键字告警和数据库告警。
包含告警规则的配置、触发条件、冷却期设置以及告警事件的生命周期管理。

Defines table structures for alert rules and alert events, supporting metric alerts,
log keyword alerts, and database alerts. Includes alert rule configuration,
trigger conditions, cooldown settings, and alert event lifecycle management.
"""
from datetime import datetime, time
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, Boolean, Text, JSON, Time, func, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AlertRule(Base):
    """
    告警规则表 (Alert Rule Table)
    
    定义各种类型的告警触发条件和配置，包括指标告警、日志关键字告警和数据库告警。
    支持复杂的过滤条件、冷却期设置和静默窗口配置，提供灵活的告警管理能力。
    
    Table for defining various types of alert trigger conditions and configurations,
    including metric alerts, log keyword alerts, and database alerts.
    Supports complex filtering, cooldown settings, and silence windows.
    """
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # 主键 ID (Primary Key ID)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # 告警规则名称 (Alert Rule Name)
    name_en: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 英文名称，用于 EN 语言模式 (English Name for EN locale)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 告警规则描述 (Alert Rule Description)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning")  # 严重程度：严重/警告/信息 (Severity: critical/warning/info)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)  # 监控指标名称，如 cpu_percent, memory_percent (Metric Name)
    operator: Mapped[str] = mapped_column(String(10), nullable=False, default=">")  # 比较操作符：>, <, >=, <=, ==, != (Comparison Operator)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)  # 触发阈值 (Trigger Threshold)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)  # 持续超过阈值的秒数 (Duration in Seconds)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否为系统内置规则 (Is Built-in Rule)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否启用该规则 (Is Rule Enabled)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, default="host")  # 目标类型：主机/服务 (Target Type: host/service)
    target_filter: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 目标过滤条件 JSON (Target Filter Conditions)
    # 日志关键字告警字段 (Log Keyword Alert Fields)
    rule_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="metric")  # 规则类型：指标/日志关键字/数据库 (Rule Type: metric/log_keyword/db_metric)
    log_keyword: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 日志关键字 (Log Keyword)
    log_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 日志级别 (Log Level)
    log_service: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 日志服务名称 (Log Service Name)
    # 数据库告警字段 (Database Alert Fields)
    db_metric_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 数据库指标名称 (Database Metric Name)
    db_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 数据库 ID (Database ID)
    # 冷却期与静默窗口 (Cooldown and Silence Window)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)  # 告警冷却期秒数 (Alert Cooldown Seconds)
    silence_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)  # 静默窗口开始时间 (Silence Window Start Time)
    silence_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)  # 静默窗口结束时间 (Silence Window End Time)
    # 通知渠道配置 (Notification Channels Configuration)
    notification_channel_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # 关联的通知渠道ID列表 (Associated Notification Channel IDs List)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 创建时间 (Creation Time)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )  # 更新时间 (Update Time)


class Alert(Base):
    """
    告警事件表 (Alert Event Table)
    
    记录由告警规则触发的具体告警事件，包含告警的完整生命周期信息。
    从触发到解决的整个过程，支持告警确认、自动修复等状态管理。
    
    Table for recording specific alert events triggered by alert rules,
    containing complete lifecycle information from trigger to resolution.
    Supports alert acknowledgment and automated remediation status management.
    """
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # 主键 ID (Primary Key ID)
    rule_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # 告警规则 ID (Alert Rule ID)
    host_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)  # 关联主机 ID (Related Host ID)
    service_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)  # 关联服务 ID (Related Service ID)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # 严重程度：严重/警告/信息 (Severity: critical/warning/info)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="firing")  # 状态：触发/解决/确认/已修复 (Status: firing/resolved/acknowledged/remediated)
    title: Mapped[str] = mapped_column(String(500), nullable=False)  # 告警标题 (Alert Title)
    title_en: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 英文告警标题 (English Alert Title)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 告警详细消息 (Alert Message)
    metric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 触发时的指标值 (Metric Value at Trigger)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 触发时的阈值 (Threshold at Trigger)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 告警触发时间 (Alert Fired Time)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # 告警解决时间 (Alert Resolved Time)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # 告警确认时间 (Alert Acknowledged Time)
    acknowledged_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 确认人用户 ID (Acknowledged by User ID)
    # 告警升级字段 (Alert Escalation Fields)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)  # 当前升级级别 (Current Escalation Level)
    last_escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # 最后升级时间 (Last Escalated Time)
    next_escalation_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # 下次升级时间 (Next Escalation Time)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 创建时间 (Creation Time)
