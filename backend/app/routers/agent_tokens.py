"""
Agent 令牌管理路由 (Agent Token Management Router)

功能说明：提供 NightMend Agent 认证令牌的完整生命周期管理
核心职责：
  - Agent Token 的安全生成和创建（带前缀标识）
  - 令牌列表查询和状态管理
  - 令牌吊销和访问控制
  - 令牌使用情况追踪（最后使用时间）
  - 基于 HMAC-SHA256 哈希的安全存储机制
依赖关系：依赖 AgentToken 数据模型和管理员权限验证
API端点：POST/GET/DELETE /api/v1/agent-tokens

Security Design:
  - 仅管理员可以管理 Agent Token，严格权限控制
  - 令牌使用 HMAC-SHA256 哈希存储，不保存明文
  - 生成的令牌带有 "vop_" 前缀，便于识别和管理
  - 支持令牌吊销而非删除，保留审计追踪
  - 记录创建者和使用情况，支持安全审计

Token Format: vop_<48位十六进制随机字符串>

Author: NightMend Team
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.agent_token import AgentToken
from app.models.user import User
from app.schemas.agent_token import AgentTokenCreate, AgentTokenCreated, AgentTokenResponse

router = APIRouter(prefix="/api/v1/agent-tokens", tags=["agent-tokens"])


def _hash_token(token: str) -> str:
    """
    使用 HMAC-SHA256 计算令牌哈希值 (Calculate Token HMAC-SHA256 Hash)

    将明文令牌通过 HMAC-SHA256 转换为安全的哈希值用于数据库存储。
    相比纯 SHA-256，HMAC 引入密钥可有效抵御彩虹表和预计算攻击。

    Args:
        token: 明文令牌字符串

    Returns:
        str: 令牌的 HMAC-SHA256 哈希值（64位十六进制字符串）

    Security:
        - 使用 HMAC-SHA256 算法，密钥来自 AGENT_TOKEN_HMAC_KEY 配置
        - 即使数据库泄漏，无密钥无法构造有效哈希（防彩虹表攻击）
        - 哈希不可逆，保护令牌安全
        - 数据库中仅存储哈希值，不保存明文
    """
    from app.core.config import settings
    return hmac.new(
        settings.agent_token_hmac_key.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()


@router.post("", response_model=AgentTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_agent_token(
    body: AgentTokenCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建新的 Agent Token (Create New Agent Token)
    
    为 NightMend Agent 生成新的认证令牌，用于 Agent 与服务器的安全通信。
    令牌只在创建时返回一次，后续无法再次获取明文令牌。
    
    Args:
        body: Token 创建请求，包含令牌名称和描述
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        AgentTokenCreated: 创建成功的令牌信息（包含明文令牌）
        
    Raises:
        HTTPException: 403 - 非管理员用户无权创建令牌
        
    Security:
        - 仅限管理员用户创建令牌
        - 使用密码学安全的随机数生成器
        - 令牌明文只在创建时返回一次
        - 数据库仅存储哈希值，保护安全
        
    Token Structure:
        - 前缀: "vop_" (NightMend 标识)
        - 随机部分: 48位十六进制字符串 (192 bits 熵)
        - 总长度: 52字符
        - 示例: vop_a1b2c3d4e5f67890abcdef1234567890abcdef123456
        
    Usage:
        1. 管理员创建令牌并记录明文
        2. 将令牌配置到 Agent 中
        3. Agent 使用令牌进行 API 认证
        4. 服务器验证令牌哈希值
        
    Examples:
        POST /api/v1/agent-tokens
        {
            "name": "生产环境Web服务器Agent",
            "description": "用于web-server-01的监控Agent"
        }
    """
    # 权限检查：仅管理员可以创建 Agent Token
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # 生成安全的随机令牌
    # 使用 secrets 模块确保密码学安全的随机性
    raw_token = f"vop_{secrets.token_hex(24)}"  # 24字节 = 192位熵
    token_hash = _hash_token(raw_token)         # 计算哈希值用于存储

    # 创建令牌记录
    agent_token = AgentToken(
        name=body.name,
        token_hash=token_hash,                  # 仅存储哈希值，不保存明文
        token_prefix=raw_token[:8],             # 保存前缀便于管理识别
        created_by=user.id,                     # 记录创建者
    )
    db.add(agent_token)
    await db.commit()
    await db.refresh(agent_token)  # 刷新对象获取数据库生成的字段

    # 构建响应数据，包含明文令牌（仅此次返回）
    data = {
        "id": agent_token.id,
        "name": agent_token.name,
        "token_prefix": agent_token.token_prefix,  # 显示前缀便于识别
        "is_active": agent_token.is_active,        # 令牌状态
        "created_by": agent_token.created_by,      # 创建者ID
        "created_at": agent_token.created_at,      # 创建时间
        "last_used_at": agent_token.last_used_at, # 最后使用时间（初始为空）
        "token": raw_token,                        # 明文令牌（仅创建时返回）
    }
    return AgentTokenCreated(**data)


@router.get("", response_model=list[AgentTokenResponse])
async def list_agent_tokens(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    列出所有 Agent Token (List All Agent Tokens)
    
    查询系统中的所有 Agent Token，用于令牌管理和状态监控。
    不返回明文令牌，仅显示令牌的管理信息和使用状态。
    
    Args:
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        list[AgentTokenResponse]: Agent Token 列表（不包含明文令牌）
        
    Raises:
        HTTPException: 403 - 非管理员用户无权查看令牌列表
        
    Security:
        - 仅限管理员用户查看令牌列表
        - 返回数据不包含明文令牌和哈希值
        - 仅显示令牌前缀便于识别管理
        
    Response Fields:
        - id: 令牌ID
        - name: 令牌名称（管理员设定的描述）
        - token_prefix: 令牌前缀（如 "vop_a1b2"）
        - is_active: 令牌是否有效
        - created_by: 创建者用户ID
        - created_at: 创建时间
        - last_used_at: 最后使用时间（Agent认证时更新）
        
    Use Cases:
        - Agent Token 管理页面展示
        - 监控令牌使用情况和状态
        - 识别需要吊销的过期令牌
        - 审计令牌的创建和使用历史
        
    Note:
        按创建时间倒序排列，最新创建的令牌在前
    """
    # 权限检查：仅管理员可以查看 Agent Token 列表
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # 查询所有 Agent Token，按创建时间倒序排列
    result = await db.execute(
        select(AgentToken).order_by(AgentToken.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_agent_token(
    token_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    吊销 Agent Token (Revoke Agent Token)
    
    将指定的 Agent Token 设置为无效状态，阻止进一步使用。
    采用软删除方式，保留令牌记录用于审计追踪。
    
    Args:
        token_id: 要吊销的令牌ID
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        HTTP 204: 吊销成功（无响应内容）
        
    Raises:
        HTTPException: 403 - 非管理员用户无权吊销令牌
        HTTPException: 404 - 指定的令牌不存在
        
    Security:
        - 仅限管理员用户可以吊销令牌
        - 使用软删除（设置 is_active=False）而非硬删除
        - 保留令牌记录便于安全审计和问题追踪
        
    Impact:
        - 被吊销的令牌立即失效，Agent 将无法认证
        - 使用被吊销令牌的 Agent 需要更新为新的有效令牌
        - 令牌记录保留在数据库中，包含使用历史
        
    Business Scenarios:
        - 安全事件响应：令牌可能泄漏时立即吊销
        - Agent 下线：服务器退役时清理对应令牌
        - 定期轮换：按安全策略定期更新令牌
        - 权限回收：移除不再需要的访问权限
        
    Examples:
        DELETE /api/v1/agent-tokens/123
        
    Note:
        吊销后的令牌仍会在令牌列表中显示，但 is_active 为 false
    """
    # 权限检查：仅管理员可以吊销 Agent Token
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # 查询指定的令牌是否存在
    result = await db.execute(select(AgentToken).where(AgentToken.id == token_id))
    agent_token = result.scalar_one_or_none()
    if not agent_token:
        raise HTTPException(status_code=404, detail="Token not found")

    # 软删除：设置为无效状态而非删除记录
    agent_token.is_active = False
    await db.commit()  # 提交状态更新
