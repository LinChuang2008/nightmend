"""
运维报告路由 (Operations Report Router)

功能说明：提供运维报告的完整生命周期管理，包括查询、生成、查看和删除
核心职责：
  - 运维报告的列表查询和分页展示
  - 单个报告的详情查看
  - 手动触发报告生成（日报、周报）
  - 报告删除管理（仅限管理员）
  - 报告时间段计算和默认值设定
依赖关系：依赖 Report 数据模型和 report_generator 服务
API端点：GET /api/v1/reports, GET /api/v1/reports/{id}, POST /api/v1/reports/generate, DELETE /api/v1/reports/{id}

Author: NightMend Team
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_operator_user
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportResponse, GenerateReportRequest
from app.services.report_generator import generate_report

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

# 东八区时区定义 (China Standard Time)
CST = timezone(timedelta(hours=8))


@router.get("", response_model=dict)
async def list_reports(
    report_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    获取运维报告列表 (Get Operations Reports List)
    
    支持按报告类型筛选和分页查询，主要用于报告管理页面的列表展示。
    报告按创建时间倒序排列，最新生成的报告显示在前面。
    
    Args:
        report_type: 可选的报告类型筛选（如 "daily", "weekly", "monthly"）
        page: 页码，从1开始
        page_size: 每页显示的报告数量，限制1-100条
        db: 数据库会话
        _user: 当前认证用户
        
    Returns:
        dict: 包含报告列表、总数和分页信息的响应对象
        
    Examples:
        GET /api/v1/reports?report_type=weekly&page=1&page_size=10
    """
    # 构建基础查询和计数查询
    q = select(Report)
    count_q = select(func.count(Report.id))

    # 如果指定了报告类型，添加筛选条件
    if report_type:
        q = q.where(Report.report_type == report_type)
        count_q = count_q.where(Report.report_type == report_type)

    # 获取符合条件的总记录数
    total = (await db.execute(count_q)).scalar()
    
    # 添加排序和分页：按创建时间倒序，最新的报告在前面
    q = q.order_by(Report.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    reports = result.scalars().all()

    # 构建响应数据，转换为 JSON 格式便于前端处理
    return {
        "items": [ReportResponse.model_validate(r).model_dump(mode="json") for r in reports],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    获取单个报告详情 (Get Single Report Detail)
    
    根据报告ID获取完整的报告内容，用于报告详情页面展示。
    包含报告的基本信息、生成状态和具体内容数据。
    
    Args:
        report_id: 报告的唯一标识ID
        db: 数据库会话
        _user: 当前认证用户
        
    Returns:
        ReportResponse: 报告详情对象，包含所有字段信息
        
    Raises:
        HTTPException: 404 - 报告不存在或已被删除
        
    Examples:
        GET /api/v1/reports/123
    """
    # 根据 ID 查询报告记录
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    
    # 报告不存在时返回 404 错误
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
        
    # 使用 Pydantic 模型验证并返回报告详情
    return ReportResponse.model_validate(report)


@router.post("/generate", response_model=ReportResponse)
async def trigger_generate(
    req: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    手动触发生成运维报告 (Manually Trigger Report Generation)
    
    允许用户手动生成指定类型和时间段的运维报告。
    报告生成是异步进行的，立即返回"生成中"状态的记录，后台完成数据收集和分析。
    
    支持的报告类型：
    - daily: 日报（默认昨天的数据）
    - weekly: 周报（默认过去7天的数据）
    - monthly: 月报（需指定具体时间段）
    
    Args:
        req: 报告生成请求对象，包含报告类型和可选的时间段
        background_tasks: FastAPI 后台任务管理器（暂未使用）
        db: 数据库会话
        user: 当前认证用户，将记录为报告生成者
        
    Returns:
        ReportResponse: 新创建的报告记录，初始状态为"generating"
        
    Examples:
        POST /api/v1/reports/generate
        {
            "report_type": "weekly",
            "period_start": "2024-01-01T00:00:00Z",
            "period_end": "2024-01-07T23:59:59Z"
        }
    """
    now = datetime.now(CST)  # 获取当前东八区时间

    # 计算报告的时间段范围（使用 naive datetime 以兼容 DB TIMESTAMP WITHOUT TIME ZONE）
    if req.period_start and req.period_end:
        # 如果请求中指定了时间段，移除时区信息
        period_start = req.period_start.replace(tzinfo=None) if req.period_start.tzinfo else req.period_start
        period_end = req.period_end.replace(tzinfo=None) if req.period_end.tzinfo else req.period_end
    elif req.report_type == "weekly":
        # 周报默认取过去 7 天的数据
        period_end = datetime(now.year, now.month, now.day)
        period_start = period_end - timedelta(days=7)
    else:
        # 日报和其他类型默认取昨天的数据
        yesterday = now.date() - timedelta(days=1)
        period_start = datetime(yesterday.year, yesterday.month, yesterday.day)
        period_end = datetime(now.year, now.month, now.day)

    # 调用报告生成服务，记录生成者信息
    report = await generate_report(db, req.report_type, period_start, period_end, generated_by=user.id)
    return ReportResponse.model_validate(report)


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    删除运维报告 (Delete Operations Report)
    
    允许管理员删除不再需要的运维报告，释放存储空间。
    采用硬删除方式，数据删除后无法恢复，需要管理员权限。
    
    Args:
        report_id: 要删除的报告ID
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        dict: 删除成功的确认消息
        
    Raises:
        HTTPException: 403 - 非管理员用户无权删除报告
        HTTPException: 404 - 报告不存在或已被删除
        
    Security:
        仅限 role="admin" 的用户可以执行删除操作
    """
    # 权限检查：仅管理员可删除报告
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除报告")

    # 查询要删除的报告是否存在
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    # 执行删除操作并提交事务
    await db.delete(report)  # 硬删除报告记录
    await db.commit()       # 提交数据库事务确保删除生效
    return {"detail": "报告已删除"}
