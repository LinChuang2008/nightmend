"""菜单设置 Schema。"""
from pydantic import BaseModel, Field


class MenuSettingResponse(BaseModel):
    hidden_keys: list[str] = Field(default_factory=list)


class MenuSettingUpdate(BaseModel):
    hidden_keys: list[str] = Field(default_factory=list)

