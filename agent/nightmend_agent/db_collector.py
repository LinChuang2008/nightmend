"""
数据库指标采集入口（向后兼容 Dispatcher）。

外部调用接口保持不变：collect_db_metrics(cfg) → Optional[Dict]

内部已重构为插件化架构（db_collectors/ 目录），
原 collect_postgres_metrics / collect_mysql_metrics / collect_oracle_metrics
保留为废弃别名（过渡期兼容），新代码请直接调用 collect_db_metrics()。
"""
import logging
from dataclasses import asdict
from typing import Dict, Optional

from nightmend_agent.config import DatabaseMonitorConfig

# 导入所有采集器，触发自动注册
import nightmend_agent.db_collectors  # noqa: F401
from nightmend_agent.db_collectors.base import AbstractDBCollector

logger = logging.getLogger(__name__)


def collect_db_metrics(cfg: DatabaseMonitorConfig) -> Optional[Dict]:
    """根据数据库类型分派执行对应的指标采集。

    Args:
        cfg: 数据库监控配置。

    Returns:
        指标字典（可直接 JSON 序列化上报），采集失败返回 None。
    """
    collector = AbstractDBCollector.get_collector(cfg.type)
    if collector is None:
        logger.warning(
            "Unsupported database type: %s (supported: %s)",
            cfg.type,
            AbstractDBCollector.registered_types(),
        )
        return None

    metrics = collector.collect(cfg)
    if metrics is None:
        return None

    result = asdict(metrics)
    # slow_queries_detail 中的 SlowQuery dataclass 已被 asdict 展开为 dict，无需额外处理
    return result


# ─────────────────────── 废弃别名（过渡期兼容） ───────────────────────

def collect_postgres_metrics(cfg: DatabaseMonitorConfig) -> Optional[Dict]:
    """已废弃：请使用 collect_db_metrics(cfg)。"""
    logger.debug("collect_postgres_metrics is deprecated, use collect_db_metrics()")
    return collect_db_metrics(cfg)


def collect_mysql_metrics(cfg: DatabaseMonitorConfig) -> Optional[Dict]:
    """已废弃：请使用 collect_db_metrics(cfg)。"""
    logger.debug("collect_mysql_metrics is deprecated, use collect_db_metrics()")
    return collect_db_metrics(cfg)


def collect_oracle_metrics(cfg: DatabaseMonitorConfig) -> Optional[Dict]:
    """已废弃：请使用 collect_db_metrics(cfg)。"""
    logger.debug("collect_oracle_metrics is deprecated, use collect_db_metrics()")
    return collect_db_metrics(cfg)
