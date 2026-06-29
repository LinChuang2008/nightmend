"""Prometheus Exporter 一键安装脚本分发端点。

两种消费模式：
  1. UI 交互：GET /api/v1/prom/exporters — 列出支持的 exporter 元数据（dropdown 用）
  2. 安装执行：GET /api/v1/prom/install-script/{exporter_type} — 返回纯文本 bash 脚本
     用户可以：
        - 直接 curl 下来看；
        - 或 "curl -fsSL <url>?token=... | sudo bash"（生产建议先看再跑）

为什么不代为 SSH 执行：
    install 涉及 useradd / systemd unit 写入 / bind 1024+ 端口，runbook 白名单不允许，
    也不该允许——NightMend 不做供应链节点。脚本透明让客户自己拿去跑是最小惊讶原则。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.core.deps import get_current_user, get_operator_user
from app.models.user import User
from app.services.exporter_provisioning import (
    ExporterType,
    build_one_liner,
    generate_install_script,
    list_supported_exporters,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prom", tags=["prom-exporters"])


class ExporterDescriptor(BaseModel):
    type: str
    name: str
    default_port: int
    default_version: str
    description: str


class InstallScriptResponse(BaseModel):
    script: str = Field(..., description="完整 bash 脚本内容，可直接保存为 .sh 运行")
    size_bytes: str
    exporter_type: str


@router.get("/exporters", response_model=list[ExporterDescriptor])
async def list_exporters(_user: User = Depends(get_current_user)):
    """列出所有支持的 exporter + 默认元数据，UI dropdown 用。"""
    return list_supported_exporters()


@router.get("/install-script/{exporter_type}")
async def install_script_plain(
    exporter_type: ExporterType,
    version: str | None = Query(None, description="覆盖默认版本；不填走 NightMend 测试过的 default"),
    arch: str = Query("amd64", description="目标主机 CPU 架构"),
    listen_port: int | None = Query(None, ge=1024, le=65535, description="自定义监听端口"),
    _user: User = Depends(get_operator_user),
):
    """返回纯文本 install 脚本；Content-Type 是 text/x-shellscript，便于 curl | bash。"""
    try:
        script = generate_install_script(
            exporter_type,
            version=version,
            arch=arch,
            listen_port=listen_port,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=script,
        media_type="text/x-shellscript",
        headers={
            "Content-Disposition": f'attachment; filename="install-{exporter_type}.sh"',
            "X-NightMend-Exporter": exporter_type,
        },
    )


@router.get("/install-script/{exporter_type}/json", response_model=InstallScriptResponse)
async def install_script_json(
    exporter_type: ExporterType,
    version: str | None = Query(None),
    arch: str = Query("amd64"),
    listen_port: int | None = Query(None, ge=1024, le=65535),
    _user: User = Depends(get_operator_user),
):
    """UI 复制按钮用：JSON 包装 + size 统计。"""
    try:
        payload = build_one_liner(
            exporter_type,
            version=version,
            arch=arch,
            listen_port=listen_port,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return payload
