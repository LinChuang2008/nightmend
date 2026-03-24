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


class OpsAIConfigResponse(BaseModel):
    id: str
    feature_key: str
    name: str
    base_url: str
    model: str
    max_output_tokens: int
    supports_deep_thinking: bool = False
    deep_thinking_max_tokens: int = 0
    model_context_tokens: int
    allowed_context_tokens: int
    extra_context: str
    has_api_key: bool
    api_key_mask: Optional[str] = None
    is_default: bool = False
    enabled: bool = True


class OpsAIConfigUpdate(BaseModel):
    feature_key: Optional[str] = None
    name: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    max_output_tokens: Optional[int] = None
    supports_deep_thinking: Optional[bool] = None
    deep_thinking_max_tokens: Optional[int] = None
    model_context_tokens: Optional[int] = None
    allowed_context_tokens: Optional[int] = None
    extra_context: Optional[str] = None
    enabled: Optional[bool] = None


class OpsAIConfigImport(BaseModel):
    feature_key: Optional[str] = None
    name: Optional[str] = None
    config: dict[str, Any]


class OpsAIConfigCreate(BaseModel):
    feature_key: str
    name: str
    base_url: str
    model: str
    api_key: Optional[str] = None
    max_output_tokens: int = 4000
    supports_deep_thinking: bool = False
    deep_thinking_max_tokens: int = 0
    model_context_tokens: int = 200000
    allowed_context_tokens: int = 120000
    extra_context: str = ""
    enabled: bool = True
