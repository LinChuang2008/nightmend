"""
数据库采集器基类。

所有具体采集器继承 AbstractDBCollector，通过 db_type 关键字参数
自动注册到全局 Registry，实现插件化分派。
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Type

from nightmend_agent.config import DatabaseMonitorConfig
from nightmend_agent.db_schema import DBMetrics

logger = logging.getLogger(__name__)


class AbstractDBCollector(ABC):
    """所有数据库采集器的基类（Strategy Pattern + Registry）。"""

    # 子类注册表：db_type → 采集器类
    _registry: Dict[str, Type["AbstractDBCollector"]] = {}

    def __init_subclass__(cls, db_type: str = "", **kwargs):
        super().__init_subclass__(**kwargs)
        if db_type:
            AbstractDBCollector._registry[db_type] = cls
            logger.debug("Registered DB collector: %s → %s", db_type, cls.__name__)

    @abstractmethod
    def collect(self, cfg: DatabaseMonitorConfig) -> Optional[DBMetrics]:
        """执行采集，返回标准化指标对象，失败返回 None。"""

    @classmethod
    def get_collector(cls, db_type: str) -> Optional["AbstractDBCollector"]:
        """按类型获取已注册的采集器实例。"""
        klass = cls._registry.get(db_type)
        if klass is None:
            return None
        return klass()

    @classmethod
    def registered_types(cls) -> list:
        """返回所有已注册的数据库类型列表。"""
        return list(cls._registry.keys())
