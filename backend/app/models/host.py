"""
主机模型 (Host Model)

定义被监控主机的表结构，记录主机基本信息、硬件配置、Agent 状态和分组信息。
每个主机对应一个监控 Agent，通过心跳机制维持连接状态，支持灵活的标签和分组管理。

Defines the table structure for monitored hosts, recording basic host information,
hardware configuration, agent status, and grouping information. Each host corresponds
to a monitoring agent, maintaining connection status through heartbeat mechanism.
"""
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Host(Base):
    """
    主机表 (Host Table)
    
    存储系统中所有被监控服务器的基本信息、硬件配置和状态数据。
    每个主机通过 Agent 上报数据，支持灵活的标签管理和分组功能，为监控体系提供基础数据支撑。
    
    Table for storing basic information, hardware configuration, and status data
    of all monitored servers in the system. Each host reports data through an agent,
    supporting flexible tag management and grouping functions.
    """
    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # 主键 ID (Primary Key ID)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # 主机名称 (Hostname)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 自定义显示名称 (Custom Display Name)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IP 地址（支持 IPv6，保留兼容） (IP Address)
    private_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # 内网 IP 地址 (Private IP Address)
    public_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # 公网 IP 地址 (Public IP Address)
    os: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 操作系统类型 (Operating System)
    os_version: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 操作系统版本 (OS Version)
    arch: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 系统架构，如 x86_64, arm64 (System Architecture)
    cpu_cores: Mapped[int | None] = mapped_column(Integer, nullable=True)  # CPU 核心数 (CPU Cores)
    memory_total_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 总内存容量 MB (Total Memory in MB)
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Agent 版本号 (Agent Version)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="online")  # 在线状态：在线/离线 (Online Status: online/offline)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)  # 主机标签 JSON 数据 (Host Tags JSON)
    group_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 主机分组名称 (Host Group Name)
    network_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 网络接口详细信息 (Network Interfaces Info)
    agent_token_id: Mapped[int] = mapped_column(Integer, nullable=False)  # Agent 认证令牌 ID (Agent Token ID)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 最后心跳时间 (Last Heartbeat Time)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 创建时间 (Creation Time)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )  # 更新时间 (Update Time)

    @property
    def display_hostname(self) -> str:
        """获取显示名称（优先使用 display_name，否则使用 hostname）。"""
        return self.display_name or self.hostname

    @property
    def display_ip(self) -> str:
        """获取显示 IP（优先内网 IP，否则公网 IP，最后兼容旧字段）。"""
        return self.private_ip or self.ip_address or self.public_ip or "N/A"
