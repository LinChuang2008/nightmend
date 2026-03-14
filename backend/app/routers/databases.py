"""
数据库监控路由 (Database Monitoring Router)

功能说明：提供数据库监控的 REST API 接口，支持多种数据库类型的指标查询和慢查询分析
核心职责：
  - 被监控数据库的列表查询和详情查询
  - 数据库实时指标获取（连接数、QPS、存储空间等）
  - 历史指标数据查询和时间范围筛选
  - 慢查询日志获取和分析（特别是 Oracle 数据库）
依赖关系：依赖 DbMetric 和 MonitoredDatabase 数据模型
API端点：GET /api/v1/databases, GET /api/v1/databases/{id}, GET /api/v1/databases/{id}/metrics, GET /api/v1/databases/{id}/slow-queries

Author: VigilOps Team
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_metric import MonitoredDatabase, DbMetric

router = APIRouter(prefix="/api/v1/databases", tags=["databases"])


def _parse_period(period: str) -> timedelta:
    """
    解析时间周期字符串为 timedelta 对象 (Parse time period string to timedelta)
    
    Args:
        period: 时间周期字符串，支持格式：'1h', '24h', '7d', '30m'
        
    Returns:
        timedelta: 对应的时间间隔对象
        
    Examples:
        _parse_period('1h') -> timedelta(hours=1)
        _parse_period('7d') -> timedelta(days=7)
    """
    p = period.strip().lower()  # 标准化输入，去除空格并转小写
    try:
        if p.endswith("h"):  # 小时单位 (hours)
            return timedelta(hours=int(p[:-1]))
        if p.endswith("d"):  # 天单位 (days)
            return timedelta(days=int(p[:-1]))
        if p.endswith("m"):  # 分钟单位 (minutes)
            return timedelta(minutes=int(p[:-1]))
    except (ValueError, OverflowError) as exc:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"无效的时间周期参数 '{period}'，支持格式示例：1h、7d、30m"
        ) from exc
    raise HTTPException(
        status_code=400,
        detail=f"无效的时间周期参数 '{period}'，支持格式示例：1h、7d、30m"
    )


@router.get("")
async def list_databases(
    host_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    查询所有被监控数据库列表 (List All Monitored Databases)
    
    支持按主机 ID 筛选，返回数据库基础信息和最新指标快照。
    用于数据库监控首页的概览展示。
    
    Args:
        host_id: 可选的主机 ID 筛选条件
        db: 数据库会话
        _user: 当前认证用户（权限校验）
        
    Returns:
        dict: 包含 databases 列表和 total 总数的响应对象
    """
    # 构建基础查询，按更新时间降序排列
    query = select(MonitoredDatabase).order_by(desc(MonitoredDatabase.updated_at))
    if host_id:  # 如果指定了主机ID，添加筛选条件
        query = query.where(MonitoredDatabase.host_id == host_id)
    result = await db.execute(query)
    databases = result.scalars().all()

    items = []
    for mdb in databases:
        # 获取每个数据库的最新一条指标数据 (Latest metrics snapshot)
        latest = await db.execute(
            select(DbMetric)
            .where(DbMetric.database_id == mdb.id)
            .order_by(desc(DbMetric.recorded_at))
            .limit(1)
        )
        metric = latest.scalar_one_or_none()
        
        # 构建数据库基础信息
        item = {
            "id": mdb.id,
            "host_id": mdb.host_id,
            "name": mdb.name,
            "db_type": mdb.db_type,  # 数据库类型：PostgreSQL/MySQL/Oracle
            "status": mdb.status,    # 运行状态：active/inactive/error
            "created_at": mdb.created_at.isoformat() if mdb.created_at else None,
            "updated_at": mdb.updated_at.isoformat() if mdb.updated_at else None,
        }
        
        # 如果有最新指标数据，附加到响应中
        if metric:
            item["latest_metrics"] = {
                "connections_total": metric.connections_total,      # 总连接数
                "connections_active": metric.connections_active,    # 活跃连接数
                "database_size_mb": metric.database_size_mb,        # 数据库大小(MB)
                "slow_queries": metric.slow_queries,                # 慢查询数量
                "tables_count": metric.tables_count,                # 表数量
                "transactions_committed": metric.transactions_committed,    # 已提交事务数
                "transactions_rolled_back": metric.transactions_rolled_back,  # 已回滚事务数
                "qps": metric.qps,                                  # 每秒查询数 (Queries Per Second)
                "tablespace_used_pct": metric.tablespace_used_pct, # 表空间使用率百分比
                "recorded_at": metric.recorded_at.isoformat() if metric.recorded_at else None,
            }
        items.append(item)

    return {"databases": items, "total": len(items)}


@router.get("/{database_id}")
async def get_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    获取单个数据库详情信息 (Get Database Detail)
    
    返回指定数据库的完整信息和最新性能指标，用于数据库详情页面展示。
    
    Args:
        database_id: 数据库 ID
        db: 数据库会话
        _user: 当前认证用户
        
    Returns:
        dict: 数据库详情和最新指标数据
        
    Raises:
        HTTPException: 404 - 数据库不存在
    """
    # 查询指定 ID 的数据库记录
    result = await db.execute(select(MonitoredDatabase).where(MonitoredDatabase.id == database_id))
    mdb = result.scalar_one_or_none()
    if not mdb:  # 数据库不存在，返回 404 错误
        raise HTTPException(status_code=404, detail="Database not found")

    # 获取该数据库的最新指标数据
    latest = await db.execute(
        select(DbMetric).where(DbMetric.database_id == mdb.id).order_by(desc(DbMetric.recorded_at)).limit(1)
    )
    metric = latest.scalar_one_or_none()

    # 构建返回的数据库详情
    data = {
        "id": mdb.id,
        "host_id": mdb.host_id,
        "name": mdb.name,
        "db_type": mdb.db_type,  # 数据库类型
        "status": mdb.status,    # 当前状态
        "created_at": mdb.created_at.isoformat() if mdb.created_at else None,
        "updated_at": mdb.updated_at.isoformat() if mdb.updated_at else None,
    }
    
    # 如果存在最新指标，添加到响应数据中
    if metric:
        data["latest_metrics"] = {
            "connections_total": metric.connections_total,      # 总连接池大小
            "connections_active": metric.connections_active,    # 当前活跃连接
            "database_size_mb": metric.database_size_mb,        # 数据库存储大小
            "slow_queries": metric.slow_queries,                # 慢查询统计
            "tables_count": metric.tables_count,                # 数据表数量
            "transactions_committed": metric.transactions_committed,    # 成功提交事务
            "transactions_rolled_back": metric.transactions_rolled_back,  # 回滚事务数
            "qps": metric.qps,                                  # 查询吞吐量
            "tablespace_used_pct": metric.tablespace_used_pct, # 存储空间使用率
            "recorded_at": metric.recorded_at.isoformat() if metric.recorded_at else None,
        }
    return data


@router.get("/{database_id}/slow-queries")
async def get_slow_queries(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    获取数据库慢查询日志 (Get Database Slow Queries)
    
    返回指定数据库的慢查询详情列表，主要用于 Oracle 数据库性能分析。
    慢查询数据包含 SQL 语句、执行时间、影响行数等关键信息。
    
    Args:
        database_id: 数据库 ID
        db: 数据库会话
        _user: 当前认证用户
        
    Returns:
        dict: 包含 database_id 和 slow_queries 列表的响应
        
    Raises:
        HTTPException: 404 - 数据库不存在
    """
    # 验证数据库是否存在
    result = await db.execute(select(MonitoredDatabase).where(MonitoredDatabase.id == database_id))
    mdb = result.scalar_one_or_none()
    if not mdb:
        raise HTTPException(status_code=404, detail="Database not found")
        
    # 返回慢查询详情，如果没有数据则返回空列表
    # slow_queries_detail 字段存储 JSON 格式的慢查询分析数据
    return {"database_id": database_id, "slow_queries": mdb.slow_queries_detail or []}


@router.get("/{database_id}/metrics")
async def get_database_metrics(
    database_id: int,
    period: str = Query("1h"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    查询数据库历史指标数据 (Get Database Historical Metrics)
    
    根据指定的时间周期返回数据库性能指标的历史数据，用于趋势图表展示。
    支持多种时间粒度：分钟(m)、小时(h)、天(d)。
    
    Args:
        database_id: 数据库 ID
        period: 时间周期，格式如 '1h', '24h', '7d', '30m'
        db: 数据库会话
        _user: 当前认证用户
        
    Returns:
        dict: 包含时间序列指标数据的响应对象
        
    Raises:
        HTTPException: 404 - 数据库不存在
    """
    # 验证数据库是否存在
    result = await db.execute(select(MonitoredDatabase).where(MonitoredDatabase.id == database_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Database not found")

    # 解析时间周期并计算查询起始时间
    delta = _parse_period(period)  # 将字符串转为 timedelta 对象
    since = datetime.now(timezone.utc) - delta  # 计算查询的起始时间点

    # 查询指定时间范围内的所有指标数据，按时间升序排列
    result = await db.execute(
        select(DbMetric)
        .where(DbMetric.database_id == database_id, DbMetric.recorded_at >= since)
        .order_by(DbMetric.recorded_at)  # 按记录时间升序，便于前端绘制时间序列图
    )
    metrics = result.scalars().all()

    # 构建时间序列数据响应
    return {
        "database_id": database_id,
        "period": period,
        "metrics": [
            {
                "connections_total": m.connections_total,      # 连接池总数趋势
                "connections_active": m.connections_active,    # 活跃连接数趋势
                "database_size_mb": m.database_size_mb,        # 存储空间增长趋势
                "slow_queries": m.slow_queries,                # 慢查询数量趋势
                "tables_count": m.tables_count,                # 表数量变化
                "transactions_committed": m.transactions_committed,    # 事务提交率趋势
                "transactions_rolled_back": m.transactions_rolled_back,  # 事务回滚率趋势
                "qps": m.qps,                                  # QPS 吞吐量趋势
                "tablespace_used_pct": m.tablespace_used_pct, # 存储使用率趋势
                "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None,
            }
            for m in metrics
        ],
    }
