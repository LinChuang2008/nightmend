"""数据库监控路由测试。"""
import pytest
from httpx import AsyncClient
from app.models.db_metric import MonitoredDatabase, DbMetric
from app.models.host import Host


@pytest.fixture
async def sample_db(db_session):
    h = Host(hostname="db-host", status="online", agent_token_id=1)
    db_session.add(h)
    await db_session.commit()
    await db_session.refresh(h)

    mdb = MonitoredDatabase(host_id=h.id, name="nightmend", db_type="postgres", status="healthy")
    db_session.add(mdb)
    await db_session.commit()
    await db_session.refresh(mdb)

    metric = DbMetric(database_id=mdb.id, connections_total=100, connections_active=5,
                      database_size_mb=512.0, slow_queries=2, qps=150.0)
    db_session.add(metric)
    await db_session.commit()
    return mdb


class TestDatabases:
    async def test_list_databases(self, client: AsyncClient, auth_headers, sample_db):
        resp = await client.get("/api/v1/databases", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["databases"][0]["name"] == "nightmend"

    async def test_list_databases_filter_host(self, client: AsyncClient, auth_headers, sample_db):
        resp = await client.get("/api/v1/databases?host_id=99999", headers=auth_headers)
        assert resp.json()["total"] == 0

    async def test_get_database(self, client: AsyncClient, auth_headers, sample_db):
        resp = await client.get(f"/api/v1/databases/{sample_db.id}", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_database_metrics(self, client: AsyncClient, auth_headers, sample_db):
        resp = await client.get(f"/api/v1/databases/{sample_db.id}/metrics", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_nonexistent_db(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/databases/99999", headers=auth_headers)
        assert resp.status_code == 404
