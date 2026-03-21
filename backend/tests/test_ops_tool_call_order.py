"""回归测试：load_skill 不应打断 tool_call/tool_result 协议顺序。"""
import asyncio
import json

import pytest

from app.services.ops_agent_loop import OpsAgentLoop


@pytest.mark.asyncio
async def test_load_skill_keeps_tool_protocol_order(monkeypatch):
    loop = OpsAgentLoop("sess-order", 1)
    loop._context = [{"role": "system", "content": "sys"}]

    # mock 持久化方法，避免依赖真实数据库
    async def _noop_save(*args, **kwargs):
        return "msg-1"

    monkeypatch.setattr(loop, "_save_message", _noop_save)
    monkeypatch.setattr(loop, "_get_session", lambda: None)
    monkeypatch.setattr(loop, "_compact_context", lambda: asyncio.sleep(0))

    # 第一轮触发 load_skill，第二轮结束
    round_idx = {"n": 0}

    async def fake_call_api_stream():
        round_idx["n"] += 1
        if round_idx["n"] == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": "tc-load-skill",
                        "type": "function",
                        "function": {
                            "name": "load_skill",
                            "arguments": json.dumps({"skill_name": "docker-troubleshoot"}),
                        },
                    }
                ],
            }
        else:
            yield {"type": "text_delta", "delta": "done"}

    monkeypatch.setattr(loop, "_call_api_stream", fake_call_api_stream)

    async for _ in loop.run("check"):
        pass

    assistant_idx = None
    tool_idx = None
    system_idx_after = None
    for i, msg in enumerate(loop._context):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            assistant_idx = i
        if msg.get("role") == "tool" and msg.get("tool_call_id") == "tc-load-skill":
            tool_idx = i
        if msg.get("role") == "system" and i > 0 and "已加载技能" in (msg.get("content") or ""):
            system_idx_after = i

    assert assistant_idx is not None
    assert tool_idx is not None
    assert system_idx_after is not None
    assert assistant_idx < tool_idx < system_idx_after
