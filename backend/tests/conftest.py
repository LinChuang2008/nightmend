"""
NightMend 测试基础配置

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
from app.services.auth_session import generate_session_id, set_active_session
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
class FakePipeline:
    """FakeRedis 的 pipeline 模拟，支持链式调用并在 execute() 时返回结果列表。"""

    def __init__(self, store: dict):
        self._store = store
        self._commands: list = []

    def get(self, key: str) -> "FakePipeline":
        self._commands.append(("get", key))
        return self

    def set(self, key: str, value: str, ex: int | None = None, **kwargs) -> "FakePipeline":
        self._commands.append(("set", key, value))
        return self

    def incr(self, key: str) -> "FakePipeline":
        self._commands.append(("incr", key))
        return self

    def expire(self, key: str, time: int) -> "FakePipeline":
        self._commands.append(("expire", key, time))
        return self

    def delete(self, *keys: str) -> "FakePipeline":
        self._commands.append(("delete", *keys))
        return self

    def zadd(self, key: str, mapping: dict) -> "FakePipeline":
        self._commands.append(("zadd", key, mapping))
        return self

    def zremrangebyscore(self, key: str, min_score, max_score) -> "FakePipeline":
        self._commands.append(("zremrangebyscore", key, min_score, max_score))
        return self

    def zcard(self, key: str) -> "FakePipeline":
        self._commands.append(("zcard", key))
        return self

    async def execute(self) -> list:
        results = []
        for cmd in self._commands:
            op = cmd[0]
            if op == "get":
                results.append(self._store.get(cmd[1]))
            elif op == "set":
                self._store[cmd[1]] = cmd[2]
                results.append(True)
            elif op == "incr":
                val = int(self._store.get(cmd[1], "0")) + 1
                self._store[cmd[1]] = str(val)
                results.append(val)
            elif op == "expire":
                results.append(True)
            elif op == "delete":
                for k in cmd[1:]:
                    self._store.pop(k, None)
                results.append(len(cmd) - 1)
            elif op == "zadd":
                key, mapping = cmd[1], cmd[2]
                zset = self._store.setdefault(f"__zset__{key}", {})
                for member, score in mapping.items():
                    zset[member] = score
                results.append(len(mapping))
            elif op == "zremrangebyscore":
                key, min_s, max_s = cmd[1], cmd[2], cmd[3]
                zset = self._store.get(f"__zset__{key}", {})
                to_remove = [m for m, s in zset.items() if min_s <= s <= max_s]
                for m in to_remove:
                    del zset[m]
                results.append(len(to_remove))
            elif op == "zcard":
                zset = self._store.get(f"__zset__{cmd[1]}", {})
                results.append(len(zset))
            else:
                results.append(None)
        self._commands.clear()
        return results


class FakePubSub:
    """内存级 Redis PubSub 模拟。"""
    def __init__(self):
        self._channels: set[str] = set()
        self._queue: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, *channels: str) -> None:
        for ch in channels:
            self._channels.add(ch)

    async def unsubscribe(self, *channels: str) -> None:
        for ch in channels:
            self._channels.discard(ch)

    async def get_message(self, ignore_subscribe_messages: bool = False, timeout: float = 0) -> dict | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

    async def aclose(self) -> None:
        self._channels.clear()


class FakeRedis:
    """内存级 Redis 模拟，支持基本 get/set/delete/pipeline/sorted-set 操作。"""
    def __init__(self):
        self._store: dict[str, str] = {}
        self._subscribers: list["FakePubSub"] = []

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self._store)

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

    async def publish(self, channel: str, message: str) -> int:
        for sub in self._subscribers:
            if channel in sub._channels:
                await sub._queue.put({"type": "message", "channel": channel, "data": message.encode() if isinstance(message, str) else message})
        return len(self._subscribers)

    def pubsub(self) -> "FakePubSub":
        ps = FakePubSub()
        self._subscribers.append(ps)
        return ps

    async def close(self) -> None:
        pass

    async def zadd(self, key: str, mapping: dict) -> int:
        zset = self._store.setdefault(f"__zset__{key}", {})
        for member, score in mapping.items():
            zset[member] = score
        return len(mapping)

    async def zremrangebyscore(self, key: str, min_score, max_score) -> int:
        zset = self._store.get(f"__zset__{key}", {})
        to_remove = [m for m, s in zset.items() if min_score <= s <= max_score]
        for m in to_remove:
            del zset[m]
        return len(to_remove)

    async def zcard(self, key: str) -> int:
        zset = self._store.get(f"__zset__{key}", {})
        return len(zset)


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
    """每个测试前创建所有表，测试后清空。同时重置 FakeRedis 存储。"""
    fake_redis._store.clear()
    # 确保 redis_module.redis_client 始终指向 fake_redis，
    # 以便 token fixture 中的 set_active_session 能正确写入
    original_redis_client = redis_module.redis_client
    redis_module.redis_client = fake_redis
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    redis_module.redis_client = original_redis_client


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
    """管理员的 JWT access token（含 session_id）。"""
    sid = generate_session_id()
    await set_active_session(admin_user.id, sid)
    return create_access_token(str(admin_user.id), session_id=sid)


@pytest_asyncio.fixture
async def viewer_token(viewer_user: User) -> str:
    """只读用户的 JWT access token（含 session_id）。"""
    sid = generate_session_id()
    await set_active_session(viewer_user.id, sid)
    return create_access_token(str(viewer_user.id), session_id=sid)


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict:
    """管理员认证头。"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def viewer_headers(viewer_token: str) -> dict:
    """只读用户认证头。"""
    return {"Authorization": f"Bearer {viewer_token}"}
