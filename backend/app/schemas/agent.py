"""
Agent 接口请求/响应模型

定义 Agent 注册、心跳、指标上报等 API 的数据结构。
"""
from datetime import datetime
from pydantic import BaseModel


class AgentRegisterRequest(BaseModel):
    """Agent 注册请求体，包含主机基本信息。"""
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
    tags: dict | None = None
    group_name: str | None = None


class AgentRegisterResponse(BaseModel):
    """Agent 注册响应体。"""
    host_id: int
    hostname: str
    status: str
    created: bool  # True 表示新建，False 表示已存在

    model_config = {"from_attributes": True}


class AgentHeartbeatRequest(BaseModel):
    """Agent 心跳请求体。"""
    host_id: int


class AgentHeartbeatResponse(BaseModel):
    """Agent 心跳响应体。"""
    status: str
    server_time: datetime
    heartbeat_interval: int = 60  # 建议的心跳间隔（秒）


class MetricReport(BaseModel):
    """Agent 指标上报请求体，包含 CPU、内存、磁盘、网络等指标。"""
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
    timestamp: datetime | None = None
