"""
Agent 更新管理模块。

提供:
- 构建 Agent wheel 包
- 下载 wheel 包
- 触发 Agent 更新
"""
import asyncio
import logging
import os
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.agent_token import AgentToken
from app.routers.agent import verify_agent_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent-updates", tags=["agent-updates"])

# wheel 包存储目录（挂载到宿主机 ./backend/agent_wheels，容器重建后不丢失）
WHEEL_STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "agent_wheels")
WHEEL_STORAGE_DIR = os.path.normpath(WHEEL_STORAGE_DIR)
os.makedirs(WHEEL_STORAGE_DIR, exist_ok=True)


def get_agent_dir() -> str:
    """获取 Agent 源代码目录"""
    # 尝试常见的路径
    possible_paths = [
        "/app/agent",  # Docker 容器内路径（通过 volume 映射）
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "agent"),  # 相对路径
        "/opt/nightmend/agent",  # 可选：系统安装路径
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None


def build_wheel_package(version: str = None) -> dict:
    """
    构建 Agent wheel 包。
    版本号始终从 pyproject.toml 读取，忽略传入的 version 参数，
    确保目录名、包名、版本号三者一致。
    """
    agent_dir = get_agent_dir()
    if not agent_dir:
        return {"success": False, "message": "Agent source directory not found"}

    pyproject_path = os.path.join(agent_dir, "pyproject.toml")
    if not os.path.exists(pyproject_path):
        return {"success": False, "message": "pyproject.toml not found"}

    # 始终从 pyproject.toml 读取真实版本号
    import toml
    with open(pyproject_path, "r") as f:
        data = toml.loads(f.read())
    real_version = data.get("project", {}).get("version", "0.0.0")

    output_dir = os.path.join(WHEEL_STORAGE_DIR, real_version)
    os.makedirs(output_dir, exist_ok=True)

    try:
        result = subprocess.run(
            ["python", "-m", "build", "--wheel", "--outdir", output_dir, agent_dir],
            capture_output=True,
            text=True,
            cwd=agent_dir
        )

        if result.returncode != 0:
            logger.error(f"Failed to build wheel: {result.stderr}")
            return {"success": False, "message": f"Build failed: {result.stderr}"}

        wheel_files = [f for f in os.listdir(output_dir) if f.endswith(".whl")]
        if not wheel_files:
            return {"success": False, "message": "No wheel file generated"}

        wheel_path = os.path.join(output_dir, wheel_files[0])
        download_url = f"/api/v1/agent-updates/download/{real_version}/{os.path.basename(wheel_path)}"

        logger.info(f"Built wheel package: {wheel_path}")
        return {
            "success": True,
            "wheel_path": wheel_path,
            "version": real_version,
            "download_url": download_url
        }

    except Exception as e:
        logger.error(f"Failed to build wheel package: {e}")
        return {"success": False, "message": str(e)}


@router.post("/build/{version}")
async def build_agent_wheel(
    version: str,
    _user: User = Depends(get_current_user)
):
    """
    构建 Agent wheel 包 (管理员接口)

    Args:
        version: 要构建的版本号
    """
    result = build_wheel_package(version)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])

    logger.info(f"Wheel package built successfully: {result['wheel_path']}")
    return {
        "success": True,
        "message": "Build successful",
        "wheel_path": result.get("wheel_path"),
        "version": result.get("version", version),
        "download_url": result.get("download_url"),
    }


@router.get("/list")
async def list_agent_versions(
    agent_token: AgentToken = Depends(verify_agent_token)
):
    """
    获取可用的 Agent 版本列表 (Agent 接口)

    返回格式：
    {
        "versions": [
            {
                "version": "0.1.0",
                "wheel_files": ["nightmend_agent-0.1.0-py3-none-any.whl"]
            }
        ]
    }
    """
    versions = []

    if not os.path.exists(WHEEL_STORAGE_DIR):
        return {"versions": []}

    for version_dir in os.listdir(WHEEL_STORAGE_DIR):
        version_path = os.path.join(WHEEL_STORAGE_DIR, version_dir)
        if os.path.isdir(version_path):
            wheel_files = [
                f for f in os.listdir(version_path)
                if f.endswith(".whl")
            ]
            if wheel_files:
                versions.append({
                    "version": version_dir,
                    "wheel_files": wheel_files
                })

    # 按版本号降序排序
    versions.sort(key=lambda x: x["version"], reverse=True)

    return {"versions": versions}


@router.get("/download/{version}/{filename}")
async def download_agent_wheel(
    version: str,
    filename: str,
    agent_token: AgentToken = Depends(verify_agent_token)
):
    """
    下载 Agent wheel 包 (Agent 接口)

    Args:
        version: 版本号
        filename: wheel 文件名
    """
    from fastapi.responses import FileResponse
    from pathlib import Path as PathLib

    # 验证 version 和 filename 安全性（防止路径遍历）
    if ".." in version or "/" in version or "\\" in version:
        raise HTTPException(status_code=400, detail="Invalid version")
    if ".." in filename or "/" in filename or "\\" in filename or not filename.endswith(".whl"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    wheel_path = PathLib(WHEEL_STORAGE_DIR) / version / filename
    # 确保解析后的路径仍在存储目录内
    if not wheel_path.resolve().is_relative_to(PathLib(WHEEL_STORAGE_DIR).resolve()):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not wheel_path.exists():
        raise HTTPException(status_code=404, detail="Wheel file not found")

    return FileResponse(
        path=str(wheel_path),
        filename=filename,
        media_type="application/octet-stream"
    )


