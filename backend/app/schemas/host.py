"""
主机相关请求/响应模型

定义主机列表、详情、指标等 API 的数据结构。
"""
from datetime import datetime
from pydantic import BaseModel, field_validator


class HostUpdate(BaseModel):
    """主机更新请求体。"""
    display_name: str | None = None

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v: str | None) -> str | None:
        """验证显示名称不能为纯空格。"""
        if v is not None and v.strip() == '':
            raise ValueError('Display name cannot be empty or only spaces')
        return v.strip() if v else None


class HostResponse(BaseModel):
    """主机基本信息响应体。"""
    id: int
    hostname: str
    display_name: str | None = None
    ip_address: str | None = None
    private_ip: str | None = None
    public_ip: str | None = None
    network_info: dict | None = None
    os: str | None = None
    os_version: str | None = None
    arch: str | None = None
    cpu_cores: int | None = None
    memory_total_mb: int | None = None
    agent_version: str | None = None
    status: str
    tags: dict | None = None
    group_name: str | None = None
    last_heartbeat: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HostWithMetrics(HostResponse):
    """包含最新指标数据的主机响应体。"""
    latest_metrics: dict | None = None


class HostMetricResponse(BaseModel):
    """主机指标响应体。"""
    id: int
    host_id: int
    cpu_percent: float | None = None
    cpu_load_1: float | None = None
    cpu_load_5: float | None = None
    cpu_load_15: float | None = None
    memory_used_mb: int | None = None
    memory_percent: float | None = None
    disk_used_mb: int | None = None
    disk_total_mb: int | None = None
    disk_percent: float | None = None
    net_bytes_sent: int | None = None
    net_bytes_recv: int | None = None
    net_send_rate_kb: float | None = None
    net_recv_rate_kb: float | None = None
    net_packet_loss_rate: float | None = None
    recorded_at: datetime

    model_config = {"from_attributes": True}
