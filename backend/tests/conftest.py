"""
VigilOps 测试基础配置

提供 SQLite in-memory 异步数据库、mock Redis、FastAPI TestClient 等通用 fixture。
所有测试使用隔离的 SQLite 数据库，不依赖外部 PostgreSQL/Redis。
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 必须在导入 app 之前设置环境变量，避免真实连接
import os
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["REDIS_HOST"] = "localhost"
os.environ["AI_API_KEY"] = "test-key"
os.environ["MEMORY_ENABLED"] = "false"

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
import app.core.redis as redis_module
from app.core.redis import get_redis
from app.models.user import User


# ── SQLite 异步引擎 ──────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

from sqlalchemy import event, BigInteger, Integer

engine = create_async_engine(TEST_DATABASE_URL, echo=False)

# Register PostgreSQL functions for SQLite compatibility
@event.listens_for(engine.sync_engine, "connect")
def _register_sqlite_functions(dbapi_conn, connection_record):
    """Register date_trunc and extract for SQLite so PG-specific SQL works in tests."""
    import sqlite3
    from datetime import datetime as _dt

    def _date_trunc(part, value):
        if value is None:
            return None
        if isinstance(value, str):
            # Try parsing ISO format
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    value = _dt.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            else:
                return value
        part = part.lower()
        if part in ("hour", "hours"):
            return value.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        elif part in ("day", "days"):
            return value.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        elif part in ("minute", "minutes"):
            return value.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d %H:%M:%S") if hasattr(value, 'strftime') else str(value)

    def _extract(field, value):
        if value is None:
            return None
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    value = _dt.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            else:
                return 0
        field = field.lower()
        if field == "epoch":
            return value.timestamp()
        elif field == "hour":
            return value.hour
        elif field == "day":
            return value.day
        elif field == "month":
            return value.month
        elif field == "year":
            return value.year
        return 0

    dbapi_conn.create_function("date_trunc", 2, _date_trunc)
    dbapi_conn.create_function("extract", 2, _extract)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# SQLite 不支持 BigInteger autoincrement，编译时替换为 Integer
from sqlalchemy.ext.compiler import compiles
@compiles(BigInteger, "sqlite")
def compile_big_int_sqlite(type_, compiler, **kw):
    return "INTEGER"

# SQLite 不支持 JSONB 类型，编译时替换为 JSON
from sqlalchemy.dialects.postgresql import JSONB
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


# ── Mock Redis ────────────────────────────────────────────────────────
class FakeRedis:
    """内存级 Redis 模拟，支持基本 get/set/delete 操作。"""
    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, **kwargs) -> None:
        self._store[key] = value

    async def setex(self, key: str, time: int, value: str) -> None:
        self._store[key] = value

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    async def incr(self, key: str) -> int:
        val = int(self._store.get(key, "0")) + 1
        self._store[key] = str(val)
        return val

    async def expire(self, key: str, time: int) -> None:
        pass

    async def publish(self, channel: str, message: str) -> None:
        pass

    async def close(self) -> None:
        pass


fake_redis = FakeRedis()


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """全局事件循环，避免跨 fixture 循环问题。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """每个测试前创建所有表，测试后清空。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """提供一个干净的数据库会话。"""
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """提供配置好依赖覆盖的异步 HTTP 测试客户端。"""
    from app.main import app

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    # Patch redis_client directly so any code calling get_redis() gets fake_redis
    original_redis_client = redis_module.redis_client
    redis_module.redis_client = fake_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    redis_module.redis_client = original_redis_client


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """创建一个管理员用户。"""
    user = User(
        email="admin@test.com",
        name="Admin",
        hashed_password=hash_password("admin123"),
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    """创建一个只读用户。"""
    user = User(
        email="viewer@test.com",
        name="Viewer",
        hashed_password=hash_password("viewer123"),
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user: User) -> str:
    """管理员的 JWT access token。"""
    return create_access_token(str(admin_user.id))


@pytest_asyncio.fixture
async def viewer_token(viewer_user: User) -> str:
    """只读用户的 JWT access token。"""
    return create_access_token(str(viewer_user.id))


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict:
    """管理员认证头。"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def viewer_headers(viewer_token: str) -> dict:
    """只读用户认证头。"""
    return {"Authorization": f"Bearer {viewer_token}"}
