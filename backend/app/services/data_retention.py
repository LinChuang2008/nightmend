"""
数据保留策略服务 (Data Retention Policy Service)

自动清理过期的监控数据，防止数据库无限增长。
支持配置化的保留期设置，分批次安全删除，记录清理统计。

Automatically cleans up expired monitoring data to prevent unlimited database growth.
Supports configurable retention period settings, batch-wise safe deletion, and cleanup statistics logging.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.ai_insight import AIInsight
from app.models.audit_log import AuditLog
from app.models.db_metric import DbMetric
from app.models.host_metric import HostMetric
from app.models.log_entry import LogEntry
from app.models.setting import Setting

logger = logging.getLogger(__name__)

# 默认保留期配置 (Default Retention Settings)
DEFAULT_RETENTION_DAYS = {
    "host_metrics": 30,      # 主机指标保留30天
    "db_metrics": 30,        # 数据库指标保留30天  
    "log_entries": 7,        # 日志条目保留7天
    "ai_insights": 90,       # AI洞察保留90天
    "audit_logs": 365        # 审计日志保留1年
}

# 批次清理大小，避免一次删除过多数据
BATCH_SIZE = 1000


class DataRetentionService:
    """数据保留策略服务类"""

    def __init__(self, db: Session):
        self.db = db

    def get_retention_days(self, data_type: str) -> int:
        """
        获取指定数据类型的保留天数
        
        Args:
            data_type: 数据类型 (host_metrics/db_metrics/log_entries/ai_insights/audit_logs)
            
        Returns:
            int: 保留天数
        """
        try:
            setting = self.db.query(Setting).filter(Setting.key == f"retention_days_{data_type}").first()
            if setting:
                return int(setting.value)
            return DEFAULT_RETENTION_DAYS.get(data_type, 30)
        except (ValueError, TypeError):
            logger.warning(f"Invalid retention setting for {data_type}, using default")
            return DEFAULT_RETENTION_DAYS.get(data_type, 30)

    def set_retention_days(self, data_type: str, days: int) -> None:
        """
        设置指定数据类型的保留天数
        
        Args:
            data_type: 数据类型
            days: 保留天数
        """
        setting = self.db.query(Setting).filter(Setting.key == f"retention_days_{data_type}").first()
        if setting:
            setting.value = str(days)
        else:
            setting = Setting(
                key=f"retention_days_{data_type}",
                value=str(days),
                description=f"{data_type} 数据保留天数"
            )
            self.db.add(setting)
        self.db.commit()

    def cleanup_expired_data(self) -> Dict[str, int]:
        """
        清理所有过期数据
        
        Returns:
            Dict[str, int]: 各类型数据清理统计 
        """
        cleanup_stats = {}
        
        # 清理主机指标
        cleanup_stats["host_metrics"] = self._cleanup_host_metrics()
        
        # 清理数据库指标  
        cleanup_stats["db_metrics"] = self._cleanup_db_metrics()
        
        # 清理日志条目
        cleanup_stats["log_entries"] = self._cleanup_log_entries()
        
        # 清理 AI 洞察
        cleanup_stats["ai_insights"] = self._cleanup_ai_insights()
        
        # 清理审计日志
        cleanup_stats["audit_logs"] = self._cleanup_audit_logs()
        
        # 记录清理统计
        total_cleaned = sum(cleanup_stats.values())
        logger.info(f"Data cleanup completed. Total records cleaned: {total_cleaned}, Details: {cleanup_stats}")
        
        return cleanup_stats

    def _cleanup_host_metrics(self) -> int:
        """清理过期主机指标数据"""
        retention_days = self.get_retention_days("host_metrics")
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        total_deleted = 0
        while True:
            # 分批删除，避免长事务
            query = self.db.query(HostMetric).filter(
                HostMetric.recorded_at < cutoff_time
            ).limit(BATCH_SIZE)
            
            batch = query.all()
            if not batch:
                break
                
            for record in batch:
                self.db.delete(record)
            
            self.db.commit()
            total_deleted += len(batch)
            
            if len(batch) < BATCH_SIZE:
                break
                
        logger.info(f"Cleaned up {total_deleted} host_metrics records older than {retention_days} days")
        return total_deleted

    def _cleanup_db_metrics(self) -> int:
        """清理过期数据库指标数据"""
        retention_days = self.get_retention_days("db_metrics")
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        total_deleted = 0
        while True:
            query = self.db.query(DbMetric).filter(
                DbMetric.recorded_at < cutoff_time
            ).limit(BATCH_SIZE)
            
            batch = query.all()
            if not batch:
                break
                
            for record in batch:
                self.db.delete(record)
            
            self.db.commit()
            total_deleted += len(batch)
            
            if len(batch) < BATCH_SIZE:
                break
                
        logger.info(f"Cleaned up {total_deleted} db_metrics records older than {retention_days} days")
        return total_deleted

    def _cleanup_log_entries(self) -> int:
        """清理过期日志条目数据"""
        retention_days = self.get_retention_days("log_entries")
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        total_deleted = 0
        while True:
            # 注意：日志使用 timestamp 字段，不是 created_at
            query = self.db.query(LogEntry).filter(
                LogEntry.timestamp < cutoff_time
            ).limit(BATCH_SIZE)
            
            batch = query.all()
            if not batch:
                break
                
            for record in batch:
                self.db.delete(record)
            
            self.db.commit()
            total_deleted += len(batch)
            
            if len(batch) < BATCH_SIZE:
                break
                
        logger.info(f"Cleaned up {total_deleted} log_entries records older than {retention_days} days")
        return total_deleted

    def _cleanup_ai_insights(self) -> int:
        """清理过期 AI 洞察数据"""
        retention_days = self.get_retention_days("ai_insights")
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        total_deleted = 0
        while True:
            query = self.db.query(AIInsight).filter(
                AIInsight.created_at < cutoff_time
            ).limit(BATCH_SIZE)
            
            batch = query.all()
            if not batch:
                break
                
            for record in batch:
                self.db.delete(record)
            
            self.db.commit()
            total_deleted += len(batch)
            
            if len(batch) < BATCH_SIZE:
                break
                
        logger.info(f"Cleaned up {total_deleted} ai_insights records older than {retention_days} days")
        return total_deleted

    def _cleanup_audit_logs(self) -> int:
        """清理过期审计日志数据"""
        retention_days = self.get_retention_days("audit_logs")
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        total_deleted = 0
        while True:
            query = self.db.query(AuditLog).filter(
                AuditLog.created_at < cutoff_time
            ).limit(BATCH_SIZE)
            
            batch = query.all()
            if not batch:
                break
                
            for record in batch:
                self.db.delete(record)
            
            self.db.commit()
            total_deleted += len(batch)
            
            if len(batch) < BATCH_SIZE:
                break
                
        logger.info(f"Cleaned up {total_deleted} audit_logs records older than {retention_days} days")
        return total_deleted

    def get_data_statistics(self) -> Dict[str, Dict[str, int]]:
        """
        获取各类型数据的统计信息
        
        Returns:
            Dict[str, Dict[str, int]]: 数据统计信息
        """
        stats = {}
        
        # 主机指标统计
        stats["host_metrics"] = {
            "total": self.db.query(HostMetric).count(),
            "retention_days": self.get_retention_days("host_metrics")
        }
        
        # 数据库指标统计
        stats["db_metrics"] = {
            "total": self.db.query(DbMetric).count(),
            "retention_days": self.get_retention_days("db_metrics")
        }
        
        # 日志条目统计
        stats["log_entries"] = {
            "total": self.db.query(LogEntry).count(),
            "retention_days": self.get_retention_days("log_entries")
        }
        
        # AI 洞察统计
        stats["ai_insights"] = {
            "total": self.db.query(AIInsight).count(),
            "retention_days": self.get_retention_days("ai_insights")
        }
        
        # 审计日志统计
        stats["audit_logs"] = {
            "total": self.db.query(AuditLog).count(),
            "retention_days": self.get_retention_days("audit_logs")
        }
        
        return stats


def run_data_cleanup():
    """
    运行数据清理任务（用于定时调度）
    
    Returns:
        Dict[str, int]: 清理统计结果
    """
    try:
        db_gen = get_db()
        db = next(db_gen)
        
        service = DataRetentionService(db)
        cleanup_stats = service.cleanup_expired_data()
        
        return cleanup_stats
    except Exception as e:
        logger.error(f"Data cleanup failed: {str(e)}")
        raise
    finally:
        if 'db' in locals():
            db.close()