"""
值班排期管理路由模块 (On-Call Schedule Management Router)

功能说明：提供值班排期的完整管理接口，包括值班组管理、排期CRUD操作、当前值班查询
核心职责：
  - 值班组的创建、查询、更新、删除操作
  - 值班排期的完整生命周期管理
  - 当前值班人员查询和值班覆盖分析
  - 排期冲突检测和数据一致性保证
依赖关系：依赖SQLAlchemy、JWT认证、审计服务、值班排期业务服务
API端点：CRUD for groups/schedules + current on-call lookup

Author: NightMend Team
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_operator_user
from app.models.on_call import OnCallGroup, OnCallSchedule
from app.models.user import User
from app.schemas.on_call import (
    OnCallGroupCreate, OnCallGroupUpdate, OnCallGroupResponse,
    OnCallScheduleCreate, OnCallScheduleUpdate, OnCallScheduleResponse,
    CurrentOnCallResponse
)
from app.services.on_call_service import OnCallService
from app.services.audit import log_audit

router = APIRouter(prefix="/api/v1/on-call", tags=["on-call"])


# ===== 值班组管理 (On-Call Group Management) =====

@router.get("/groups", response_model=dict)
async def list_on_call_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    值班组列表查询接口 (On-Call Group List Query)
    
    分页查询值班组列表，支持按激活状态筛选。
    
    Args:
        page: 页码，从1开始
        page_size: 每页数量，限制1-100之间
        is_active: 是否激活状态筛选
        db: 数据库会话依赖注入
        _user: 当前登录用户（JWT认证）
    Returns:
        dict: 包含值班组列表、总数、分页信息的响应
    """
    # 构建查询条件
    q = select(OnCallGroup)
    count_q = select(func.count(OnCallGroup.id))
    
    if is_active is not None:
        q = q.where(OnCallGroup.is_active == is_active)
        count_q = count_q.where(OnCallGroup.is_active == is_active)
    
    # 执行查询
    total = (await db.execute(count_q)).scalar()
    q = q.order_by(OnCallGroup.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    groups = result.scalars().all()
    
    return {
        "items": [OnCallGroupResponse.model_validate(g).model_dump(mode="json") for g in groups],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/groups", response_model=OnCallGroupResponse)
async def create_on_call_group(
    group_data: OnCallGroupCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    创建值班组接口 (Create On-Call Group)
    
    创建新的值班组。
    
    Args:
        group_data: 值班组创建数据
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        OnCallGroupResponse: 创建的值班组信息
    """
    # 创建值班组
    db_group = OnCallGroup(**group_data.model_dump())
    db.add(db_group)
    await db.commit()
    await db.refresh(db_group)
    
    # 记录审计日志
    await log_audit(db, user.id, "create_on_call_group", "on_call_group", db_group.id,
                    None, request.client.host if request.client else None)
    
    return db_group


@router.get("/groups/{group_id}", response_model=OnCallGroupResponse)
async def get_on_call_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取单个值班组详情 (Get Single On-Call Group Detail)"""
    result = await db.execute(select(OnCallGroup).where(OnCallGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="On-call group not found")
    return group


@router.put("/groups/{group_id}", response_model=OnCallGroupResponse)
async def update_on_call_group(
    group_id: int,
    group_data: OnCallGroupUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    更新值班组接口 (Update On-Call Group)
    
    更新指定值班组的信息。
    
    Args:
        group_id: 值班组ID
        group_data: 更新数据
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        OnCallGroupResponse: 更新后的值班组信息
    """
    result = await db.execute(select(OnCallGroup).where(OnCallGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="On-call group not found")
    
    # 更新字段
    update_data = group_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)
    
    await db.commit()
    await db.refresh(group)
    
    # 记录审计日志
    await log_audit(db, user.id, "update_on_call_group", "on_call_group", group_id,
                    update_data, request.client.host if request.client else None)
    
    return group


@router.delete("/groups/{group_id}")
async def delete_on_call_group(
    group_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    删除值班组接口 (Delete On-Call Group)
    
    删除指定的值班组（软删除，设置为非激活状态）。
    
    Args:
        group_id: 值班组ID
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        dict: 删除结果
    """
    result = await db.execute(select(OnCallGroup).where(OnCallGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="On-call group not found")
    
    # 软删除：设置为非激活状态
    group.is_active = False
    await db.commit()
    
    # 记录审计日志
    await log_audit(db, user.id, "delete_on_call_group", "on_call_group", group_id,
                    None, request.client.host if request.client else None)
    
    return {"message": "On-call group deleted successfully"}


# ===== 值班排期管理 (On-Call Schedule Management) =====

@router.get("/schedules", response_model=dict)
async def list_on_call_schedules(
    group_id: Optional[int] = None,
    user_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    值班排期列表查询接口 (On-Call Schedule List Query)
    
    分页查询值班排期，支持多维度筛选。
    
    Args:
        group_id: 值班组ID筛选
        user_id: 值班用户ID筛选
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        page: 页码
        page_size: 每页数量
        db: 数据库会话依赖注入
        _user: 当前登录用户
    Returns:
        dict: 分页的值班排期列表
    """
    # 构建查询条件
    q = select(OnCallSchedule)
    count_q = select(func.count(OnCallSchedule.id))
    
    filters = []
    if group_id:
        filters.append(OnCallSchedule.group_id == group_id)
    if user_id:
        filters.append(OnCallSchedule.user_id == user_id)
    if start_date:
        filters.append(OnCallSchedule.end_date >= start_date)
    if end_date:
        filters.append(OnCallSchedule.start_date <= end_date)
    
    if filters:
        q = q.where(and_(*filters))
        count_q = count_q.where(and_(*filters))
    
    # 执行查询
    total = (await db.execute(count_q)).scalar()
    q = q.order_by(OnCallSchedule.start_date.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    schedules = result.scalars().all()
    
    return {
        "items": [OnCallScheduleResponse.model_validate(s).model_dump(mode="json") for s in schedules],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/schedules", response_model=OnCallScheduleResponse)
async def create_on_call_schedule(
    schedule_data: OnCallScheduleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    创建值班排期接口 (Create On-Call Schedule)
    
    创建新的值班排期，包含冲突检测。
    
    Args:
        schedule_data: 排期创建数据
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        OnCallScheduleResponse: 创建的排期信息
    Raises:
        HTTPException 400: 排期冲突或数据无效
    """
    # 验证开始日期不能晚于结束日期
    if schedule_data.start_date > schedule_data.end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be later than end date")
    
    # 检查排期冲突
    conflicts = await OnCallService.check_schedule_conflicts(
        db, schedule_data.user_id, schedule_data.start_date, schedule_data.end_date
    )
    if conflicts:
        conflict_info = [f"{c.start_date} to {c.end_date}" for c in conflicts[:3]]
        raise HTTPException(
            status_code=400,
            detail=f"Schedule conflicts detected with existing schedules: {', '.join(conflict_info)}"
        )
    
    # 创建排期
    db_schedule = OnCallSchedule(**schedule_data.model_dump())
    db.add(db_schedule)
    await db.commit()
    await db.refresh(db_schedule)
    
    # 记录审计日志
    await log_audit(db, user.id, "create_on_call_schedule", "on_call_schedule", db_schedule.id,
                    None, request.client.host if request.client else None)
    
    return db_schedule


@router.get("/schedules/{schedule_id}", response_model=OnCallScheduleResponse)
async def get_on_call_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取单个值班排期详情 (Get Single On-Call Schedule Detail)"""
    result = await db.execute(select(OnCallSchedule).where(OnCallSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="On-call schedule not found")
    return schedule


@router.put("/schedules/{schedule_id}", response_model=OnCallScheduleResponse)
async def update_on_call_schedule(
    schedule_id: int,
    schedule_data: OnCallScheduleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    更新值班排期接口 (Update On-Call Schedule)
    
    更新指定值班排期，包含冲突检测。
    
    Args:
        schedule_id: 排期ID
        schedule_data: 更新数据
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        OnCallScheduleResponse: 更新后的排期信息
    """
    result = await db.execute(select(OnCallSchedule).where(OnCallSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="On-call schedule not found")
    
    # 更新字段
    update_data = schedule_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(schedule, field, value)
    
    # 如果更新了时间相关字段，需要检查冲突
    if any(field in update_data for field in ["user_id", "start_date", "end_date"]):
        if schedule.start_date > schedule.end_date:
            raise HTTPException(status_code=400, detail="Start date cannot be later than end date")
        
        conflicts = await OnCallService.check_schedule_conflicts(
            db, schedule.user_id, schedule.start_date, schedule.end_date, exclude_schedule_id=schedule_id
        )
        if conflicts:
            raise HTTPException(status_code=400, detail="Schedule conflicts detected")
    
    await db.commit()
    await db.refresh(schedule)
    
    # 记录审计日志
    await log_audit(db, user.id, "update_on_call_schedule", "on_call_schedule", schedule_id,
                    update_data, request.client.host if request.client else None)
    
    return schedule


@router.delete("/schedules/{schedule_id}")
async def delete_on_call_schedule(
    schedule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """删除值班排期接口 (Delete On-Call Schedule)"""
    result = await db.execute(select(OnCallSchedule).where(OnCallSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="On-call schedule not found")
    
    # 软删除：设置为非激活状态
    schedule.is_active = False
    await db.commit()
    
    # 记录审计日志
    await log_audit(db, user.id, "delete_on_call_schedule", "on_call_schedule", schedule_id,
                    None, request.client.host if request.client else None)
    
    return {"message": "On-call schedule deleted successfully"}


# ===== 当前值班查询 (Current On-Call Lookup) =====

@router.get("/current", response_model=Optional[CurrentOnCallResponse])
async def get_current_on_call(
    group_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    获取当前值班人员接口 (Get Current On-Call Personnel)
    
    查询当前正在值班的人员信息。
    
    Args:
        group_id: 可选的值班组ID，如果不提供则查询所有组
        db: 数据库会话依赖注入
        _user: 当前登录用户
    Returns:
        CurrentOnCallResponse: 当前值班人员信息，如果没有则返回None
    """
    try:
        current_on_call = await OnCallService.get_current_on_call_user(db, group_id)
        if current_on_call:
            return CurrentOnCallResponse(**current_on_call)
    except Exception:
        pass
    return None


@router.get("/coverage")
async def get_schedule_coverage(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    获取值班覆盖情况接口 (Get Schedule Coverage)
    
    分析指定时间段内的值班覆盖情况，识别覆盖空档。
    
    Args:
        start_date: 分析开始日期
        end_date: 分析结束日期
        db: 数据库会话依赖注入
        _user: 当前登录用户
    Returns:
        dict: 值班覆盖情况分析结果
    """
    from datetime import timedelta as td
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - td(days=7)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be later than end date")
    
    coverage_info = await OnCallService.get_schedule_coverage(db, start_date, end_date)
    return coverage_info