"""
数据模型包 (Data Models Package)

集中导出所有 SQLAlchemy ORM 模型，为 VigilOps 运维监控平台提供完整的数据模型定义。
包含用户管理、主机监控、服务检查、告警通知、AI 分析等各个功能模块的数据结构。

Centrally exports all SQLAlchemy ORM models, providing complete data model definitions
for the VigilOps operations monitoring platform. Includes data structures for
user management, host monitoring, service checking, alert notifications, AI analysis, and other modules.
"""
from app.models.user import User
from app.models.agent_token import AgentToken
from app.models.host import Host
from app.models.host_metric import HostMetric
from app.models.service import Service, ServiceCheck
from app.models.alert import Alert, AlertRule
from app.models.notification import NotificationChannel, NotificationLog
from app.models.notification_template import NotificationTemplate
from app.models.setting import Setting
from app.models.log_entry import LogEntry
from app.models.db_metric import MonitoredDatabase, DbMetric
from app.models.ai_insight import AIInsight
from app.models.audit_log import AuditLog
from app.models.report import Report
from app.models.service_dependency import ServiceDependency
from app.models.sla import SLARule, SLAViolation
from app.models.server import Server
from app.models.service_group import ServiceGroup
from app.models.server_service import ServerService
from app.models.nginx_upstream import NginxUpstream
from app.models.dashboard_config import DashboardLayout, DashboardComponent
from app.models.ai_feedback import AIFeedback, AIFeedbackSummary
from app.models.topology_layout import TopologyLayout

# 导出所有模型类供外部模块使用 (Export all model classes for external modules)
__all__ = [
    "User", "AgentToken", "Host", "HostMetric", "Service", "ServiceCheck",
    "Alert", "AlertRule", "NotificationChannel", "NotificationLog",
    "NotificationTemplate", "Setting", "LogEntry", "MonitoredDatabase",
    "DbMetric", "AIInsight", "AuditLog", "Report", "ServiceDependency",
    "SLARule", "SLAViolation", "Server", "ServiceGroup", "ServerService",
    "NginxUpstream", "DashboardLayout", "DashboardComponent", "AIFeedback", "AIFeedbackSummary",
    "TopologyLayout",
]
