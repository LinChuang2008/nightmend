"""
Demo API 路由 — Autopilot Demo 状态查询

提供 Demo 模式状态接口，供前端判断是否在 Demo 模式下运行。
"""
from fastapi import APIRouter

from app.core.config import settings
from app.services.demo_orchestrator import get_demo_status

router = APIRouter(prefix="/api/v1/demo", tags=["Demo"])


@router.get("/status")
async def demo_status():
    """返回当前 Demo 模式状态和阶段。"""
    if not settings.demo_mode:
        return {"demo_mode": False}
    return await get_demo_status()
