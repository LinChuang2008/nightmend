"""
数据库监控统一输出 Schema。

DBMetrics 是所有数据库采集器的标准输出对象，
通过 dataclasses.asdict() 可序列化为字典上报。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SlowQuery:
    """慢查询详情条目。"""
    sql_id: str
    avg_seconds: float
    executions: int
    sql_text: str


@dataclass
class DBMetrics:
    """统一数据库指标模型。

    必填字段：db_name、db_type、timestamp。
    其余字段按数据库类型填充，未支持的保留默认值。
    数据库特有扩展指标放入 extra 字典，格式自由。
    """
    # 必填核心字段
    db_name: str
    db_type: str
    timestamp: str

    # 连接
    connections_total: int = 0
    connections_active: int = 0
    connections_max: int = 0          # 最大连接数上限（max_connections / processes）

    # 性能
    qps: float = 0.0
    slow_queries: int = 0
    slow_queries_detail: List[SlowQuery] = field(default_factory=list)

    # 存储
    database_size_mb: float = 0.0
    tables_count: int = 0

    # 事务
    transactions_committed: int = 0
    transactions_rolled_back: int = 0

    # 锁等待
    lock_waits: int = 0               # 当前等待锁的请求数
    deadlocks: int = 0                # 死锁次数（累计）

    # 扩展字段（各数据库特有）
    # 常见 key 示例：
    #   innodb_buffer_pool_hit_rate  float   MySQL InnoDB 命中率
    #   replication_lag_seconds      float   主从复制延迟
    #   cache_hit_ratio              float   PostgreSQL 缓存命中率
    #   tablespace_used_pct          float   Oracle 表空间使用率
    #   used_memory_mb               float   Redis 内存使用
    #   keyspace_hit_ratio           float   Redis 命中率
    #   connection_breakdown         dict    连接根因分析（超阈值时填充）
    extra: Dict = field(default_factory=dict)
