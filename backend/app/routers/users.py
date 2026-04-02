"""
用户管理路由 (User Management Router)

功能说明：提供完整的用户生命周期管理，包括 CRUD 操作和密码重置
核心职责：
  - 用户信息的增删改查（仅限管理员操作）
  - 用户角色管理（admin/operator/viewer）
  - 密码重置和安全控制
  - 特殊账号保护（demo 账号不可编辑删除）
  - 完整的审计日志记录（操作追踪）
依赖关系：依赖 User 数据模型、审计服务和安全模块
API端点：GET /me, GET/POST/PUT/DELETE /api/v1/users, PUT /api/v1/users/{id}/password

Author: NightMend Team
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_admin_user, get_current_user
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserOut, UserListResponse, PasswordReset
from app.services.audit import log_audit

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息 (Get current logged-in user info)"""
    return current_user


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    获取用户列表 (Get Users List)
    
    分页查询系统中的所有用户，用于用户管理页面展示。
    支持用户信息的统一查看，方便管理员进行用户管理操作。
    
    Args:
        page: 页码，从1开始
        page_size: 每页用户数量，限制1-100个用户
        db: 数据库会话
        admin: 当前管理员用户（权限校验）
        
    Returns:
        UserListResponse: 包含用户列表、总数和分页信息的响应
        
    Security:
        - 仅限 admin 角色用户访问（通过 get_admin_user 依赖校验）
        - 返回数据排除敏感信息（密码哈希等）
        
    Examples:
        GET /api/v1/users?page=1&page_size=10
    """
    # 获取用户总数，用于分页计算
    total = (await db.execute(select(func.count(User.id)))).scalar()
    
    # 分页查询用户列表，按 ID 升序排列
    result = await db.execute(
        select(User).order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()
    
    # 构建响应数据，使用 UserOut 模型过滤敏感字段
    return UserListResponse(
        items=[UserOut.model_validate(u) for u in users],  # 排除 hashed_password 等敏感字段
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    创建新用户 (Create New User)
    
    管理员创建新的系统用户，支持三种角色权限分配。
    包含完整的数据验证、安全控制和审计日志记录。
    
    Args:
        data: 用户创建数据，包含邮箱、姓名、密码、角色
        request: HTTP 请求对象，用于获取客户端IP
        db: 数据库会话
        admin: 当前管理员用户
        
    Returns:
        UserOut: 创建成功的用户信息（排除密码）
        
    Raises:
        HTTPException: 400 - 角色值无效
        HTTPException: 409 - 邮箱已被注册
        
    Security:
        - 仅限管理员操作
        - 密码自动加密存储
        - 邮箱唯一性校验
        - 完整审计日志记录
        
    Business Rules:
        - 支持三种角色：admin（管理员）、operator（操作员）、viewer（观察者）
        - 邮箱作为唯一标识，不可重复
    """
    # 验证用户角色的有效性
    if data.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="角色必须为 admin / operator / viewer")

    # 检查邮箱唯一性，防止重复注册
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="邮箱已被注册")

    # 创建新用户对象
    user = User(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),  # 密码安全加密存储
        role=data.role,
    )
    db.add(user)
    await db.flush()  # 刷新获取用户 ID，用于审计日志

    # 记录审计日志：谁在什么时候从哪里创建了什么用户
    await log_audit(db, admin.id, "create_user", "user", user.id,
                    json.dumps({"email": data.email, "role": data.role}),
                    request.client.host if request.client else None)
    await db.commit()  # 提交数据库事务
    await db.refresh(user)  # 刷新用户对象获取最新数据
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    获取指定用户详情 (Get User Detail)
    
    根据用户ID获取单个用户的完整信息，用于用户详情页面展示或编辑表单填充。
    
    Args:
        user_id: 要查询的用户ID
        db: 数据库会话
        admin: 当前管理员用户（权限校验）
        
    Returns:
        UserOut: 用户详情信息（排除敏感字段）
        
    Raises:
        HTTPException: 404 - 用户不存在或已被删除
        
    Security:
        - 仅限管理员访问
        - 自动排除密码等敏感信息
        
    Examples:
        GET /api/v1/users/123
    """
    # 根据用户 ID 查询用户记录
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    # 用户不存在时返回 404 错误
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
        
    # 返回用户信息，UserOut 模型会自动排除敏感字段
    return user


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    编辑用户信息 (Update User Information)
    
    管理员编辑用户的基本信息，包括姓名、角色和账号状态。
    支持部分字段更新（patch 语义），包含特殊账号保护机制。
    
    Args:
        user_id: 要编辑的用户ID
        data: 用户更新数据（仅包含要修改的字段）
        request: HTTP 请求对象，用于审计日志
        db: 数据库会话
        admin: 当前管理员用户
        
    Returns:
        UserOut: 更新后的用户信息
        
    Raises:
        HTTPException: 404 - 用户不存在
        HTTPException: 403 - Demo 账号不可编辑（系统保护）
        HTTPException: 400 - 角色值无效
        
    Security:
        - 仅限管理员操作
        - Demo 账号特殊保护
        - 角色修改验证
        - 完整审计日志记录
        
    Business Rules:
        - demo@nightmend.io 为系统保护账号，不可编辑
        - 支持部分字段更新，未提供的字段保持不变
    """
    # 查询要编辑的用户是否存在
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 特殊账号保护：demo 账号不可编辑
    if user.email == "demo@nightmend.io":
        raise HTTPException(status_code=403, detail="Demo 账号不可编辑")

    # 获取要更新的字段，仅包含实际提供的字段（patch 语义）
    updates = data.model_dump(exclude_unset=True)

    # 如果包含角色更新，验证角色值的有效性
    if "role" in updates and updates["role"] not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="角色必须为 admin / operator / viewer")

    # 应用所有字段更新
    for field, value in updates.items():
        setattr(user, field, value)

    # 记录审计日志：记录具体修改了哪些字段
    await log_audit(db, admin.id, "update_user", "user", user_id,
                    json.dumps(updates),  # 记录具体的修改内容
                    request.client.host if request.client else None)
    await db.commit()
    await db.refresh(user)  # 刷新对象获取最新数据
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    删除用户 (Delete User)
    
    管理员删除指定用户，包含多重安全保护机制。
    删除操作是硬删除且不可逆，需要谨慎操作。
    
    Args:
        user_id: 要删除的用户ID
        request: HTTP 请求对象，用于审计日志
        db: 数据库会话
        admin: 当前管理员用户
        
    Returns:
        HTTP 204: 删除成功（无响应内容）
        
    Raises:
        HTTPException: 400 - 管理员不能删除自己（防止系统锁定）
        HTTPException: 404 - 用户不存在
        HTTPException: 403 - Demo 账号不可删除（系统保护）
        
    Security:
        - 仅限管理员操作
        - 自我保护：管理员不能删除自己
        - 系统账号保护：demo 账号不可删除
        - 完整审计日志记录
        
    Business Rules:
        - 硬删除，无法恢复
        - 删除前记录用户邮箱便于审计追踪
    """
    # 安全检查：管理员不能删除自己，防止系统管理员全部被删除
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    # 查询要删除的用户是否存在
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 特殊账号保护：demo 账号不可删除
    if user.email == "demo@nightmend.io":
        raise HTTPException(status_code=403, detail="Demo 账号不可删除")

    # 记录审计日志：删除前记录用户邮箱，便于审计追踪
    await log_audit(db, admin.id, "delete_user", "user", user_id,
                    json.dumps({"email": user.email}),
                    request.client.host if request.client else None)
    
    # 执行硬删除并提交事务
    await db.delete(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="该用户存在关联数据（如审计日志或 AI 操作记录），无法删除。请先禁用该用户。"
        ) from None


@router.put("/{user_id}/password", status_code=status.HTTP_200_OK)
async def reset_password(
    user_id: int,
    data: PasswordReset,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    重置用户密码 (Reset User Password)
    
    管理员为指定用户重置密码，通常用于用户忘记密码或安全事件处理。
    新密码会自动加密存储，并记录审计日志（不记录密码内容）。
    
    Args:
        user_id: 要重置密码的用户ID
        data: 包含新密码的重置请求
        request: HTTP 请求对象，用于审计日志
        db: 数据库会话
        admin: 当前管理员用户
        
    Returns:
        dict: 操作成功的确认消息
        
    Raises:
        HTTPException: 404 - 用户不存在
        HTTPException: 403 - Demo 账号密码不可修改（系统保护）
        
    Security:
        - 仅限管理员操作
        - 密码自动安全加密存储
        - 审计日志记录（不包含密码内容）
        - Demo 账号特殊保护
        
    Business Rules:
        - demo@nightmend.io 密码不可修改，保护演示环境
        - 新密码立即生效，用户下次登录使用新密码
    """
    # 查询要重置密码的用户是否存在
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 特殊账号保护：demo 账号密码不可修改
    if user.email == "demo@nightmend.io":
        raise HTTPException(status_code=403, detail="Demo 账号密码不可修改")

    # 使用安全哈希算法存储新密码
    user.hashed_password = hash_password(data.new_password)

    # 记录审计日志：密码重置操作（不记录密码内容，保护隐私）
    await log_audit(db, admin.id, "reset_password", "user", user_id,
                    None,  # 不记录密码内容，仅记录操作事实
                    request.client.host if request.client else None)
    await db.commit()  # 提交密码更新
    return {"status": "ok"}
