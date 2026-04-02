"""
内置告警规则种子数据模块 (Built-in Alert Rules Seed Data Module)

功能描述 (Description):
    NightMend 系统的预定义告警规则初始化器，确保系统启动后具备基本的监控能力。
    提供开箱即用的核心告警规则，覆盖常见的运维监控场景。
    
核心功能 (Core Features):
    1. 内置规则定义 (Built-in Rules Definition) - 预定义5类核心告警规则
    2. 自动初始化 (Auto Initialization) - 应用启动时自动种入数据库
    3. 幂等操作 (Idempotent Operation) - 重复执行不会产生重复数据
    4. 零配置监控 (Zero-config Monitoring) - 用户无需手动配置基础告警
    
内置告警类型 (Built-in Alert Types):
    1. CPU使用率过高 - 主机CPU超过90%持续5分钟
    2. 内存使用率过高 - 主机内存超过90%持续5分钟  
    3. 磁盘使用率过高 - 主机磁盘超过95%立即告警
    4. 主机离线 - 心跳丢失立即告警
    5. 服务不可用 - 健康检查失败立即告警
    
技术特性 (Technical Features):
    - 数据库幂等：检查规则是否已存在，避免重复插入
    - 内置标记：is_builtin字段区分系统内置规则和用户自定义规则
    - 灵活配置：阈值、持续时间等参数可后续通过界面调整
    - 分级告警：warning和critical两个级别，便于优先级处理
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertRule

# 内置告警规则定义列表 (Built-in Alert Rules Definition List)
# 覆盖运维监控的核心场景，提供开箱即用的基础监控能力
BUILTIN_RULES = [
    # 1. CPU使用率监控规则 (CPU Usage Rate Monitoring Rule)
    # 场景：检测主机CPU资源压力，预防性能瓶颈
    {
        "name": "CPU 使用率过高",
        "name_en": "High CPU Usage",
        "description": "CPU 使用率超过阈值持续一段时间",
        "severity": "warning",           # 警告级别：给运维团队缓冲时间处理
        "metric": "cpu_percent",         # 监控指标：CPU使用率百分比
        "operator": ">",                 # 比较操作符：大于阈值触发
        "threshold": 90.0,               # 告警阈值：90%，预留性能缓冲
        "duration_seconds": 300,         # 持续时间：5分钟，避免短暂峰值误报
        "target_type": "host",           # 目标类型：主机级别监控
        "is_builtin": True,              # 内置规则标记，区分用户自定义规则
    },
    # 2. 内存使用率监控规则 (Memory Usage Rate Monitoring Rule)
    # 场景：检测内存资源不足，预防OOM和交换区频繁使用
    {
        "name": "内存使用率过高",
        "name_en": "High Memory Usage",
        "description": "内存使用率超过阈值",
        "severity": "warning",           # 警告级别：内存不足影响性能但不立即崩溃
        "metric": "memory_percent",      # 监控指标：内存使用率百分比
        "operator": ">",                 # 比较操作符：大于阈值触发
        "threshold": 90.0,               # 告警阈值：90%，预防OOM
        "duration_seconds": 300,         # 持续时间：5分钟，确认内存压力持续存在
        "target_type": "host",           # 目标类型：主机级别监控
        "is_builtin": True,              # 内置规则标记
    },

    # 3. 磁盘使用率监控规则 (Disk Usage Rate Monitoring Rule)
    # 场景：检测存储空间不足，预防应用崩溃和数据丢失
    {
        "name": "磁盘使用率过高",
        "name_en": "High Disk Usage",
        "description": "磁盘使用率超过阈值",
        "severity": "critical",          # 严重级别：磁盘满可能导致服务停止
        "metric": "disk_percent",        # 监控指标：磁盘使用率百分比
        "operator": ">",                 # 比较操作符：大于阈值触发
        "threshold": 95.0,               # 告警阈值：95%，紧急清理阈值
        "duration_seconds": 0,           # 持续时间：0秒立即告警，磁盘满风险高
        "target_type": "host",           # 目标类型：主机级别监控
        "is_builtin": True,              # 内置规则标记
    },
    # 4. 主机离线监控规则 (Host Offline Monitoring Rule)
    # 场景：检测主机连通性，识别硬件故障或网络中断
    {
        "name": "主机离线",
        "name_en": "Host Offline",
        "description": "主机心跳丢失",
        "severity": "critical",          # 严重级别：主机离线影响所有运行服务
        "metric": "host_offline",        # 监控指标：主机离线状态标识
        "operator": "==",                # 比较操作符：等于1表示离线
        "threshold": 1.0,                # 告警阈值：1表示离线状态
        "duration_seconds": 0,           # 持续时间：0秒立即告警，连通性问题需快速响应
        "target_type": "host",           # 目标类型：主机级别监控
        "is_builtin": True,              # 内置规则标记
    },

    # 5. 服务不可用监控规则 (Service Unavailable Monitoring Rule)
    # 场景：检测应用服务健康状态，识别服务故障
    {
        "name": "服务不可用",
        "name_en": "Service Unavailable",
        "description": "服务健康检查失败",
        "severity": "critical",          # 严重级别：服务不可用直接影响业务
        "metric": "service_down",        # 监控指标：服务下线状态标识
        "operator": "==",                # 比较操作符：等于1表示服务不可用
        "threshold": 1.0,                # 告警阈值：1表示服务下线状态
        "duration_seconds": 0,           # 持续时间：0秒立即告警，业务影响需快速处理
        "target_type": "service",        # 目标类型：服务级别监控
        "is_builtin": True,              # 内置规则标记
    },
]


async def seed_builtin_rules(session: AsyncSession):
    """
    内置告警规则种入器 (Built-in Alert Rules Seeder)
    
    功能描述:
        将预定义的内置告警规则写入数据库，确保系统具备基本监控能力。
        使用幂等操作，重复执行不会产生重复数据。
        
    Args:
        session: 异步数据库会话，用于执行数据库操作
        
    执行逻辑:
        1. 查询数据库中已存在的内置规则
        2. 对比预定义规则列表，识别缺失的规则
        3. 仅插入不存在的规则，避免重复
        4. 批量提交所有新增规则
        
    调用时机:
        - 应用初始化启动时
        - 数据库迁移后
        - 系统升级后的种子数据同步
        
    幂等保证:
        通过规则名称去重，确保多次执行不会产生重复数据
    """
    # 1. 查询现有内置规则 (Query Existing Built-in Rules)
    # 获取数据库中所有标记为内置的告警规则
    result = await session.execute(
        select(AlertRule).where(AlertRule.is_builtin == True)  # noqa: E712
    )
    existing = {r.name for r in result.scalars().all()}  # 构建已存在规则名称集合

    # 2. 增量插入缺失规则 (Incremental Insert Missing Rules)
    # 遍历预定义规则，仅插入数据库中不存在的规则
    for rule_data in BUILTIN_RULES:
        if rule_data["name"] not in existing:
            # 创建新的告警规则对象并添加到会话
            session.add(AlertRule(**rule_data))

    # 3. 批量提交变更 (Batch Commit Changes)
    # 一次性提交所有新增规则，提高性能和一致性
    await session.commit()
