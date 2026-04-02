"""测试 AbstractDBCollector 注册机制和分派逻辑。"""
import pytest
from nightmend_agent.db_collectors.base import AbstractDBCollector

# 导入所有采集器触发注册
import nightmend_agent.db_collectors  # noqa: F401


def test_registry_contains_all_types():
    """所有实现的采集器类型必须在注册表中。"""
    types = AbstractDBCollector.registered_types()
    assert "postgres" in types
    assert "mysql" in types
    assert "oracle" in types
    assert "redis" in types


def test_get_collector_returns_instance():
    """get_collector 对已注册类型返回实例，未知类型返回 None。"""
    pg = AbstractDBCollector.get_collector("postgres")
    assert pg is not None

    unknown = AbstractDBCollector.get_collector("unknown_db")
    assert unknown is None


def test_custom_collector_auto_registers():
    """自定义子类通过 db_type 参数自动注册。"""
    from nightmend_agent.db_collectors.base import AbstractDBCollector
    from nightmend_agent.config import DatabaseMonitorConfig

    class FakeCollector(AbstractDBCollector, db_type="fakedb_test"):
        def collect(self, cfg: DatabaseMonitorConfig):
            return None

    assert "fakedb_test" in AbstractDBCollector.registered_types()
    instance = AbstractDBCollector.get_collector("fakedb_test")
    assert isinstance(instance, FakeCollector)
