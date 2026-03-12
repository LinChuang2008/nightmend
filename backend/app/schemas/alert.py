"""
告警相关请求/响应模型

定义告警规则 CRUD 和告警事件查询的数据结构。
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


# ── 告警规则 ──

class AlertRuleCreate(BaseModel):
    """创建告警规则请求体。"""
    name: str
    description: Optional[str] = None
    severity: str = "warning"
    metric: str = ""
    operator: str = ">"
    threshold: float = 0
    duration_seconds: int = 300
    is_enabled: bool = True
    target_type: str = "host"
    target_filter: Optional[dict] = None
    rule_type: str = "metric"
    log_keyword: Optional[str] = None
    log_level: Optional[str] = None
    log_service: Optional[str] = None
    db_metric_name: Optional[str] = None
    db_id: Optional[int] = None
    cooldown_seconds: int = 300
    silence_start: Optional[str] = None
    silence_end: Optional[str] = None
    notification_channel_ids: Optional[List[int]] = None  # 关联的通知渠道ID列表


class AlertRuleUpdate(BaseModel):
    """更新告警规则请求体（所有字段可选）。"""
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    metric: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    duration_seconds: Optional[int] = None
    is_enabled: Optional[bool] = None
    target_filter: Optional[dict] = None
    rule_type: Optional[str] = None
    log_keyword: Optional[str] = None
    log_level: Optional[str] = None
    log_service: Optional[str] = None
    db_metric_name: Optional[str] = None
    db_id: Optional[int] = None
    cooldown_seconds: Optional[int] = None
    silence_start: Optional[str] = None
    silence_end: Optional[str] = None
    notification_channel_ids: Optional[List[int]] = None  # 关联的通知渠道ID列表


class AlertRuleResponse(BaseModel):
    """告警规则响应体。"""
    id: int
    name: str
    name_en: Optional[str] = None
    description: Optional[str]
    severity: str
    metric: str
    operator: str
    threshold: float
    duration_seconds: int
    is_builtin: bool
    is_enabled: bool
    target_type: str
    target_filter: Optional[dict]
    rule_type: Optional[str] = "metric"
    log_keyword: Optional[str] = None
    log_level: Optional[str] = None
    log_service: Optional[str] = None
    db_metric_name: Optional[str] = None
    db_id: Optional[int] = None
    cooldown_seconds: int = 300
    silence_start: Optional[str] = None
    silence_end: Optional[str] = None
    notification_channel_ids: Optional[List[int]] = None  # 关联的通知渠道ID列表
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── 告警事件 ──

class AlertResponse(BaseModel):
    """告警事件响应体。"""
    id: int
    rule_id: int
    host_id: Optional[int]
    service_id: Optional[int]
    severity: str
    status: str
    title: str
    title_en: Optional[str] = None
    message: Optional[str]
    metric_value: Optional[float]
    threshold: Optional[float]
    fired_at: datetime
    resolved_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[int]
    created_at: datetime
    remediation_status: Optional[str] = None  # 关联修复状态（来自 remediation_logs 表）

    model_config = {"from_attributes": True}
