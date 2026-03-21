"""统一审批/问答等待服务。"""
import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


@dataclass
class _PendingApproval:
    request_type: str
    event: asyncio.Event


class ApprovalService:
    """
    统一管理 command_request 与 ask_user 的等待/回复流程。

    request_type:
    - command_request
    - ask_user
    """

    def __init__(
        self,
        update_message_content: Callable[[str, dict[str, Any]], Awaitable[None]],
    ):
        self._update_message_content = update_message_content
        self._pending: dict[str, _PendingApproval] = {}
        self._results: dict[str, dict[str, Any]] = {}

    async def register(self, message_id: str, request_type: str):
        self._pending[message_id] = _PendingApproval(
            request_type=request_type,
            event=asyncio.Event(),
        )
        self._results.pop(message_id, None)

    async def resolve(
        self,
        message_id: str,
        action: str,
        *,
        answer: Optional[str] = None,
        request_type: Optional[str] = None,
    ):
        pending = self._pending.get(message_id)
        resolved_request_type = request_type or (pending.request_type if pending else self._infer_request_type(action, answer))
        patch = self._build_patch(resolved_request_type, action, answer)
        if patch:
            await self._update_message_content(message_id, patch)

        if pending:
            self._results[message_id] = {
                "request_type": resolved_request_type,
                "action": action,
                "answer": answer,
            }
            pending.event.set()

    async def wait_for_reply(
        self,
        message_id: str,
        *,
        timeout: int,
        timeout_action: str,
    ) -> dict[str, Any]:
        pending = self._pending.get(message_id)
        if not pending:
            return {"action": timeout_action}

        try:
            await asyncio.wait_for(pending.event.wait(), timeout=timeout)
            return self._results.pop(message_id, {"action": timeout_action})
        except asyncio.TimeoutError:
            await self.resolve(
                message_id,
                timeout_action,
                request_type=pending.request_type,
            )
            return {"action": timeout_action}
        finally:
            self._pending.pop(message_id, None)
            self._results.pop(message_id, None)

    @staticmethod
    def _infer_request_type(action: str, answer: Optional[str]) -> str:
        if action in ("confirm", "reject"):
            return "command_request"
        if answer is not None or action in ("answer", "answered"):
            return "ask_user"
        return "command_request"

    @staticmethod
    def _build_patch(request_type: str, action: str, answer: Optional[str]) -> dict[str, Any]:
        if request_type == "command_request":
            if action == "confirm":
                return {"status": "confirmed"}
            if action == "reject":
                return {"status": "rejected"}
            if action == "expired":
                return {"status": "expired"}
            return {}

        if request_type == "ask_user":
            if action in ("answer", "answered"):
                return {"status": "answered", "answer": answer or ""}
            if action == "expired":
                return {"status": "expired", "answer": None}
            return {}

        return {}
