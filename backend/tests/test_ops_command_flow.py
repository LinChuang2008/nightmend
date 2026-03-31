"""Ops 命令确认与执行回传链路集成测试（模拟调试）。"""
import asyncio
import json

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.host import Host
from app.models.ops_session import OpsSession
from app.models.user import User
from app.services import ops_agent_loop as loop_module
from app.services.ops_agent_loop import OpsAgentLoop
from tests.conftest import TestingSessionLocal


class _FakePubSub:
    def __init__(self, redis_ref):
        self._redis = redis_ref
        self._queue: asyncio.Queue = asyncio.Queue()
        self._channels: set[str] = set()

    async def subscribe(self, *channels: str):
        for ch in channels:
            self._channels.add(ch)
            self._redis._subscribers.setdefault(ch, []).append(self._queue)

    async def unsubscribe(self, *channels: str):
        targets = channels or tuple(self._channels)
        for ch in targets:
            self._channels.discard(ch)
            queues = self._redis._subscribers.get(ch, [])
            self._redis._subscribers[ch] = [q for q in queues if q is not self._queue]

    async def close(self):
        await self.unsubscribe()

    async def listen(self):
        while True:
            item = await self._queue.get()
            yield item


class _FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self.published: list[tuple[str, str]] = []

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, **kwargs):
        self._store[key] = value

    async def delete(self, key: str):
        self._store.pop(key, None)

    async def publish(self, channel: str, message: str):
        self.published.append((channel, message))
        for q in self._subscribers.get(channel, []):
            await q.put({"type": "message", "data": message})
        return len(self._subscribers.get(channel, []))

    def pubsub(self):
        return _FakePubSub(self)


async def _wait_event(events: list[dict], event_name: str, timeout: float = 3.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for ev in events:
            if ev.get("event") == event_name:
                return ev
        await asyncio.sleep(0.02)
    raise TimeoutError(f"wait {event_name} timeout")


@pytest.mark.asyncio
async def test_ops_command_confirm_execute_and_result_back(monkeypatch):
    fake_redis = _FakeRedis()
    async def _fake_get_redis():
        return fake_redis
    monkeypatch.setattr(loop_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(loop_module, "AsyncSessionLocal", TestingSessionLocal)

    # 准备基础数据：用户、目标主机、会话
    async with TestingSessionLocal() as db:
        user = User(
            email="ops-flow@test.com",
            name="OpsFlow",
            hashed_password=hash_password("pass"),
            role="admin",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        host = Host(
            hostname="a-client",
            display_name="A客户机",
            ip_address="10.10.10.8",
            status="online",
            agent_token_id=1,
        )
        db.add(host)
        await db.commit()
        await db.refresh(host)

        session = OpsSession(id="sess-ops-flow", user_id=user.id, title="ops-flow")
        db.add(session)
        await db.commit()

    # mock AI：第一轮只发 execute_command，第二轮给结论文本后结束
    call_round = {"n": 0}

    async def fake_call_api_stream(self):
        call_round["n"] += 1
        if call_round["n"] == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "type": "function",
                        "function": {
                            "name": "execute_command",
                            "arguments": json.dumps(
                                {
                                    "host_id": host.id,
                                    "command": "docker ps --format '{{.Names}} {{.Status}}' | head -n 5",
                                    "timeout": 30,
                                    "reason": "检查 Docker 容器运行状态",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        else:
            yield {"type": "text_delta", "delta": "已收到 A 客户机执行结果，docker 运行正常。"}

    loop = OpsAgentLoop(session.id, user.id)
    monkeypatch.setattr(loop, "_call_api_stream", fake_call_api_stream.__get__(loop, OpsAgentLoop))

    events: list[dict] = []

    async def run_loop():
        async for ev in loop.run("请检查 A 客户机 docker 运行情况", host_id=host.id):
            events.append(ev)

    run_task = asyncio.create_task(run_loop())

    # 1) 等 AI 发起命令确认
    command_req = await _wait_event(events, "command_request")
    message_id = command_req["message_id"]

    # 2) 用户确认执行
    await loop.handle_command_confirm(message_id, "confirm")

    # 3) 验证命令已下发到目标主机 channel
    await asyncio.sleep(0.05)
    cmd_events = [x for x in fake_redis.published if x[0] == f"cmd_to_agent:{host.id}"]
    assert cmd_events, "未向目标主机发布命令"
    cmd_payload = json.loads(cmd_events[-1][1])
    assert cmd_payload["type"] == "exec_command"
    assert "docker ps" in cmd_payload["command"]
    assert cmd_payload["request_id"] == message_id

    # 4) 模拟 Agent 回传执行结果
    await fake_redis.publish(
        f"cmd_result:{session.id}",
        json.dumps(
            {
                "type": "command_result",
                "request_id": message_id,
                "exit_code": 0,
                "stdout": "web-1 Up 2 hours\nredis-1 Up 2 hours",
                "stderr": "",
                "duration_ms": 1234,
            },
            ensure_ascii=False,
        ),
    )

    await asyncio.wait_for(run_task, timeout=5)

    # 5) 验证结果回到 AI loop 并结束
    cmd_result = [e for e in events if e.get("event") == "command_result"]
    assert cmd_result, "未收到 command_result 事件"
    assert cmd_result[-1]["message_id"] == message_id
    assert cmd_result[-1]["exit_code"] == 0
    assert any(e.get("event") == "done" for e in events)

    # 6) 验证目标主机已写入 session（确保“指定 A 客户机”落地）
    async with TestingSessionLocal() as db:
        res = await db.execute(select(OpsSession).where(OpsSession.id == session.id))
        refreshed = res.scalar_one()
        assert refreshed.target_host_id == host.id
