"""通知模板路由测试。"""
import pytest
from httpx import AsyncClient
from app.models.notification_template import NotificationTemplate


@pytest.fixture
async def sample_template(db_session):
    t = NotificationTemplate(
        name="Default Alert", channel_type="webhook",
        body_template="Alert: {title} - {severity}", is_default=True,
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


class TestNotificationTemplates:
    async def test_list_templates(self, client: AsyncClient, auth_headers, sample_template):
        resp = await client.get("/api/v1/notification-templates", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_create_template(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/notification-templates", headers=auth_headers, json={
            "name": "Custom", "channel_type": "email",
            "body_template": "Alert: {title}", "subject_template": "[NightMend] {severity}",
        })
        assert resp.status_code in (200, 201)

    async def test_update_template(self, client: AsyncClient, auth_headers, sample_template):
        resp = await client.put(f"/api/v1/notification-templates/{sample_template.id}",
                                headers=auth_headers, json={"name": "Updated"})
        assert resp.status_code == 200

    async def test_delete_template(self, client: AsyncClient, auth_headers, sample_template):
        resp = await client.delete(f"/api/v1/notification-templates/{sample_template.id}",
                                   headers=auth_headers)
        assert resp.status_code in (200, 204)
