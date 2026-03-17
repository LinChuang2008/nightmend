"""
屏蔽规则 Schema (Suppression Rule Schemas)

定义屏蔽规则的请求和响应数据结构，用于 API 接口的数据验证和序列化。
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class SuppressionRuleBase(BaseModel):
    """屏蔽规则基础 Schema (Suppression Rule Base Schema)"""
    resource_type: str = Field(default="general", description="资源类型：host/service/alert_rule/log_keyword/general")
    resource_id: Optional[int] = Field(None, description="资源 ID（如 host_id, service_id）")
    resource_pattern: Optional[str] = Field(None, description="资源匹配模式（如日志关键词、服务名模式）")
    alert_rule_id: Optional[int] = Field(None, description="关联的告警规则 ID（可选）")

    start_time: Optional[datetime] = Field(None, description="屏蔽开始时间（为空则立即生效）")
    end_time: Optional[datetime] = Field(None, description="屏蔽结束时间（为空则永久屏蔽）")

    suppress_alerts: bool = Field(default=True, description="是否屏蔽告警创建")
    suppress_notifications: bool = Field(default=True, description="是否屏蔽通知发送")
    suppress_ai_analysis: bool = Field(default=True, description="是否屏蔽 AI 分析")
    suppress_log_scan: bool = Field(default=False, description="是否屏蔽日志异常扫描")

    reason: Optional[str] = Field(None, description="屏蔽原因")


class SuppressionRuleCreate(SuppressionRuleBase):
    """创建屏蔽规则请求 Schema (Create Suppression Rule Request Schema)"""
    pass


class SuppressionRuleUpdate(BaseModel):
    """更新屏蔽规则请求 Schema (Update Suppression Rule Request Schema)"""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    suppress_alerts: Optional[bool] = None
    suppress_notifications: Optional[bool] = None
    suppress_ai_analysis: Optional[bool] = None
    suppress_log_scan: Optional[bool] = None
    reason: Optional[str] = None
    is_active: Optional[bool] = None


class SuppressionRuleResponse(SuppressionRuleBase):
    """屏蔽规则响应 Schema (Suppression Rule Response Schema)"""
    id: int
    created_by: Optional[str] = None
    is_active: bool
    match_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SuppressionRuleListResponse(BaseModel):
    """屏蔽规则列表响应 Schema (Suppression Rule List Response Schema)"""
    items: List[SuppressionRuleResponse]
    total: int
    page: int
    page_size: int


class QuickSuppressRequest(BaseModel):
    """快速屏蔽请求 Schema (Quick Suppress Request Schema)

    用于快速创建屏蔽规则的简化请求，通常由前端"忽略"按钮触发。
    """
    resource_type: str = Field(..., description="资源类型：host/service")
    resource_id: int = Field(..., description="资源 ID")
    reason: Optional[str] = Field(None, description="屏蔽原因")
    duration_hours: Optional[float] = Field(None, description="屏蔽时长（小时），为空则永久屏蔽")
