"""
数据库监控目标 Schema。
"""
from pydantic import BaseModel, Field


class DatabaseTargetBase(BaseModel):
    host_id: int
    name: str = Field(min_length=1, max_length=255)
    db_type: str = Field(default="postgres", max_length=20)
    db_host: str = Field(default="localhost", min_length=1, max_length=255)
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(default="", max_length=255)
    username: str = Field(default="", max_length=255)
    password: str = Field(default="", max_length=512)
    interval_sec: int = Field(default=60, ge=15, le=3600)
    connect_timeout_sec: int = Field(default=10, ge=1, le=120)
    is_active: bool = True
    extra_config: dict | None = None


class DatabaseTargetCreate(DatabaseTargetBase):
    pass


class DatabaseTargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    db_type: str | None = Field(default=None, max_length=20)
    db_host: str | None = Field(default=None, min_length=1, max_length=255)
    db_port: int | None = Field(default=None, ge=1, le=65535)
    db_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=512)
    interval_sec: int | None = Field(default=None, ge=15, le=3600)
    connect_timeout_sec: int | None = Field(default=None, ge=1, le=120)
    is_active: bool | None = None
    extra_config: dict | None = None


class DatabaseTargetOut(BaseModel):
    id: int
    host_id: int
    host_name: str
    name: str
    db_type: str
    db_host: str
    db_port: int
    db_name: str
    username: str
    has_password: bool
    interval_sec: int
    connect_timeout_sec: int
    is_active: bool
    extra_config: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AgentDatabaseTargetOut(BaseModel):
    id: int
    name: str
    db_type: str
    db_host: str
    db_port: int
    db_name: str
    username: str
    password: str
    interval_sec: int
    connect_timeout_sec: int
    is_active: bool
    extra_config: dict | None = None
