"""DBMetrics schema 序列化测试。"""
from dataclasses import asdict
from nightmend_agent.db_schema import DBMetrics, SlowQuery


def test_dbmetrics_default_values():
    """DBMetrics 默认值正确。"""
    m = DBMetrics(db_name="test", db_type="postgres", timestamp="2026-01-01T00:00:00Z")
    assert m.connections_total == 0
    assert m.lock_waits == 0
    assert m.deadlocks == 0
    assert m.extra == {}
    assert m.slow_queries_detail == []


def test_dbmetrics_asdict_serializable():
    """DBMetrics 可通过 asdict 序列化为纯 dict（无自定义对象）。"""
    sq = SlowQuery(sql_id="abc123", avg_seconds=2.5, executions=10, sql_text="SELECT 1")
    m = DBMetrics(
        db_name="mydb",
        db_type="mysql",
        timestamp="2026-01-01T00:00:00Z",
        connections_total=50,
        slow_queries=1,
        slow_queries_detail=[sq],
        extra={"innodb_buffer_pool_hit_rate": 0.999},
    )

    d = asdict(m)
    assert isinstance(d, dict)
    assert d["db_name"] == "mydb"
    assert d["slow_queries_detail"][0]["sql_id"] == "abc123"
    assert d["extra"]["innodb_buffer_pool_hit_rate"] == 0.999


def test_dbmetrics_extra_is_independent():
    """两个 DBMetrics 实例的 extra 字典相互独立。"""
    m1 = DBMetrics(db_name="a", db_type="pg", timestamp="t")
    m2 = DBMetrics(db_name="b", db_type="pg", timestamp="t")
    m1.extra["key"] = "value"
    assert "key" not in m2.extra
