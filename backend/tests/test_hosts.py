"""主机管理路由测试 — 列表、详情、指标查询。"""
import pytest
from httpx import AsyncClient
from app.models.host import Host
from app.models.host_metric import HostMetric


@pytest.fixture
async def sample_host(db_session):
    h = Host(hostname="test-host", ip_address="10.0.0.1", status="online", agent_token_id=1, group_name="web")
    db_session.add(h)
    await db_session.commit()
    await db_session.refresh(h)
    return h


@pytest.fixture
async def sample_metrics(db_session, sample_host):
    for i in range(3):
        m = HostMetric(host_id=sample_host.id, cpu_percent=50.0 + i, memory_percent=60.0 + i)
        db_session.add(m)
    await db_session.commit()


class TestListHosts:
    async def test_list_hosts(self, client: AsyncClient, auth_headers, sample_host):
        resp = await client.get("/api/v1/hosts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    async def test_list_hosts_filter_status(self, client: AsyncClient, auth_headers, sample_host):
        resp = await client.get("/api/v1/hosts?status=offline", headers=auth_headers)
        assert resp.json()["total"] == 0

    async def test_list_hosts_search(self, client: AsyncClient, auth_headers, sample_host):
        resp = await client.get("/api/v1/hosts?search=test", headers=auth_headers)
        assert resp.json()["total"] >= 1

    async def test_list_hosts_pagination(self, client: AsyncClient, auth_headers, sample_host):
        resp = await client.get("/api/v1/hosts?page=1&page_size=1", headers=auth_headers)
        assert resp.json()["page"] == 1
        assert resp.json()["page_size"] == 1

    async def test_list_hosts_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/hosts")
        assert resp.status_code == 401


class TestGetHost:
    async def test_get_host(self, client: AsyncClient, auth_headers, sample_host):
        resp = await client.get(f"/api/v1/hosts/{sample_host.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["hostname"] == "test-host"

    async def test_get_nonexistent_host(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/hosts/99999", headers=auth_headers)
        assert resp.status_code == 404


class TestHostMetrics:
    async def test_get_host_metrics(self, client: AsyncClient, auth_headers, sample_host, sample_metrics):
        resp = await client.get(f"/api/v1/hosts/{sample_host.id}/metrics", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_metrics_nonexistent_host(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/hosts/99999/metrics", headers=auth_headers)
        assert resp.status_code in (200, 404)  # may return empty or 404
