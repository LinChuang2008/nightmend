"""
系统设置管理路由 (System Settings Management Router)

功能说明：提供 VigilOps 系统配置参数的统一管理，支持动态配置更新
核心职责：
  - 系统配置项的查询和展示（支持默认值回退）
  - 配置参数的批量更新（仅限管理员操作）
  - 配置变更的审计日志记录
  - 内置默认配置项和描述信息管理
  - 新配置项的动态创建和管理
依赖关系：依赖 Setting 数据模型和审计服务
API端点：GET /api/v1/settings, PUT /api/v1/settings

Configuration Categories:
  - metrics_retention_days: 监控数据保留策略
  - alert_check_interval: 告警检查频率控制
  - heartbeat_timeout: 心跳检测超时配置
  - webhook_retry_count: 外部通知重试策略

Author: VigilOps Team
"""

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.deps import get_current_user, get_operator_user, get_admin_user
from app.models.setting import Setting
from app.models.user import User
from app.services.audit import log_audit

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# 系统默认配置项及说明 (System Default Settings and Descriptions)
DEFAULT_SETTINGS = {
    # 数据保留策略配置
    "metrics_retention_days": {
        "value": "90", 
        "description": "指标数据保留天数 - 超过此天数的监控数据将被自动清理"
    },
    # 告警系统配置
    "alert_check_interval": {
        "value": "60", 
        "description": "告警检查间隔(秒) - 系统检查告警规则的频率，影响告警响应速度"
    },
    # 心跳监控配置
    "heartbeat_timeout": {
        "value": "120", 
        "description": "心跳超时时间(秒) - Agent 心跳超时判定，超时后标记为离线状态"
    },
    # 外部通知配置
    "webhook_retry_count": {
        "value": "3", 
        "description": "Webhook 重试次数 - 外部通知失败时的最大重试次数"
    },
}


@router.get("")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_operator_user),
):
    """
    获取所有系统设置 (Get All System Settings)
    
    返回完整的系统配置列表，包括已配置项和默认配置项。
    对于数据库中不存在的配置项，自动使用预定义的默认值补充。
    
    Args:
        db: 数据库会话
        _: 当前认证用户（所有角色都可以查看设置）
        
    Returns:
        dict: 所有系统设置的键值对，格式为 {key: {value, description}}
        
    Features:
        - 自动合并数据库配置和默认配置
        - 提供配置项的描述信息便于理解
        - 确保所有必要的配置项都有值
        - 支持新配置项的动态添加
        
    Response Format:
        {
            "metrics_retention_days": {
                "value": "90",
                "description": "指标数据保留天数"
            },
            "alert_check_interval": {
                "value": "60", 
                "description": "告警检查间隔(秒)"
            }
        }
        
    Use Cases:
        - 系统设置页面的配置展示
        - 其他模块获取配置参数
        - 配置项的完整性检查
    """
    # 查询数据库中的所有配置项
    result = await db.execute(select(Setting))
    settings = {s.key: {"value": s.value, "description": s.description} for s in result.scalars().all()}
    
    # 合并默认配置：为数据库中不存在的配置项补充默认值
    # 这确保了系统在首次部署或添加新配置项时的正常运行
    for key, default in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = default
            
    return settings


@router.put("")
async def update_settings(
    data: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_admin_user),
):
    """
    批量更新系统设置 (Batch Update System Settings)
    
    允许管理员批量修改系统配置参数。
    支持更新现有配置项和创建新的配置项，包含完整的审计日志记录。
    
    Args:
        data: 要更新的配置项字典，格式为 {key: value}
        request: HTTP 请求对象，用于审计日志
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        dict: 更新成功的确认消息
        
    Raises:
        HTTPException: 403 - 非管理员用户无权修改系统设置
        
    Security:
        - 仅限 admin 角色用户操作
        - 完整的审计日志记录配置变更
        - 记录操作者和操作时间
        
    Business Logic:
        - 更新已存在的配置项
        - 为新配置项创建记录，自动添加默认描述
        - 所有配置值统一转换为字符串存储
        - 支持动态配置项的创建和管理
        
    Examples:
        PUT /api/v1/settings
        {
            "metrics_retention_days": "30",
            "alert_check_interval": "120",
            "new_custom_config": "custom_value"
        }
        
    Impact:
        - 配置变更会影响相关系统模块的行为
        - 部分配置可能需要重启相关服务生效
        - 建议在维护窗口进行重要配置的修改
    """
    # 权限检查已由 get_admin_user 依赖完成

    # 安全: 限制可修改的配置项白名单
    ALLOWED_SETTINGS = {
        "metrics_retention_days", "alert_check_interval", "ai_auto_scan",
        "ai_model", "ai_api_url", "notification_max_retries",
        "remediation_auto_mode", "remediation_approval_required",
        "dashboard_refresh_interval", "log_retention_days",
        "session_timeout_minutes", "max_login_attempts",
    }
    for key in data.keys():
        if key not in ALLOWED_SETTINGS:
            raise HTTPException(status_code=400, detail=f"Setting '{key}' is not allowed to be modified")

    # 批量更新配置项
    for key, value in data.items():
        # 查询配置项是否已存在
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        
        if setting:
            # 配置项已存在，更新其值
            setting.value = str(value)  # 统一转换为字符串存储
        else:
            # 配置项不存在，创建新的配置记录
            # 尝试从默认配置中获取描述，如果没有则留空
            desc = DEFAULT_SETTINGS.get(key, {}).get("description", "")
            db.add(Setting(key=key, value=str(value), description=desc))

    # 记录审计日志：谁在什么时候从哪里修改了哪些系统设置
    await log_audit(db, user.id, "update_settings", "settings", None,
                    json.dumps(data),  # 记录具体的配置变更内容
                    request.client.host if request.client else None)
    
    await db.commit()  # 提交所有配置更新
    return {"status": "ok"}
