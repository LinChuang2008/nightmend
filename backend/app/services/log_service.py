"""
日志服务管理器 (Log Service Manager)

统一管理日志的存储、查询和实时推送，集成多种后端存储。
提供与现有API完全兼容的接口，支持平滑切换到高性能日志后端。

功能：
1. 统一的日志CRUD操作接口
2. 自动后端选择和故障转移
3. 实时日志流管理
4. 数据迁移和同步
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.log_backend import (
    LogBackend, 
    LogBackendFactory, 
    LogBackendType,
    PostgreSQLLogBackend
)
from app.models.log_entry import LogEntry
from app.services.log_broadcaster import log_broadcaster

logger = logging.getLogger(__name__)


class LogService:
    """
    日志服务管理器 
    
    负责协调多个日志后端，提供统一的日志操作接口。
    支持写入双写、故障转移、性能监控等企业级功能。
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.primary_backend: Optional[LogBackend] = None
        self.fallback_backend: Optional[LogBackend] = None
        self.backend_type = LogBackendType(settings.log_backend_type)
        self._initialized = False

    async def initialize(self):
        """初始化日志后端"""
        if self._initialized:
            return
            
        try:
            # 创建主要后端
            if self.backend_type == LogBackendType.CLICKHOUSE:
                self.primary_backend = await LogBackendFactory.create_backend(
                    LogBackendType.CLICKHOUSE,
                    clickhouse_url=settings.clickhouse_url,
                    username=settings.clickhouse_user,
                    password=settings.clickhouse_password
                )
                # PostgreSQL作为备用后端
                self.fallback_backend = await LogBackendFactory.create_backend(
                    LogBackendType.POSTGRESQL,
                    db_session=self.db
                )
            elif self.backend_type == LogBackendType.LOKI:
                # TODO: 实现Loki后端
                logger.warning("Loki backend not implemented, falling back to PostgreSQL")
                self.primary_backend = await LogBackendFactory.create_backend(
                    LogBackendType.POSTGRESQL,
                    db_session=self.db
                )
            else:
                # 默认使用PostgreSQL
                self.primary_backend = await LogBackendFactory.create_backend(
                    LogBackendType.POSTGRESQL,
                    db_session=self.db
                )
                
            self._initialized = True
            logger.info(f"Log service initialized with {self.backend_type} backend")
            
        except Exception as e:
            logger.error(f"Failed to initialize log backend: {e}")
            # 故障转移到PostgreSQL
            self.primary_backend = await LogBackendFactory.create_backend(
                LogBackendType.POSTGRESQL,
                db_session=self.db
            )
            self._initialized = True

    async def store_logs(self, logs: List[Dict[str, Any]], broadcast: bool = True) -> bool:
        """
        存储日志条目
        
        Args:
            logs: 日志条目列表
            broadcast: 是否广播到WebSocket订阅者
            
        Returns:
            bool: 存储成功
        """
        if not self._initialized:
            await self.initialize()
            
        success = False
        
        # PostgreSQL存储（兼容性保证）
        try:
            if self.backend_type != LogBackendType.POSTGRESQL:
                # 非PostgreSQL模式下，仍需要存储到PostgreSQL以保证兼容性
                log_entries = []
                for log_data in logs:
                    log_entry = LogEntry(
                        host_id=log_data['host_id'],
                        service=log_data.get('service'),
                        source=log_data.get('source'),
                        level=log_data.get('level'),
                        message=log_data['message'],
                        timestamp=log_data['timestamp']
                    )
                    log_entries.append(log_entry)
                    
                self.db.add_all(log_entries)
                await self.db.commit()
                success = True
                
                # 添加ID到日志数据中，用于其他后端
                for i, log_entry in enumerate(log_entries):
                    logs[i]['id'] = log_entry.id
        except Exception as e:
            logger.error(f"Failed to store logs to PostgreSQL: {e}")
            await self.db.rollback()
            
        # 主要后端存储
        try:
            if self.primary_backend and self.backend_type != LogBackendType.POSTGRESQL:
                backend_success = await self.primary_backend.store_logs(logs)
                if not backend_success and self.fallback_backend:
                    logger.warning("Primary backend failed, using fallback")
                    await self.fallback_backend.store_logs(logs)
                success = success or backend_success
            else:
                success = True  # PostgreSQL已经成功
                
        except Exception as e:
            logger.error(f"Failed to store logs to {self.backend_type}: {e}")
            if self.fallback_backend:
                try:
                    await self.fallback_backend.store_logs(logs)
                    success = True
                except Exception as fe:
                    logger.error(f"Fallback backend also failed: {fe}")
                    
        # 实时广播
        if success and broadcast:
            try:
                # 转换为广播格式
                broadcast_logs = []
                for log_data in logs:
                    broadcast_entry = {
                        "id": log_data.get('id'),
                        "host_id": log_data['host_id'],
                        "service": log_data.get('service'),
                        "level": log_data.get('level'),
                        "message": log_data['message'],
                        "timestamp": log_data['timestamp'].isoformat(),
                    }
                    broadcast_logs.append(broadcast_entry)
                    
                await log_broadcaster.publish(broadcast_logs)
            except Exception as e:
                logger.error(f"Failed to broadcast logs: {e}")
                
        return success

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
        搜索日志条目，优先使用高性能后端
        
        Returns:
            Tuple[List[Dict], int]: (日志条目列表, 总数)
        """
        if not self._initialized:
            await self.initialize()
            
        # 尝试使用主要后端
        try:
            if self.primary_backend:
                return await self.primary_backend.search_logs(
                    q=q, host_id=host_id, service=service, level=level,
                    start_time=start_time, end_time=end_time,
                    page=page, page_size=page_size
                )
        except Exception as e:
            logger.error(f"Primary backend search failed: {e}")
            
        # 故障转移到备用后端
        if self.fallback_backend:
            try:
                return await self.fallback_backend.search_logs(
                    q=q, host_id=host_id, service=service, level=level,
                    start_time=start_time, end_time=end_time,
                    page=page, page_size=page_size
                )
            except Exception as e:
                logger.error(f"Fallback backend search failed: {e}")
                
        # 最后使用直接PostgreSQL查询（兼容模式）
        return await self._postgresql_search(
            q=q, host_id=host_id, service=service, level=level,
            start_time=start_time, end_time=end_time,
            page=page, page_size=page_size
        )

    async def get_stats(
        self,
        host_id: Optional[int] = None,
        service: Optional[str] = None,
        period: str = "1h",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """获取日志统计，优先使用高性能后端"""
        if not self._initialized:
            await self.initialize()
            
        # 尝试使用主要后端
        try:
            if self.primary_backend:
                return await self.primary_backend.get_stats(
                    host_id=host_id, service=service, period=period,
                    start_time=start_time, end_time=end_time
                )
        except Exception as e:
            logger.error(f"Primary backend stats failed: {e}")
            
        # 故障转移到备用后端
        if self.fallback_backend:
            try:
                return await self.fallback_backend.get_stats(
                    host_id=host_id, service=service, period=period,
                    start_time=start_time, end_time=end_time
                )
            except Exception as e:
                logger.error(f"Fallback backend stats failed: {e}")
                
        # 最后使用直接PostgreSQL查询
        return await self._postgresql_stats(
            host_id=host_id, service=service, period=period,
            start_time=start_time, end_time=end_time
        )

    async def cleanup_logs(self, retention_days: int = None) -> int:
        """清理过期日志"""
        if not self._initialized:
            await self.initialize()
            
        if retention_days is None:
            retention_days = settings.log_retention_days
            
        total_deleted = 0
        
        # 清理主要后端
        try:
            if self.primary_backend:
                deleted = await self.primary_backend.cleanup_logs(retention_days)
                total_deleted += deleted
                logger.info(f"Cleaned up {deleted} logs from {self.backend_type}")
        except Exception as e:
            logger.error(f"Failed to cleanup {self.backend_type}: {e}")
            
        # 清理PostgreSQL（总是执行）
        try:
            from datetime import timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            from sqlalchemy import delete
            result = await self.db.execute(
                delete(LogEntry).where(LogEntry.timestamp < cutoff)
            )
            deleted = result.rowcount or 0
            await self.db.commit()
            total_deleted += deleted
            logger.info(f"Cleaned up {deleted} logs from PostgreSQL")
        except Exception as e:
            logger.error(f"Failed to cleanup PostgreSQL: {e}")
            await self.db.rollback()
            
        return total_deleted

    async def health_check(self) -> Dict[str, Any]:
        """检查所有后端健康状态"""
        if not self._initialized:
            await self.initialize()
            
        health = {
            "primary_backend": {
                "type": self.backend_type,
                "healthy": False,
                "error": None
            }
        }
        
        try:
            if self.primary_backend:
                health["primary_backend"]["healthy"] = await self.primary_backend.health_check()
        except Exception as e:
            health["primary_backend"]["error"] = str(e)
            
        if self.fallback_backend:
            health["fallback_backend"] = {
                "type": "postgresql",
                "healthy": False,
                "error": None
            }
            try:
                health["fallback_backend"]["healthy"] = await self.fallback_backend.health_check()
            except Exception as e:
                health["fallback_backend"]["error"] = str(e)
                
        return health

    async def migrate_data(self, source: str = "postgresql", target: str = None, batch_size: int = 1000) -> Dict[str, Any]:
        """
        迁移数据到新后端
        
        Args:
            source: 源后端类型
            target: 目标后端类型，默认为当前配置的后端
            batch_size: 批处理大小
            
        Returns:
            Dict: 迁移统计信息
        """
        if not target:
            target = self.backend_type
            
        if source == target:
            return {"error": "Source and target backends are the same"}
            
        if not self._initialized:
            await self.initialize()
            
        logger.info(f"Starting data migration from {source} to {target}")
        
        migrated_count = 0
        error_count = 0
        
        try:
            # 获取源数据总数
            count_stmt = select(func.count(LogEntry.id))
            total_result = await self.db.execute(count_stmt)
            total_count = total_result.scalar() or 0
            
            logger.info(f"Total logs to migrate: {total_count}")
            
            # 批量迁移
            offset = 0
            while offset < total_count:
                try:
                    # 从PostgreSQL读取批量数据
                    stmt = (
                        select(LogEntry)
                        .order_by(LogEntry.id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                    result = await self.db.execute(stmt)
                    logs = result.scalars().all()
                    
                    if not logs:
                        break
                        
                    # 转换为目标格式
                    log_data = []
                    for log in logs:
                        log_data.append({
                            "id": log.id,
                            "host_id": log.host_id,
                            "service": log.service,
                            "source": log.source,
                            "level": log.level,
                            "message": log.message,
                            "timestamp": log.timestamp,
                            "created_at": log.created_at
                        })
                    
                    # 写入目标后端（不广播）
                    if target == LogBackendType.CLICKHOUSE and self.primary_backend:
                        success = await self.primary_backend.store_logs(log_data)
                        if success:
                            migrated_count += len(logs)
                        else:
                            error_count += len(logs)
                    
                    offset += batch_size
                    
                    if offset % (batch_size * 10) == 0:
                        logger.info(f"Migration progress: {offset}/{total_count}")
                        
                except Exception as e:
                    logger.error(f"Batch migration error at offset {offset}: {e}")
                    error_count += batch_size
                    offset += batch_size
                    continue
                    
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return {"error": str(e)}
            
        logger.info(f"Migration completed: {migrated_count} success, {error_count} errors")
        
        return {
            "total_count": total_count,
            "migrated_count": migrated_count,
            "error_count": error_count,
            "success_rate": migrated_count / total_count if total_count > 0 else 0
        }

    # 内部方法：PostgreSQL直接查询（兼容模式）
    async def _postgresql_search(self, **kwargs) -> Tuple[List[Dict[str, Any]], int]:
        """PostgreSQL直接搜索（作为最后的兼容方案）"""
        # 重用现有的PostgreSQL查询逻辑
        pg_backend = PostgreSQLLogBackend(self.db)
        return await pg_backend.search_logs(**kwargs)

    async def _postgresql_stats(self, **kwargs) -> Dict[str, Any]:
        """PostgreSQL直接统计（作为最后的兼容方案）"""
        pg_backend = PostgreSQLLogBackend(self.db)
        return await pg_backend.get_stats(**kwargs)


# 全局实例管理
_log_service_instances = {}

async def get_log_service(db: AsyncSession) -> LogService:
    """获取日志服务实例（单例模式）"""
    instance_key = id(db)
    if instance_key not in _log_service_instances:
        service = LogService(db)
        await service.initialize()
        _log_service_instances[instance_key] = service
    return _log_service_instances[instance_key]