"""Users 路由深度测试 — CRUD + RBAC + demo账号保护。"""
import pytest
from app.models.user import User
from app.core.security import hash_password


class TestListUsers:
    @pytest.mark.asyncio
    async def test_list_users(self, client, auth_headers):
        resp = await client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, client, auth_headers):
        resp = await client.get("/api/v1/users?page=1&page_size=1", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 1

    @pytest.mark.asyncio
    async def test_list_users_forbidden_for_viewer(self, client, viewer_headers):
        resp = await client.get("/api/v1/users", headers=viewer_headers)
        assert resp.status_code == 403


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_create_user(self, client, auth_headers):
        resp = await client.post("/api/v1/users", json={
            "email": "new@test.com", "name": "New User",
            "password": "password123", "role": "operator",
        }, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["email"] == "new@test.com"
        assert resp.json()["role"] == "operator"

    @pytest.mark.asyncio
    async def test_create_user_invalid_role(self, client, auth_headers):
        resp = await client.post("/api/v1/users", json={
            "email": "bad@test.com", "name": "Bad",
            "password": "pass", "role": "superadmin",
        }, headers=auth_headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_duplicate_email(self, client, auth_headers):
        await client.post("/api/v1/users", json={
            "email": "dup@test.com", "name": "First",
            "password": "pass", "role": "viewer",
        }, headers=auth_headers)
        resp = await client.post("/api/v1/users", json={
            "email": "dup@test.com", "name": "Second",
            "password": "pass", "role": "viewer",
        }, headers=auth_headers)
        assert resp.status_code == 409


class TestGetUser:
    @pytest.mark.asyncio
    async def test_get_user(self, client, auth_headers, admin_user):
        resp = await client.get(f"/api/v1/users/{admin_user.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == admin_user.email

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, client, auth_headers):
        resp = await client.get("/api/v1/users/99999", headers=auth_headers)
        assert resp.status_code == 404


class TestUpdateUser:
    @pytest.mark.asyncio
    async def test_update_user_name(self, client, auth_headers, db_session):
        user = User(email="upd@test.com", name="Before", hashed_password=hash_password("pass"), role="viewer")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resp = await client.put(f"/api/v1/users/{user.id}", json={"name": "After"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    @pytest.mark.asyncio
    async def test_update_user_invalid_role(self, client, auth_headers, db_session):
        user = User(email="role@test.com", name="User", hashed_password=hash_password("pass"), role="viewer")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resp = await client.put(f"/api/v1/users/{user.id}", json={"role": "god"}, headers=auth_headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_demo_forbidden(self, client, auth_headers, db_session):
        user = User(email="demo@nightmend.io", name="Demo", hashed_password=hash_password("pass"), role="admin")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resp = await client.put(f"/api/v1/users/{user.id}", json={"name": "Hacked"}, headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_not_found(self, client, auth_headers):
        resp = await client.put("/api/v1/users/99999", json={"name": "X"}, headers=auth_headers)
        assert resp.status_code == 404


class TestDeleteUser:
    @pytest.mark.asyncio
    async def test_delete_user(self, client, auth_headers, db_session):
        user = User(email="del@test.com", name="Del", hashed_password=hash_password("pass"), role="viewer")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resp = await client.delete(f"/api/v1/users/{user.id}", headers=auth_headers)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_self_forbidden(self, client, auth_headers, admin_user):
        resp = await client.delete(f"/api/v1/users/{admin_user.id}", headers=auth_headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_demo_forbidden(self, client, auth_headers, db_session):
        user = User(email="demo@nightmend.io", name="Demo", hashed_password=hash_password("pass"), role="admin")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resp = await client.delete(f"/api/v1/users/{user.id}", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client, auth_headers):
        resp = await client.delete("/api/v1/users/99999", headers=auth_headers)
        assert resp.status_code == 404


class TestResetPassword:
    @pytest.mark.asyncio
    async def test_reset_password(self, client, auth_headers, db_session):
        user = User(email="pwd@test.com", name="Pwd", hashed_password=hash_password("old"), role="viewer")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resp = await client.put(f"/api/v1/users/{user.id}/password", json={"new_password": "newpass123"}, headers=auth_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_password_demo_forbidden(self, client, auth_headers, db_session):
        user = User(email="demo@nightmend.io", name="Demo", hashed_password=hash_password("pass"), role="admin")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resp = await client.put(f"/api/v1/users/{user.id}/password", json={"new_password": "new"}, headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_reset_password_not_found(self, client, auth_headers):
        resp = await client.put("/api/v1/users/99999/password", json={"new_password": "x"}, headers=auth_headers)
        assert resp.status_code == 404
