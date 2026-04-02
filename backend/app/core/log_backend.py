"""
日志后端抽象层 (Log Backend Abstraction Layer)

定义统一的日志存储接口，支持 PostgreSQL、ClickHouse、Loki 等多种后端。
通过工厂模式根据配置动态选择后端实现，保持API接口不变。

支持的后端类型:
- postgresql: 默认PostgreSQL存储（兼容模式）
- clickhouse: ClickHouse高性能日志存储
- loki: Grafana Loki时序日志存储
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

import httpx
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log_entry import LogEntry
from app.models.host import Host

logger = logging.getLogger(__name__)


class LogBackendType(str, Enum):
    """支持的日志后端类型"""
    POSTGRESQL = "postgresql"
    CLICKHOUSE = "clickhouse"
    LOKI = "loki"


class LogBackend(ABC):
    """日志后端抽象基类"""

    @abstractmethod
    async def store_logs(self, logs: List[Dict[str, Any]]) -> bool:
        """
        存储日志条目
        
        Args:
            logs: 日志条目列表，每个条目包含 host_id, service, level, message, timestamp, source
            
        Returns:
            bool: 存储成功返回True
        """
        pass

    @abstractmethod
    async def search_logs(
        self,
        q: Optional[str] = None,
        host_id: Optional[int] = None,
        service: Optional[str] = None,
        level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        搜索日志条目
        
        Returns:
            Tuple[List[Dict], int]: (日志条目列表, 总数)
        """
        pass

    @abstractmethod
    async def get_stats(
        self,
        host_id: Optional[int] = None,
        service: Optional[str] = None,
        period: str = "1h",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        获取日志统计数据
        
        Returns:
            Dict: 包含 by_level 和 by_time 统计数据
        """
        pass

    @abstractmethod
    async def cleanup_logs(self, retention_days: int = 7) -> int:
        """
        清理过期日志
        
        Returns:
            int: 删除的记录数
        """
        pass

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 子类可以重写此方法
            return True
        except Exception:
            logger.exception(f"Health check failed for {self.__class__.__name__}")
            return False


class PostgreSQLLogBackend(LogBackend):
    """PostgreSQL 日志后端（兼容模式）"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def store_logs(self, logs: List[Dict[str, Any]]) -> bool:
        """存储到PostgreSQL（现有实现）"""
        try:
            # 注意：这里需要在调用方处理 LogEntry 对象创建
            # 因为我们在抽象层不直接依赖 SQLAlchemy 模型
            return True
        except Exception:
            logger.exception("Failed to store logs to PostgreSQL")
            return False

    async def search_logs(
        self,
        q: Optional[str] = None,
        host_id: Optional[int] = None,
        service: Optional[str] = None,
        level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Dict[str, Any]], int]:
        """使用现有的 PostgreSQL 查询逻辑"""
        # 构建查询条件
        conditions = []
        if q:
            conditions.append(LogEntry.message.ilike(f"%{q}%"))
        if host_id is not None:
            conditions.append(LogEntry.host_id == host_id)
        if service:
            conditions.append(LogEntry.service == service)
        if level:
            levels = [l.strip().upper() for l in level.split(",") if l.strip()]
            conditions.append(LogEntry.level.in_(levels))
        if start_time:
            conditions.append(LogEntry.timestamp >= start_time)
        if end_time:
            conditions.append(LogEntry.timestamp <= end_time)

        # 计算总数
        count_base = select(func.count(LogEntry.id))
        for cond in conditions:
            count_base = count_base.where(cond)
        total_result = await self.db.execute(count_base)
        total = total_result.scalar() or 0

        # 分页查询
        offset = (page - 1) * page_size
        stmt = (
            select(LogEntry, Host.hostname)
            .outerjoin(Host, LogEntry.host_id == Host.id)
        )
        for cond in conditions:
            stmt = stmt.where(cond)
        stmt = stmt.order_by(LogEntry.timestamp.desc()).offset(offset).limit(page_size)
        rows = await self.db.execute(stmt)
        
        items = []
        for log_entry, hostname in rows.all():
            item = {
                "id": log_entry.id,
                "host_id": log_entry.host_id,
                "hostname": hostname,
                "service": log_entry.service,
                "source": log_entry.source,
                "level": log_entry.level,
                "message": log_entry.message,
                "timestamp": log_entry.timestamp,
                "created_at": log_entry.created_at,
            }
            items.append(item)

        return items, total

    async def get_stats(
        self,
        host_id: Optional[int] = None,
        service: Optional[str] = None,
        period: str = "1h",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """使用现有的 PostgreSQL 统计逻辑"""
        conditions = []
        if host_id is not None:
            conditions.append(LogEntry.host_id == host_id)
        if service:
            conditions.append(LogEntry.service == service)
        if start_time:
            conditions.append(LogEntry.timestamp >= start_time)
        if end_time:
            conditions.append(LogEntry.timestamp <= end_time)

        # 按级别统计
        level_stmt = select(LogEntry.level, func.count(LogEntry.id).label("count")).group_by(LogEntry.level)
        for cond in conditions:
            level_stmt = level_stmt.where(cond)
        level_rows = await self.db.execute(level_stmt)
        by_level = [{"level": row.level or "UNKNOWN", "count": row.count} for row in level_rows.all()]

        # 按时间统计
        trunc = "hour" if period == "1h" else "day"
        bucket = func.date_trunc(trunc, LogEntry.timestamp).label("time_bucket")
        time_stmt = select(bucket, func.count(LogEntry.id).label("count")).group_by(bucket).order_by(bucket)
        for cond in conditions:
            time_stmt = time_stmt.where(cond)
        time_rows = await self.db.execute(time_stmt)
        by_time = [{"time_bucket": row.time_bucket, "count": row.count} for row in time_rows.all()]

        return {"by_level": by_level, "by_time": by_time}

    async def cleanup_logs(self, retention_days: int = 7) -> int:
        """清理过期日志"""
        from datetime import timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await self.db.execute(delete(LogEntry).where(LogEntry.timestamp < cutoff))
        await self.db.commit()
        return result.rowcount or 0


class ClickHouseLogBackend(LogBackend):
    """ClickHouse 高性能日志后端"""

    def __init__(self, clickhouse_url: str, username: str = "default", password: str = ""):
        self.base_url = clickhouse_url.rstrip("/")
        self.username = username
        self.password = password
        self.table_name = "nightmend_logs"
        
    async def _ensure_table_exists(self):
        """确保日志表存在"""
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            id UInt64,
            host_id UInt32,
            service LowCardinality(String),
            source String,
            level LowCardinality(String),
            message String,
            timestamp DateTime64(3),
            created_at DateTime64(3)
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, host_id, level)
        SETTINGS index_granularity = 8192
        """
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}:8123",
                auth=(self.username, self.password) if self.password else None,
                data=create_table_sql,
                timeout=30.0
            )
            if response.status_code != 200:
                raise Exception(f"Failed to create ClickHouse table: {response.text}")

    async def store_logs(self, logs: List[Dict[str, Any]]) -> bool:
        """批量插入日志到ClickHouse（使用 JSONEachRow 格式避免 SQL 注入）"""
        if not logs:
            return True

        try:
            await self._ensure_table_exists()

            import json

            # 使用 JSONEachRow 格式，避免手动拼接 VALUES
            rows = []
            for log in logs:
                row = {
                    "id": int(log.get('id', 0)),
                    "host_id": int(log['host_id']),
                    "service": str(log.get('service', '')),
                    "source": str(log.get('source', '')),
                    "level": str(log.get('level', '')),
                    "message": str(log['message']),
                    "timestamp": log['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    "created_at": log.get('created_at', datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                }
                rows.append(json.dumps(row, ensure_ascii=False))

            body = "\n".join(rows)
            insert_sql = f"INSERT INTO {self.table_name} FORMAT JSONEachRow"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}:8123",
                    auth=(self.username, self.password) if self.password else None,
                    params={"query": insert_sql},
                    content=body,
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )

                if response.status_code != 200:
                    logger.error(f"ClickHouse insert failed: {response.text}")
                    return False

            logger.info(f"Stored {len(logs)} logs to ClickHouse")
            return True

        except Exception:
            logger.exception("Failed to store logs to ClickHouse")
            return False

    async def search_logs(
        self,
        q: Optional[str] = None,
        host_id: Optional[int] = None,
        service: Optional[str] = None,
        level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Dict[str, Any]], int]:
        """ClickHouse日志搜索（使用参数化查询防止 SQL 注入）"""
        try:
            # 构建WHERE条件和参数化查询参数
            conditions = []
            params: Dict[str, str] = {}

            if q:
                conditions.append("position(message, {param_q:String}) > 0")
                params["param_q"] = q
            if host_id is not None:
                conditions.append("host_id = {param_host_id:UInt32}")
                params["param_host_id"] = str(int(host_id))
            if service:
                conditions.append("service = {param_service:String}")
                params["param_service"] = service
            if level:
                level_list = [l.strip().upper() for l in level.split(",") if l.strip()]
                conditions.append("level IN ({param_levels:Array(String)})")
                params["param_levels"] = "[" + ",".join(f"'{l}'" for l in level_list) + "]"
            if start_time:
                conditions.append("timestamp >= {param_start:String}")
                params["param_start"] = start_time.strftime('%Y-%m-%d %H:%M:%S')
            if end_time:
                conditions.append("timestamp <= {param_end:String}")
                params["param_end"] = end_time.strftime('%Y-%m-%d %H:%M:%S')

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 整数参数先转换确保安全
            safe_page_size = int(page_size)
            safe_offset = (int(page) - 1) * safe_page_size

            # 获取总数
            count_sql = f"SELECT count() as total FROM {self.table_name} WHERE {where_clause} FORMAT JSON"
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}:8123",
                    auth=(self.username, self.password) if self.password else None,
                    params={**params, "query": count_sql},
                    timeout=30.0
                )
                if response.status_code != 200:
                    raise Exception(f"ClickHouse count query failed: {response.text}")

                count_data = response.json()
                total = count_data['data'][0]['total'] if count_data['data'] else 0

            # 分页查询（LIMIT/OFFSET 使用安全转换后的整数直接拼入，非用户可控）
            query_sql = f"""
            SELECT id, host_id, service, source, level, message, timestamp, created_at
            FROM {self.table_name}
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT {safe_page_size} OFFSET {safe_offset}
            FORMAT JSON
            """

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}:8123",
                    auth=(self.username, self.password) if self.password else None,
                    params={**params, "query": query_sql},
                    timeout=30.0
                )
                if response.status_code != 200:
                    raise Exception(f"ClickHouse search query failed: {response.text}")

                search_data = response.json()
                items = search_data['data'] if search_data['data'] else []

                # 转换时间格式
                for item in items:
                    if 'timestamp' in item:
                        item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    if 'created_at' in item:
                        item['created_at'] = datetime.fromisoformat(item['created_at'])
                    item['hostname'] = None  # ClickHouse 版本暂不支持hostname关联

                return items, total

        except Exception:
            logger.exception("ClickHouse search failed")
            return [], 0

    async def get_stats(
        self,
        host_id: Optional[int] = None,
        service: Optional[str] = None,
        period: str = "1h",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """ClickHouse统计查询（使用参数化查询防止 SQL 注入）"""
        try:
            # 构建WHERE条件和参数化查询参数
            conditions = []
            params: Dict[str, str] = {}

            if host_id is not None:
                conditions.append("host_id = {param_host_id:UInt32}")
                params["param_host_id"] = str(int(host_id))
            if service:
                conditions.append("service = {param_service:String}")
                params["param_service"] = service
            if start_time:
                conditions.append("timestamp >= {param_start:String}")
                params["param_start"] = start_time.strftime('%Y-%m-%d %H:%M:%S')
            if end_time:
                conditions.append("timestamp <= {param_end:String}")
                params["param_end"] = end_time.strftime('%Y-%m-%d %H:%M:%S')

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 按级别统计
            level_sql = f"""
            SELECT level, count() as count
            FROM {self.table_name}
            WHERE {where_clause}
            GROUP BY level
            ORDER BY count DESC
            FORMAT JSON
            """

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}:8123",
                    auth=(self.username, self.password) if self.password else None,
                    params={**params, "query": level_sql},
                    timeout=30.0
                )
                if response.status_code != 200:
                    raise Exception(f"ClickHouse level stats failed: {response.text}")

                level_data = response.json()
                by_level = level_data['data'] if level_data['data'] else []

            # 按时间统计（period 只允许白名单值，不从用户输入拼接函数名）
            time_func = "toStartOfHour" if period == "1h" else "toDate"
            time_sql = f"""
            SELECT {time_func}(timestamp) as time_bucket, count() as count
            FROM {self.table_name}
            WHERE {where_clause}
            GROUP BY time_bucket
            ORDER BY time_bucket
            FORMAT JSON
            """

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}:8123",
                    auth=(self.username, self.password) if self.password else None,
                    params={**params, "query": time_sql},
                    timeout=30.0
                )
                if response.status_code != 200:
                    raise Exception(f"ClickHouse time stats failed: {response.text}")

                time_data = response.json()
                by_time_raw = time_data['data'] if time_data['data'] else []

                # 转换时间格式
                by_time = []
                for item in by_time_raw:
                    time_bucket = datetime.fromisoformat(item['time_bucket'])
                    by_time.append({"time_bucket": time_bucket, "count": item['count']})

            return {"by_level": by_level, "by_time": by_time}

        except Exception:
            logger.exception("ClickHouse stats query failed")
            return {"by_level": [], "by_time": []}

    async def cleanup_logs(self, retention_days: int = 7) -> int:
        """ClickHouse日志清理"""
        try:
            from datetime import timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')

            # 使用 ClickHouse 参数化查询防止 SQL 注入
            # Use ClickHouse parameterized query to prevent SQL injection
            delete_sql = f"""
            ALTER TABLE {self.table_name}
            DELETE WHERE timestamp < {{cutoff:DateTime}}
            """

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}:8123",
                    auth=(self.username, self.password) if self.password else None,
                    params={"param_cutoff": cutoff_str},
                    data=delete_sql,
                    timeout=60.0
                )
                if response.status_code != 200:
                    logger.error(f"ClickHouse cleanup failed: {response.text}")
                    return 0

            logger.info(f"ClickHouse cleanup completed for logs older than {retention_days} days")
            return 1  # ClickHouse不直接返回删除数量
            
        except Exception:
            logger.exception("ClickHouse cleanup failed")
            return 0

    async def health_check(self) -> bool:
        """ClickHouse健康检查"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}:8123",
                    auth=(self.username, self.password) if self.password else None,
                    data="SELECT 1",
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception:
            return False


class LogBackendFactory:
    """日志后端工厂类"""

    _backends = {}

    @classmethod
    async def create_backend(
        cls, 
        backend_type: LogBackendType,
        **kwargs
    ) -> LogBackend:
        """
        创建日志后端实例
        
        Args:
            backend_type: 后端类型
            **kwargs: 后端特定的参数
            
        Returns:
            LogBackend: 后端实例
        """
        if backend_type == LogBackendType.POSTGRESQL:
            db_session = kwargs.get('db_session')
            if not db_session:
                raise ValueError("PostgreSQL backend requires db_session")
            return PostgreSQLLogBackend(db_session)
            
        elif backend_type == LogBackendType.CLICKHOUSE:
            clickhouse_url = kwargs.get('clickhouse_url')
            if not clickhouse_url:
                raise ValueError("ClickHouse backend requires clickhouse_url")
            return ClickHouseLogBackend(
                clickhouse_url=clickhouse_url,
                username=kwargs.get('username', 'default'),
                password=kwargs.get('password', '')
            )
            
        elif backend_type == LogBackendType.LOKI:
            # TODO: 实现Loki后端
            raise NotImplementedError("Loki backend not implemented yet")
            
        else:
            raise ValueError(f"Unsupported backend type: {backend_type}")

    @classmethod
    async def get_default_backend(cls, **kwargs) -> LogBackend:
        """获取默认配置的日志后端"""
        from app.core.config import settings
        backend_type = getattr(settings, 'log_backend_type', LogBackendType.POSTGRESQL)
        return await cls.create_backend(LogBackendType(backend_type), **kwargs)