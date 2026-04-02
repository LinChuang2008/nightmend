"""
审计日志服务 (Audit Log Service)

功能描述 (Description):
    NightMend 统一审计日志记录引擎，提供合规性和安全性保障。
    记录所有关键操作的完整审计轨迹，支持安全审查和问题追溯。
    
核心功能 (Core Features):
    1. 操作记录 (Operation Recording) - 记录用户的所有关键操作
    2. 资源追踪 (Resource Tracking) - 追踪对特定资源的增删改操作
    3. 变更详情 (Change Details) - 记录具体的变更内容和上下文
    4. 来源标识 (Source Identification) - 记录操作来源IP和用户标识
    
审计范围 (Audit Scope):
    - 用户管理：登录、注册、权限变更
    - 配置管理：告警规则、通知渠道、系统设置
    - 运维操作：手动告警处理、服务重启、配置变更
    - 安全事件：登录失败、权限提升、敏感操作
    
合规特性 (Compliance Features):
    - 完整性：所有关键操作都有审计记录
    - 不可篡改：审计日志只允许追加，不允许修改
    - 可追溯：详细记录操作者、时间、内容、结果
    - 长期保存：支持合规要求的长期数据保留
    
技术特性 (Technical Features):
    - 异步记录：不阻塞主业务流程
    - 结构化存储：支持复杂查询和统计分析
    - 统一接口：所有模块使用相同的审计接口
    - 灵活详情：支持JSON格式的任意变更详情记录
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_audit(
    db: AsyncSession,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
):
    """
    统一审计日志记录器 (Unified Audit Log Recorder)
    
    功能描述:
        NightMend 系统的中心化审计日志记录接口，为所有业务模块提供统一的审计能力。
        确保关键操作的完整记录，满足合规性和安全性要求。
        
    Args:
        db: 异步数据库会话，用于持久化审计记录
        user_id: 操作用户ID，标识操作主体
        action: 操作类型标识，建议使用动词格式
               常见操作：login/logout/create/update/delete/view/export
        resource_type: 资源类型，标识操作对象的分类
                      常见类型：user/alert/alert_rule/host/service/notification
        resource_id: 可选，被操作资源的具体ID，用于精确定位
        detail: 可选，JSON格式的详细变更信息，记录前后状态对比
        ip_address: 可选，客户端IP地址，用于来源追踪和安全分析
        
    使用示例:
        # 用户登录审计
        await log_audit(db, user.id, "login", "user", user.id, None, request_ip)
        
        # 告警规则创建审计
        await log_audit(db, current_user.id, "create", "alert_rule", rule.id, 
                       json.dumps(rule.dict()), client_ip)
        
        # 配置更新审计
        await log_audit(db, user.id, "update", "settings", setting.id,
                       json.dumps({"before": old_value, "after": new_value}), ip)
    
    技术实现:
        - 异步记录：使用flush()而非commit()，不干扰主事务
        - 结构化存储：所有字段规范化，便于查询和分析  
        - 时间戳自动：数据库自动记录创建时间
        - 只追加模式：审计日志不允许修改，确保完整性
        
    合规考虑:
        - 完整记录：关键操作必须调用此函数记录
        - 敏感信息：detail字段避免记录密码等敏感数据
        - 数据保留：审计日志应按合规要求长期保存
        - 访问控制：审计日志查看应有适当的权限控制
    """
    # 创建审计日志条目 (Create Audit Log Entry)
    entry = AuditLog(
        user_id=user_id,              # 操作用户标识
        action=action,                # 操作类型（标准化动词）
        resource_type=resource_type,  # 资源类型（标准化名词）
        resource_id=resource_id,      # 具体资源ID（可选）
        detail=detail,                # 变更详情（JSON格式，可选）
        ip_address=ip_address,        # 来源IP地址（可选）
        # timestamp 字段由数据库自动填充当前时间
    )
    
    # 添加到数据库会话 (Add to Database Session)
    db.add(entry)
    
    # 立即刷新到数据库 (Immediate Flush to Database)
    # 使用flush()而非commit()，确保审计记录写入但不影响主事务
    # 这样即使主业务失败回滚，审计记录仍然保留
    await db.flush()
