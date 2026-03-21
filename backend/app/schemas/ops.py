"""运维助手 Pydantic Schema"""
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel


class OpsSessionCreate(BaseModel):
    title: Optional[str] = None


class OpsSessionResponse(BaseModel):
    id: str
    title: Optional[str]
    status: str
    target_host_id: Optional[int]
    token_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OpsMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    msg_type: str
    content: dict[str, Any]
    tool_call_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class OpsSessionDetail(OpsSessionResponse):
    messages: list[OpsMessageResponse] = []


class SkillInfo(BaseModel):
    name: str
    description: str
    triggers: list[str]


class OpsApprovalReply(BaseModel):
    message_id: str
    request_type: Optional[Literal["command_request", "ask_user"]] = None
    action: Literal["confirm", "reject", "answer", "expired", "answered"]
    answer: Optional[str] = None
