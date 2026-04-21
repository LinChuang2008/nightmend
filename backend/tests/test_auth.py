"""认证模块测试 — 注册、登录、JWT 刷新、获取当前用户。"""
from httpx import AsyncClient


class TestRegister:
    async def test_register_first_user_is_admin(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "first@test.com", "name": "First", "password": "pass1234"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_register_duplicate_email(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "email": "dup@test.com", "name": "A", "password": "pass1234"
        })
        resp = await client.post("/api/v1/auth/register", json={
            "email": "dup@test.com", "name": "B", "password": "pass4567"
        })
        assert resp.status_code == 409

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email", "name": "Bad", "password": "pass1234"
        })
        assert resp.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient, admin_user):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "admin@test.com", "password": "admin123"
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_login_wrong_password(self, client: AsyncClient, admin_user):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "admin@test.com", "password": "wrong"
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nobody@test.com", "password": "pass"
        })
        assert resp.status_code == 401


class TestRefresh:
    async def test_refresh_token(self, client: AsyncClient):
        reg = await client.post("/api/v1/auth/register", json={
            "email": "refresh@test.com", "name": "R", "password": "pass1234"
        })
        refresh_token = reg.json()["refresh_token"]
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_refresh_invalid_token(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid.token.here"
        })
        assert resp.status_code == 401


class TestMe:
    async def test_get_me(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "admin@test.com"
        assert data["role"] == "admin"

    async def test_get_me_no_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
