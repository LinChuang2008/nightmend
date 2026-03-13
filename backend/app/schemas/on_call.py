"""
值班排期模式定义 (On-Call Schedule Schema Definitions)

定义值班排期相关的 API 请求和响应模式，包括数据验证、序列化规则。
提供类型安全的接口定义，确保前后端数据交互的一致性。

Defines API request and response schemas for on-call schedules,
including data validation and serialization rules.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class OnCallGroupBase(BaseModel):
    """值班组基础模式 (On-Call Group Base Schema)"""
    name: str = Field(..., min_length=1, max_length=255, description="值班组名称")
    description: Optional[str] = Field(None, description="值班组描述")
    is_active: bool = Field(True, description="是否激活")


class OnCallGroupCreate(OnCallGroupBase):
    """创建值班组请求模式 (Create On-Call Group Request Schema)"""
    pass


class OnCallGroupUpdate(BaseModel):
    """更新值班组请求模式 (Update On-Call Group Request Schema)"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="值班组名称")
    description: Optional[str] = Field(None, description="值班组描述")
    is_active: Optional[bool] = Field(None, description="是否激活")


class OnCallGroupResponse(OnCallGroupBase):
    """值班组响应模式 (On-Call Group Response Schema)"""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OnCallScheduleBase(BaseModel):
    """值班排期基础模式 (On-Call Schedule Base Schema)"""
    group_id: int = Field(..., description="值班组ID")
    user_id: int = Field(..., description="值班用户ID")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    is_active: bool = Field(True, description="是否激活")


class OnCallScheduleCreate(OnCallScheduleBase):
    """创建值班排期请求模式 (Create On-Call Schedule Request Schema)"""
    pass


class OnCallScheduleUpdate(BaseModel):
    """更新值班排期请求模式 (Update On-Call Schedule Request Schema)"""
    group_id: Optional[int] = Field(None, description="值班组ID")
    user_id: Optional[int] = Field(None, description="值班用户ID")
    start_date: Optional[date] = Field(None, description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期")
    is_active: Optional[bool] = Field(None, description="是否激活")


class OnCallScheduleResponse(OnCallScheduleBase):
    """值班排期响应模式 (On-Call Schedule Response Schema)"""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CurrentOnCallResponse(BaseModel):
    """当前值班响应模式 (Current On-Call Response Schema)"""
    user_id: int = Field(..., description="值班用户ID")
    email: str = Field(..., description="值班用户邮箱")
    group_id: int = Field(..., description="值班组ID")
    group_name: str = Field(..., description="值班组名称")
    schedule_id: int = Field(..., description="排期ID")
    start_date: date = Field(..., description="值班开始日期")
    end_date: date = Field(..., description="值班结束日期")