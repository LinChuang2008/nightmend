"""
Agent 配置加载模块。

定义所有配置数据类，并从 YAML 文件加载配置。
支持环境变量覆盖（如 NIGHTMEND_TOKEN）和时间间隔简写（如 '15s'、'1m'）。
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class ServerConfig:
    """服务端连接配置。"""
    url: str = "http://localhost:8001"
    token: str = ""


@dataclass
class HostConfig:
    """主机标识配置。"""
    name: str = ""
    display_name: str = ""  # 自定义显示名称
    ip: str = ""  # 手动指定 IP（留空则自动检测）
    private_ip: str = ""  # 手动指定内网 IP
    public_ip: str = ""  # 手动指定公网 IP
    tags: List[str] = field(default_factory=list)


@dataclass
class MetricsConfig:
    """指标采集配置。"""
    interval: int = 15  # 采集间隔（秒）


@dataclass
class ServiceCheckConfig:
    """服务健康检查配置。"""
    name: str = ""
    type: str = "http"  # 检查类型：http / tcp
    url: str = ""
    host: str = ""
    port: int = 0
    interval: int = 30  # 检查间隔（秒）
    timeout: int = 10


@dataclass
class LogSourceConfig:
    """日志源配置。"""
    path: str = ""           # 日志文件路径，如 /var/log/app.log
    service: str = ""        # 服务名
    multiline: bool = False  # 是否启用多行合并
    multiline_pattern: str = "^\\d{4}-\\d{2}-\\d{2}|^\\["  # 新日志行起始pattern
    docker: bool = False     # 是否为 Docker json-log 格式


@dataclass
class DiscoveryConfig:
    """服务自动发现配置。"""
    docker: bool = True         # 是否自动发现 Docker 容器
    host_services: bool = True  # 是否自动发现宿主机直接运行的服务（ss -tlnp）
    interval: int = 30          # 发现的服务默认检查间隔


@dataclass
class DatabaseMonitorConfig:
    """数据库监控配置。"""
    name: str = ""          # 显示名称
    type: str = "postgres"  # 数据库类型：postgres / mysql / oracle / redis
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    username: str = ""
    password: str = ""
    interval: int = 60      # 采集间隔（秒）
    connect_timeout: int = 10  # 连接超时（秒）

    # Oracle 配置
    connection_mode: str = "auto"  # direct | docker | auto（Oracle 专用，其他忽略）
    container_name: str = ""       # Docker 容器名（oracle docker 模式使用）
    oracle_sid: str = ""           # Oracle SID
    oracle_home: str = ""          # ORACLE_HOME（可选，默认从 .bash_profile 读取）
    service_name: str = ""         # Oracle service_name（12c+ 推荐，替代 SID）

    # Redis 配置
    redis_mode: str = "single"     # single | sentinel | cluster
    sentinel_master: str = ""      # Sentinel 模式下的 master name

    # 连接根因分析触发阈值（连接数占 max_connections 的比例）
    connection_threshold: float = 0.8


@dataclass
class AgentConfig:
    """Agent 主配置，聚合所有子配置。"""
    server: ServerConfig = field(default_factory=ServerConfig)
    host: HostConfig = field(default_factory=HostConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    services: List[ServiceCheckConfig] = field(default_factory=list)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    log_sources: List[LogSourceConfig] = field(default_factory=list)
    databases: List[DatabaseMonitorConfig] = field(default_factory=list)


def _parse_interval(val) -> int:
    """解析时间间隔，支持 '15s'、'1m' 等简写格式。"""
    if isinstance(val, int):
        return val
    s = str(val).strip().lower()
    if s.endswith("s"):
        return int(s[:-1])
    if s.endswith("m"):
        return int(s[:-1]) * 60
    return int(s)


def load_config(path: str) -> AgentConfig:
    """从 YAML 文件加载 Agent 配置。

    Args:
        path: 配置文件路径。

    Returns:
        解析后的 AgentConfig 实例。

    Raises:
        FileNotFoundError: 配置文件不存在时抛出。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(p) as f:
        data = yaml.safe_load(f) or {}

    cfg = AgentConfig()

    # 解析服务端配置，token 优先从环境变量读取
    srv = data.get("server", {})
    cfg.server.url = srv.get("url", cfg.server.url).rstrip("/")
    cfg.server.token = os.environ.get("NIGHTMEND_TOKEN", srv.get("token", ""))

    # 解析主机配置
    h = data.get("host", {})
    cfg.host.name = h.get("name", "")
    cfg.host.display_name = h.get("display_name", "")
    cfg.host.ip = h.get("ip", "")
    cfg.host.private_ip = h.get("private_ip", "")
    cfg.host.public_ip = h.get("public_ip", "")
    cfg.host.tags = h.get("tags", [])

    # 解析指标采集配置
    m = data.get("metrics", {})
    cfg.metrics.interval = _parse_interval(m.get("interval", 15))

    # 解析服务检查配置
    for svc in data.get("services", []):
        svc_type = svc.get("type", "http")
        target = svc.get("target", "")
        url = svc.get("url", "")
        host = svc.get("host", "")
        port = svc.get("port", 0)

        # 解析 target 简写："http://..." → url，"host:port" → host+port
        if target and not url and not host:
            if target.startswith("http://") or target.startswith("https://"):
                url = target
            elif ":" in target:
                parts = target.rsplit(":", 1)
                host = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    host = target

        sc = ServiceCheckConfig(
            name=svc.get("name", ""),
            type=svc_type,
            url=url,
            host=host,
            port=port,
            interval=_parse_interval(svc.get("interval", 30)),
            timeout=svc.get("timeout", 10),
        )
        cfg.services.append(sc)

    # 解析自动发现配置
    disc = data.get("discovery", {})
    if isinstance(disc, bool):
        cfg.discovery.docker = disc
    elif isinstance(disc, dict):
        cfg.discovery.docker = disc.get("docker", True)
        cfg.discovery.host_services = disc.get("host_services", True)
        cfg.discovery.interval = _parse_interval(disc.get("interval", 30))

    # 解析日志源配置
    for src in data.get("log_sources", []):
        ls = LogSourceConfig(
            path=src.get("path", ""),
            service=src.get("service", ""),
            multiline=src.get("multiline", False),
            multiline_pattern=src.get("multiline_pattern", LogSourceConfig.multiline_pattern),
            docker=src.get("docker", False),
        )
        if ls.path:
            cfg.log_sources.append(ls)

    # 解析数据库监控配置
    for db_conf in data.get("databases", []):
        db_type = db_conf.get("type", "postgres")
        # 根据数据库类型设置默认端口
        _default_ports = {
            "mysql": 3306, "oracle": 1521,
            "redis": 6379, "mssql": 1433, "mongodb": 27017,
        }
        default_port = _default_ports.get(db_type, 5432)
        dmc = DatabaseMonitorConfig(
            name=db_conf.get("name", ""),
            type=db_type,
            host=db_conf.get("host", "localhost"),
            port=db_conf.get("port", default_port),
            database=db_conf.get("database", ""),
            username=db_conf.get("username", ""),
            password=db_conf.get("password", ""),
            interval=_parse_interval(db_conf.get("interval", 60)),
            connect_timeout=db_conf.get("connect_timeout", 10),
            connection_mode=db_conf.get("connection_mode", "auto"),
            container_name=db_conf.get("container_name", ""),
            oracle_sid=db_conf.get("oracle_sid", ""),
            oracle_home=db_conf.get("oracle_home", ""),
            service_name=db_conf.get("service_name", ""),
            redis_mode=db_conf.get("redis_mode", "single"),
            sentinel_master=db_conf.get("sentinel_master", ""),
            connection_threshold=db_conf.get("connection_threshold", 0.8),
        )
        cfg.databases.append(dmc)

    return cfg
