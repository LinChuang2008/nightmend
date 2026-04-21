"""Agent Token 管理路由测试。"""
from httpx import AsyncClient


class TestAgentTokens:
    async def test_create_token_admin(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/agent-tokens", headers=auth_headers, json={
            "name": "Production Agent",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Production Agent"
        assert "token" in data  # 首次返回明文 token
        assert data["token"].startswith("vop_")

    async def test_create_token_viewer_forbidden(self, client: AsyncClient, viewer_headers):
        resp = await client.post("/api/v1/agent-tokens", headers=viewer_headers, json={
            "name": "Test",
        })
        assert resp.status_code == 403

    async def test_list_tokens(self, client: AsyncClient, auth_headers):
        await client.post("/api/v1/agent-tokens", headers=auth_headers, json={"name": "T1"})
        resp = await client.get("/api/v1/agent-tokens", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_revoke_token(self, client: AsyncClient, auth_headers):
        create_resp = await client.post("/api/v1/agent-tokens", headers=auth_headers, json={"name": "ToRevoke"})
        token_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/agent-tokens/{token_id}", headers=auth_headers)
        assert resp.status_code == 204
