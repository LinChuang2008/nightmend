"""SLA 管理路由测试。"""
import pytest
from httpx import AsyncClient
from app.models.sla import SLARule
from app.models.service import Service
from app.models.host import Host


@pytest.fixture
async def sample_sla(db_session):
    h = Host(hostname="sla-host", status="online", agent_token_id=1)
    db_session.add(h)
    await db_session.commit()
    await db_session.refresh(h)

    svc = Service(name="api-svc", type="http", target="http://localhost", host_id=h.id, status="up", is_active=True)
    db_session.add(svc)
    await db_session.commit()
    await db_session.refresh(svc)

    rule = SLARule(service_id=svc.id, name="API SLA", target_percent=99.90, calculation_window="monthly")
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return {"service": svc, "rule": rule}


class TestSLARules:
    async def test_list_rules(self, client: AsyncClient, auth_headers, sample_sla):
        resp = await client.get("/api/v1/sla/rules", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_create_rule(self, client: AsyncClient, auth_headers, db_session):
        h = Host(hostname="sla2-host", status="online", agent_token_id=1)
        db_session.add(h)
        await db_session.commit()
        await db_session.refresh(h)
        svc = Service(name="web-svc", type="http", target="http://localhost", host_id=h.id, status="up", is_active=True)
        db_session.add(svc)
        await db_session.commit()
        await db_session.refresh(svc)

        resp = await client.post("/api/v1/sla/rules", headers=auth_headers, json={
            "service_id": svc.id, "name": "Web SLA", "target_percent": 99.5,
        })
        assert resp.status_code == 200

    async def test_delete_rule(self, client: AsyncClient, auth_headers, sample_sla):
        resp = await client.delete(f"/api/v1/sla/rules/{sample_sla['rule'].id}", headers=auth_headers)
        assert resp.status_code in (200, 204)


class TestSLAStatus:
    async def test_sla_status(self, client: AsyncClient, auth_headers, sample_sla):
        resp = await client.get("/api/v1/sla/status", headers=auth_headers)
        assert resp.status_code == 200

    async def test_sla_violations(self, client: AsyncClient, auth_headers, sample_sla):
        resp = await client.get("/api/v1/sla/violations", headers=auth_headers)
        assert resp.status_code == 200
