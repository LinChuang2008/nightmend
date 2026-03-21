"""ApprovalService 单元测试。"""
import pytest

from app.services.approval_service import ApprovalService


@pytest.mark.asyncio
async def test_approval_service_command_confirm():
    patches: list[tuple[str, dict]] = []

    async def _update(mid: str, patch: dict):
        patches.append((mid, patch))

    service = ApprovalService(_update)
    await service.register("m1", "command_request")
    await service.resolve("m1", "confirm")
    reply = await service.wait_for_reply("m1", timeout=1, timeout_action="expired")

    assert reply["action"] == "confirm"
    assert patches[-1] == ("m1", {"status": "confirmed"})


@pytest.mark.asyncio
async def test_approval_service_ask_user_timeout():
    patches: list[tuple[str, dict]] = []

    async def _update(mid: str, patch: dict):
        patches.append((mid, patch))

    service = ApprovalService(_update)
    await service.register("m2", "ask_user")
    reply = await service.wait_for_reply("m2", timeout=0, timeout_action="expired")

    assert reply["action"] == "expired"
    assert patches[-1] == ("m2", {"status": "expired", "answer": None})
