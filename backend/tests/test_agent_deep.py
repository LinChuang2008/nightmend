"""Agent 路由深度测试 — 注册、心跳、指标、服务、DB指标、日志。"""
import hashlib
import hmac
import pytest

from app.core.config import settings
from app.models.agent_token import AgentToken
from app.models.host import Host
from app.models.service import Service


@pytest.fixture
async def agent_token_and_headers(db_session):
    """Create an agent token and return (token_obj, headers)."""
    raw = "test-agent-token-12345"
    token_hash = hmac.new(
        settings.agent_token_hmac_key.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()
    token = AgentToken(
        name="test-token", token_hash=token_hash,
        token_prefix=raw[:8], created_by=1, is_active=True,
    )
    db_session.add(token)
    await db_session.commit()
    await db_session.refresh(token)
    headers = {"Authorization": f"Bearer {raw}"}
    return token, headers


class TestAgentRegister:
    @pytest.mark.asyncio
    async def test_register_new_host(self, client, agent_token_and_headers):
        _, headers = agent_token_and_headers
        resp = await client.post("/api/v1/agent/register", json={
            "hostname": "new-host-001",
            "ip_address": "10.0.0.1",
            "os": "Linux",
            "cpu_cores": 8,
            "memory_total_mb": 16384,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert data["hostname"] == "new-host-001"

    @pytest.mark.asyncio
    async def test_register_idempotent(self, client, agent_token_and_headers):
        _, headers = agent_token_and_headers
        body = {"hostname": "idempotent-host", "ip_address": "10.0.0.2"}
        resp1 = await client.post("/api/v1/agent/register", json=body, headers=headers)
        resp2 = await client.post("/api/v1/agent/register", json=body, headers=headers)
        assert resp1.json()["created"] is True
        assert resp2.json()["created"] is False
        assert resp1.json()["host_id"] == resp2.json()["host_id"]


class TestAgentHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat(self, client, agent_token_and_headers, db_session):
        token, headers = agent_token_and_headers
        host = Host(hostname="hb-host", status="online", agent_token_id=token.id)
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        resp = await client.post("/api/v1/agent/heartbeat", json={"host_id": host.id}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAgentMetrics:
    @pytest.mark.asyncio
    async def test_report_metrics(self, client, agent_token_and_headers, db_session):
        token, headers = agent_token_and_headers
        host = Host(hostname="metric-host", status="online", agent_token_id=token.id)
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        resp = await client.post("/api/v1/agent/metrics", json={
            "host_id": host.id,
            "cpu_percent": 75.5,
            "memory_percent": 60.0,
            "disk_percent": 40.0,
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["status"] == "ok"


class TestServiceRegister:
    @pytest.mark.asyncio
    async def test_register_service(self, client, agent_token_and_headers):
        _, headers = agent_token_and_headers
        resp = await client.post("/api/v1/agent/services/register", json={
            "name": "test-nginx",
            "target": "http://nginx:80",
            "type": "http",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["created"] is True

    @pytest.mark.asyncio
    async def test_register_service_idempotent(self, client, agent_token_and_headers):
        _, headers = agent_token_and_headers
        body = {"name": "test-redis", "target": "redis:6379", "type": "tcp"}
        r1 = await client.post("/api/v1/agent/services/register", json=body, headers=headers)
        r2 = await client.post("/api/v1/agent/services/register", json=body, headers=headers)
        assert r1.json()["created"] is True
        assert r2.json()["created"] is False


class TestServiceCheck:
    @pytest.mark.asyncio
    async def test_report_service_check(self, client, agent_token_and_headers, db_session):
        _, headers = agent_token_and_headers
        svc = Service(name="check-svc", type="http", target="http://svc", status="up")
        db_session.add(svc)
        await db_session.commit()
        await db_session.refresh(svc)

        resp = await client.post("/api/v1/agent/services", json={
            "service_id": svc.id,
            "status": "down",
            "response_time_ms": 5000,
            "error": "timeout",
        }, headers=headers)
        assert resp.status_code == 201

        # Verify service status updated
        await db_session.refresh(svc)
        assert svc.status == "down"


class TestDbMetrics:
    @pytest.mark.asyncio
    async def test_report_db_metrics(self, client, agent_token_and_headers, db_session):
        token, headers = agent_token_and_headers
        host = Host(hostname="db-host", status="online", agent_token_id=token.id)
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        resp = await client.post("/api/v1/agent/db-metrics", json={
            "host_id": host.id,
            "db_name": "testdb",
            "db_type": "postgres",
            "connections_total": 100,
            "connections_active": 20,
            "database_size_mb": 500,
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_report_db_metrics_missing_fields(self, client, agent_token_and_headers):
        _, headers = agent_token_and_headers
        resp = await client.post("/api/v1/agent/db-metrics", json={}, headers=headers)
        assert resp.status_code == 400


class TestAutoClassify:
    def test_classify_middleware(self):
        from app.routers.agent import _auto_classify_service
        assert _auto_classify_service("PostgreSQL 15") == "middleware"
        assert _auto_classify_service("Redis Cache") == "middleware"
        assert _auto_classify_service("RabbitMQ") == "middleware"

    def test_classify_infrastructure(self):
        from app.routers.agent import _auto_classify_service
        assert _auto_classify_service("Nginx") == "infrastructure"
        assert _auto_classify_service("HAProxy") == "infrastructure"

    def test_classify_business(self):
        from app.routers.agent import _auto_classify_service
        assert _auto_classify_service("backend-api") == "business"
        assert _auto_classify_service("frontend-web") == "business"

    def test_classify_default(self):
        from app.routers.agent import _auto_classify_service
        assert _auto_classify_service("my-custom-thing") == "business"
