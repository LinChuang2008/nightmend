"""用户管理 CRUD + RBAC 测试。"""
from httpx import AsyncClient


class TestUserList:
    async def test_admin_can_list_users(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200
        assert "items" in resp.json()

    async def test_viewer_cannot_list_users(self, client: AsyncClient, viewer_headers):
        resp = await client.get("/api/v1/users", headers=viewer_headers)
        assert resp.status_code == 403

    async def test_no_auth_rejected(self, client: AsyncClient):
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 401


class TestUserCreate:
    async def test_admin_create_user(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/users", headers=auth_headers, json={
            "email": "new@test.com", "name": "New", "password": "pass123", "role": "operator"
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "operator"

    async def test_create_duplicate_email(self, client: AsyncClient, auth_headers):
        await client.post("/api/v1/users", headers=auth_headers, json={
            "email": "dup2@test.com", "name": "A", "password": "p", "role": "viewer"
        })
        resp = await client.post("/api/v1/users", headers=auth_headers, json={
            "email": "dup2@test.com", "name": "B", "password": "p", "role": "viewer"
        })
        assert resp.status_code == 409

    async def test_create_invalid_role(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/users", headers=auth_headers, json={
            "email": "bad@test.com", "name": "Bad", "password": "p", "role": "superadmin"
        })
        assert resp.status_code == 400


class TestUserGetUpdateDelete:
    async def test_get_user(self, client: AsyncClient, auth_headers, admin_user):
        resp = await client.get(f"/api/v1/users/{admin_user.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@test.com"

    async def test_get_nonexistent_user(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/users/99999", headers=auth_headers)
        assert resp.status_code == 404

    async def test_update_user(self, client: AsyncClient, auth_headers, admin_user):
        resp = await client.put(f"/api/v1/users/{admin_user.id}", headers=auth_headers, json={
            "name": "Updated Admin"
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Admin"

    async def test_delete_user(self, client: AsyncClient, auth_headers, db_session):
        from app.models.user import User
        from app.core.security import hash_password
        u = User(email="del@test.com", name="Del", hashed_password=hash_password("p"), role="viewer")
        db_session.add(u)
        await db_session.commit()
        await db_session.refresh(u)
        resp = await client.delete(f"/api/v1/users/{u.id}", headers=auth_headers)
        assert resp.status_code == 204
