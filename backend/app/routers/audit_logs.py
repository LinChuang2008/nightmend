"""
审计日志路由 (Audit Log Router)

功能说明：提供系统审计日志的查询和分析功能，用于安全审计和合规追踪
核心职责：
  - 审计日志的多维度查询和筛选
  - 支持按用户、操作类型、资源类型的精确筛选
  - 分页查询大量审计记录，按时间倒序展示
  - 严格的权限控制（仅管理员可访问）
  - 完整的操作追踪信息展示（操作者、时间、IP、详情）
依赖关系：依赖 AuditLog 数据模型和管理员权限验证
API端点：GET /api/v1/audit-logs

Security Features:
  - 仅限管理员用户访问，保护敏感操作记录
  - 包含 IP 地址追踪，支持异常访问分析
  - 操作详情记录，便于事后审计和问题定位

Audit Categories:
  - 用户管理：create_user, update_user, delete_user, reset_password
  - 系统配置：update_settings
  - 其他关键操作的完整记录

Author: NightMend Team
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_admin_user
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit-logs"])


@router.get("")
async def list_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    查询审计日志列表 (Get Audit Logs List)
    
    提供系统审计日志的多维度查询功能，支持按操作者、操作类型、资源类型进行筛选。
    用于安全审计、合规检查和问题追踪，帮助管理员了解系统的操作历史。
    
    Args:
        user_id: 可选的用户ID筛选，查看特定用户的操作记录
        action: 可选的操作类型筛选（如 "create_user", "update_settings"）
        resource_type: 可选的资源类型筛选（如 "user", "settings"）
        page: 页码，从1开始
        page_size: 每页记录数，限制1-100条
        db: 数据库会话
        admin: 当前管理员用户（权限校验）
        
    Returns:
        dict: 包含审计日志列表、总数和分页信息的响应
        
    Security:
        - 仅限管理员用户访问（通过 get_admin_user 依赖校验）
        - 记录包含敏感操作信息，需要严格权限控制
        
    Filter Examples:
        - GET /api/v1/audit-logs?user_id=123 （查看特定用户的操作）
        - GET /api/v1/audit-logs?action=delete_user （查看删除用户操作）
        - GET /api/v1/audit-logs?resource_type=user （查看用户相关操作）
        - 支持多个筛选条件组合使用
        
    Response Fields:
        - id: 审计日志ID
        - user_id: 操作者用户ID
        - action: 具体操作类型
        - resource_type: 被操作的资源类型
        - resource_id: 被操作的资源ID
        - detail: 操作详情（JSON格式）
        - ip_address: 操作者IP地址
        - created_at: 操作时间（ISO格式）
        
    Use Cases:
        - 安全审计：追踪异常操作和权限变更
        - 合规检查：满足审计要求的操作记录
        - 问题定位：追溯配置变更和用户操作历史
        - 用户行为分析：了解系统使用模式
    """
    # 构建筛选条件列表
    filters = []
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)  # 按操作用户筛选
    if action:
        filters.append(AuditLog.action == action)    # 按操作类型筛选
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)  # 按资源类型筛选

    # 组合筛选条件，如果没有筛选条件则查询所有记录
    where = and_(*filters) if filters else True

    # 获取符合条件的记录总数
    total = (await db.execute(select(func.count(AuditLog.id)).where(where))).scalar()
    
    # 分页查询审计日志，按创建时间倒序（最新操作在前）
    result = await db.execute(
        select(AuditLog).where(where)
        .order_by(AuditLog.created_at.desc())  # 时间倒序，便于查看最新操作
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()

    # 构建审计日志响应数据
    return {
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,                # 操作者ID
                "action": log.action,                  # 操作类型（如 create_user）
                "resource_type": log.resource_type,    # 资源类型（如 user）
                "resource_id": log.resource_id,        # 被操作资源的ID
                "detail": log.detail,                  # 操作详情（JSON字符串）
                "ip_address": log.ip_address,          # 操作者IP地址
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
