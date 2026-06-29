"""系统设置路由测试。"""
from httpx import AsyncClient


class TestSettings:
    async def test_get_settings(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/settings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # 应该有默认配置项
        assert "metrics_retention_days" in data

    async def test_update_settings_admin(self, client: AsyncClient, auth_headers):
        resp = await client.put("/api/v1/settings", headers=auth_headers, json={
            "metrics_retention_days": "30",
        })
        assert resp.status_code == 200

    async def test_update_settings_viewer_forbidden(self, client: AsyncClient, viewer_headers):
        resp = await client.put("/api/v1/settings", headers=viewer_headers, json={
            "metrics_retention_days": "30",
        })
        assert resp.status_code == 403

    async def test_get_settings_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/settings")
        assert resp.status_code == 401
