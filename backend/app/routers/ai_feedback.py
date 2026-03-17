"""
AI 反馈管理 API

提供 AI 反馈的 CRUD 操作、统计分析、性能监控等功能。
帮助改进 AI 服务质量，提升用户体验。
"""
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.ai_feedback import AIFeedback, AIFeedbackSummary
from app.schemas.ai_feedback import (
    AIFeedbackCreate,
    AIFeedbackUpdate,
    AIFeedbackResponse,
    AIFeedbackList,
    AIFeedbackStats,
    QuickFeedback,
    FeedbackTrend,
    AIPerformanceReport,
)

router = APIRouter(prefix="/ai-feedback", tags=["ai-feedback"])


@router.post("/", response_model=AIFeedbackResponse)
async def create_feedback(
    feedback_data: AIFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建 AI 反馈"""
    feedback = AIFeedback(
        user_id=current_user.id,
        **feedback_data.dict()
    )
    
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    
    return feedback


@router.post("/quick", response_model=AIFeedbackResponse)
async def quick_feedback(
    feedback_data: QuickFeedback,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """快速反馈（只需评分和有用性）"""
    feedback = AIFeedback(
        user_id=current_user.id,
        session_id=feedback_data.session_id,
        message_id=feedback_data.message_id,
        ai_response=feedback_data.ai_response,
        rating=feedback_data.rating,
        is_helpful=feedback_data.is_helpful,
        feedback_type="quick"
    )
    
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    
    return feedback


@router.get("/", response_model=AIFeedbackList)
async def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    rating: Optional[int] = Query(None, ge=1, le=5),
    feedback_type: Optional[str] = None,
    is_helpful: Optional[bool] = None,
    is_reviewed: Optional[bool] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取反馈列表"""
    query = select(AIFeedback)
    count_query = select(func.count(AIFeedback.id))
    
    if current_user.role != "admin":
        query = query.where(AIFeedback.user_id == current_user.id)
        count_query = count_query.where(AIFeedback.user_id == current_user.id)
    
    if rating is not None:
        query = query.where(AIFeedback.rating == rating)
        count_query = count_query.where(AIFeedback.rating == rating)
    if feedback_type:
        query = query.where(AIFeedback.feedback_type == feedback_type)
        count_query = count_query.where(AIFeedback.feedback_type == feedback_type)
    if is_helpful is not None:
        query = query.where(AIFeedback.is_helpful == is_helpful)
        count_query = count_query.where(AIFeedback.is_helpful == is_helpful)
    if is_reviewed is not None:
        query = query.where(AIFeedback.is_reviewed == is_reviewed)
        count_query = count_query.where(AIFeedback.is_reviewed == is_reviewed)
    
    if start_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        query = query.where(AIFeedback.created_at >= start)
        count_query = count_query.where(AIFeedback.created_at >= start)
    if end_date:
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        query = query.where(AIFeedback.created_at <= end)
        count_query = count_query.where(AIFeedback.created_at <= end)
    
    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(desc(AIFeedback.created_at)).offset(offset).limit(page_size))
    items = result.scalars().all()
    
    return AIFeedbackList(total=total, items=items)


@router.get("/stats", response_model=AIFeedbackStats)
async def get_feedback_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取反馈统计"""
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = select(AIFeedback).where(AIFeedback.created_at >= start_date)
    
    if current_user.role != "admin":
        query = query.where(AIFeedback.user_id == current_user.id)
    
    result = await db.execute(query)
    feedback_list = result.scalars().all()
    
    if not feedback_list:
        return AIFeedbackStats(
            total_feedback=0,
            avg_rating=None,
            helpful_percentage=None,
            rating_distribution={},
            feedback_by_type={},
            avg_response_time_ms=None,
            avg_confidence=None,
            trends={}
        )
    
    # 计算统计数据
    total_feedback = len(feedback_list)
    avg_rating = sum(f.rating for f in feedback_list) / total_feedback
    
    helpful_feedback = [f for f in feedback_list if f.is_helpful is not None]
    helpful_percentage = None
    if helpful_feedback:
        helpful_count = sum(1 for f in helpful_feedback if f.is_helpful)
        helpful_percentage = (helpful_count / len(helpful_feedback)) * 100
    
    # 评分分布
    rating_distribution = {}
    for i in range(1, 6):
        count = sum(1 for f in feedback_list if f.rating == i)
        rating_distribution[str(i)] = count
    
    # 按类型统计
    feedback_by_type = {}
    for f in feedback_list:
        feedback_by_type[f.feedback_type] = feedback_by_type.get(f.feedback_type, 0) + 1
    
    # 响应时间和置信度
    response_times = [f.response_time_ms for f in feedback_list if f.response_time_ms is not None]
    avg_response_time_ms = sum(response_times) / len(response_times) if response_times else None
    
    confidences = [f.ai_confidence for f in feedback_list if f.ai_confidence is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else None
    
    return AIFeedbackStats(
        total_feedback=total_feedback,
        avg_rating=avg_rating,
        helpful_percentage=helpful_percentage,
        rating_distribution=rating_distribution,
        feedback_by_type=feedback_by_type,
        avg_response_time_ms=avg_response_time_ms,
        avg_confidence=avg_confidence,
        trends={}  # TODO: 实现趋势分析
    )


@router.get("/trends", response_model=List[FeedbackTrend])
async def get_feedback_trends(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取反馈趋势数据"""
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = select(
        func.date(AIFeedback.created_at).label('date'),
        func.avg(AIFeedback.rating).label('avg_rating'),
        func.count(AIFeedback.id).label('feedback_count'),
        func.sum(func.case((AIFeedback.is_helpful == True, 1), else_=0)).label('helpful_count')
    ).where(AIFeedback.created_at >= start_date)
    
    if current_user.role != "admin":
        query = query.where(AIFeedback.user_id == current_user.id)
    
    result = await db.execute(query.group_by(func.date(AIFeedback.created_at)).order_by(asc(func.date(AIFeedback.created_at))))
    trends = result.all()
    
    return [
        FeedbackTrend(
            date=trend.date.isoformat(),
            avg_rating=trend.avg_rating,
            feedback_count=trend.feedback_count,
            helpful_count=trend.helpful_count or 0
        ) for trend in trends
    ]


@router.put("/{feedback_id}", response_model=AIFeedbackResponse)
async def update_feedback(
    feedback_id: int,
    feedback_data: AIFeedbackUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新反馈"""
    result = await db.execute(select(AIFeedback).where(AIFeedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="反馈不存在"
        )
    
    # 权限检查：只有反馈创建者或管理员可以修改
    if feedback.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限修改此反馈"
        )
    
    # 更新字段
    update_data = feedback_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(feedback, field, value)
    
    await db.commit()
    await db.refresh(feedback)
    
    return feedback


@router.delete("/{feedback_id}")
async def delete_feedback(
    feedback_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除反馈"""
    result = await db.execute(select(AIFeedback).where(AIFeedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="反馈不存在"
        )
    
    # 权限检查
    if feedback.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限删除此反馈"
        )
    
    await db.delete(feedback)
    await db.commit()
    
    return {"message": "反馈删除成功"}


@router.get("/report", response_model=AIPerformanceReport)
async def get_performance_report(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取 AI 性能报告（管理员功能）"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    days = days_map[period]
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    result = await db.execute(select(AIFeedback).where(AIFeedback.created_at >= start_date))
    feedback_list = result.scalars().all()
    
    if not feedback_list:
        return AIPerformanceReport(
            period=period,
            total_interactions=0,
            feedback_rate=0.0,
            satisfaction_score=0.0,
            improvement_suggestions=[],
            common_issues=[],
            top_rated_responses=[]
        )
    
    # 计算指标
    total_feedback = len(feedback_list)
    # TODO: 获取实际交互总数以计算反馈率
    total_interactions = total_feedback * 3  # 假设反馈率 33%
    feedback_rate = (total_feedback / total_interactions) * 100
    
    satisfaction_score = sum(f.rating for f in feedback_list) / total_feedback * 20  # 转换为 100 分制
    
    # 改进建议
    improvement_suggestions = []
    low_rated = [f for f in feedback_list if f.rating <= 2]
    if len(low_rated) > total_feedback * 0.2:  # 低评分超过 20%
        improvement_suggestions.append("低评分反馈较多，需要改进 AI 回答质量")
    
    slow_responses = [f for f in feedback_list if f.response_time_ms and f.response_time_ms > 5000]
    if len(slow_responses) > total_feedback * 0.3:  # 慢响应超过 30%
        improvement_suggestions.append("响应时间较慢，需要优化 AI 推理性能")
    
    # 常见问题（基于反馈文本）
    common_issues = []
    for f in feedback_list:
        if f.feedback_text and f.rating <= 3:
            common_issues.append({
                "issue": f.feedback_text[:100],
                "rating": f.rating,
                "count": 1  # TODO: 实现文本聚类分析
            })
    
    # 高评分回答
    top_rated = [f for f in feedback_list if f.rating >= 4][:5]
    top_rated_responses = [
        {
            "response": f.ai_response[:200] + "..." if len(f.ai_response) > 200 else f.ai_response,
            "rating": f.rating,
            "question": f.user_question[:100] if f.user_question else None
        } for f in top_rated
    ]
    
    return AIPerformanceReport(
        period=period,
        total_interactions=total_interactions,
        feedback_rate=feedback_rate,
        satisfaction_score=satisfaction_score,
        improvement_suggestions=improvement_suggestions,
        common_issues=common_issues[:10],  # 限制返回数量
        top_rated_responses=top_rated_responses
    )