"""通知渠道管理测试。"""
import pytest
from httpx import AsyncClient
from app.models.notification import NotificationChannel


@pytest.fixture
async def sample_channel(db_session):
    ch = NotificationChannel(name="Test Webhook", type="webhook",
                             config={"url": "https://example.com/hook"}, is_enabled=True)
    db_session.add(ch)
    await db_session.commit()
    await db_session.refresh(ch)
    return ch


class TestNotificationChannels:
    async def test_list_channels(self, client: AsyncClient, auth_headers, sample_channel):
        resp = await client.get("/api/v1/notification-channels", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_create_channel(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/notification-channels", headers=auth_headers, json={
            "name": "New Webhook", "type": "webhook",
            "config": {"url": "https://hook.example.com"}, "is_enabled": True,
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "New Webhook"

    async def test_update_channel(self, client: AsyncClient, auth_headers, sample_channel):
        resp = await client.put(f"/api/v1/notification-channels/{sample_channel.id}",
                                headers=auth_headers, json={"name": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    async def test_delete_channel(self, client: AsyncClient, auth_headers, sample_channel):
        resp = await client.delete(f"/api/v1/notification-channels/{sample_channel.id}",
                                   headers=auth_headers)
        assert resp.status_code == 204

    async def test_get_nonexistent(self, client: AsyncClient, auth_headers):
        resp = await client.put("/api/v1/notification-channels/99999",
                                headers=auth_headers, json={"name": "X"})
        assert resp.status_code == 404


class TestNotificationLogs:
    async def test_list_notification_logs(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/notification-channels/logs", headers=auth_headers)
        assert resp.status_code == 200
