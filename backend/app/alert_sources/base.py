"""
告警源适配器基类 (Alert Source Adapter Base)

定义了所有告警源适配器必须实现的接口。
新增告警源只需继承 AlertSourceAdapter 并实现三个方法。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.host import Host
from app.remediation.models import RemediationAlert


class IncomingAlert(BaseModel):
    """外部告警系统传入的标准化告警结构"""
    source: str                                      # 告警源标识: "prometheus", "grafana", "pagerduty"
    external_id: str                                 # 去重 key (alertname + instance + starts_at)
    alertname: str                                   # 告警名称
    instance: str = ""                               # 主机标识 (IP:port 或 hostname)
    severity: str = "warning"                        # 严重程度
    status: str = "firing"                           # "firing" / "resolved"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ends_at: Optional[datetime] = None


class AlertGroup(BaseModel):
    """告警分组，用于因果链分析"""
    host: str
    root_cause: Optional[IncomingAlert] = None       # 根因告警
    alerts: list[IncomingAlert] = Field(default_factory=list)
    causal_chain: str = ""                           # AI 分析的因果链描述


class AlertSourceAdapter(ABC):
    """告警源适配器抽象基类

    实现三个方法即可接入新的告警源:
    1. parse()            — 解析原始 webhook payload
    2. map_to_host()      — 将告警中的主机标识映射到 VigilOps Host
    3. to_remediation_alert() — 转换为 RemediationAlert 供修复管道使用
    """

    @abstractmethod
    def parse(self, raw_payload: dict) -> list[IncomingAlert]:
        """解析原始 webhook payload 为标准化 IncomingAlert 列表。

        AlertManager 可能在一次 POST 中发送多个 alerts。
        """
        ...

    @abstractmethod
    async def map_to_host(self, alert: IncomingAlert, db: AsyncSession) -> Optional[Host]:
        """将告警中的主机标识（IP/hostname）映射到 VigilOps Host 记录。

        返回 None 表示未找到匹配的 Host。
        """
        ...

    @abstractmethod
    def to_remediation_alert(self, incoming: IncomingAlert, host: Host, alert_db_id: int) -> RemediationAlert:
        """将 IncomingAlert + Host 转换为 RemediationAgent 所需的 RemediationAlert。"""
        ...
