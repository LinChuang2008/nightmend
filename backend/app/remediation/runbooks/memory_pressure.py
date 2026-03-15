"""
VigilOps 自动修复 Runbook - 内存压力缓解
VigilOps Automatic Remediation Runbook - Memory Pressure Relief

这是一个内存压力缓解脚本，用于处理内存使用率过高或即将发生 OOM 的告警。
This is a memory pressure relief script for handling high memory usage or impending OOM alerts.

适用场景 (Applicable Scenarios):
- 系统内存使用率超过 80% (System memory usage exceeds 80%)
- 收到 OOM (Out of Memory) 警告 (Received OOM warning)
- Swap 使用率异常升高 (Abnormal increase in swap usage)
- 应用程序内存泄漏导致的内存压力 (Memory pressure caused by application memory leaks)

缓解策略 (Relief Strategy):
1. 诊断优先：首先分析内存使用情况和主要消耗者
2. 安全释放：清理可安全释放的系统缓存
3. 非破坏性：不杀死进程，不影响正在运行的应用
4. 可恢复性：清理的缓存可以自动重建

技术原理 (Technical Principles):
- Page Cache 清理：释放文件系统缓存，不影响数据安全
- 缓存同步：确保脏页被写入磁盘后再清理
- 内存监控：通过系统工具识别内存使用模式

风险评估 (Risk Assessment):
- 风险等级：CONFIRM（需要确认）
- 原因：虽然操作相对安全，但涉及系统核心内存管理
- 影响：可能短暂影响系统性能（缓存重建）
- 可逆性：清理的缓存会在后续访问中自动重建

注意事项 (Important Notes):
- drop_caches 是安全操作，但会暂时影响 I/O 性能
- 此 Runbook 不会终止进程，如需更激进的内存回收需要人工介入
- 效果通常是临时的，需要配合应用层面的内存优化

预期效果 (Expected Results):
- 释放 100MB - 2GB 的系统缓存（取决于系统负载）
- 降低内存使用率 5-20%
- 为系统运行争取缓冲时间
- 提供内存使用诊断信息

作者：VigilOps Team
版本：v1.0
风险等级：MEDIUM
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

# 内存压力缓解 Runbook 定义 (Memory Pressure Relief Runbook Definition)
RUNBOOK = RunbookDefinition(
    # 基本信息 (Basic Information)
    name="memory_pressure",
    description="Relieve memory pressure by clearing caches and identifying memory hogs",
    
    # 匹配规则 (Matching Rules)
    match_alert_types=["high_memory", "oom_warning", "memory_usage_high", "swap_usage_high", "memory_percent"],  # 内存相关告警
    match_keywords=["memory", "OOM", "out of memory", "swap", "ram", "内存"],  # 内存关键词
    
    # 安全设置 (Safety Settings)
    risk_level=RiskLevel.CONFIRM,  # 需要确认：涉及系统内存管理，需要人工审批
    
    # 内存缓解命令序列 (Memory Relief Command Sequence)
    # 先诊断再处理的安全策略
    commands=[
        # 第1步：诊断当前内存使用情况 (Step 1: Diagnose current memory usage)
        RunbookStep(
            description="Show current memory usage",
            command="free -h",  # 显示人类可读的内存使用情况
            timeout_seconds=10
        ),
        
        # 第2步：识别内存消耗大户 (Step 2: Identify top memory consumers)
        RunbookStep(
            description="List top memory consumers",
            command="ps aux --sort=-%mem | head -10",  # 按内存使用率排序，显示前10个进程
            timeout_seconds=10
        ),
        
        # 第3步：同步文件系统缓冲区 (Step 3: Sync filesystem buffers)
        RunbookStep(
            description="Sync filesystem buffers",
            command="sync",  # 将脏页写入磁盘，确保数据安全
            timeout_seconds=15  # 给足时间完成同步操作
        ),
        
        # 第4步：安全清理页面缓存 (Step 4: Safely drop page cache)
        RunbookStep(
            description="Drop page cache (safe, recoverable)",
            command="echo 3 > /proc/sys/vm/drop_caches",  # 清理页面缓存、目录项缓存、inode缓存
            timeout_seconds=10
            # 注：echo 3 含义：
            # 1 - 清理页面缓存 (page cache)
            # 2 - 清理目录项和inode (dentries and inodes)  
            # 3 - 清理所有缓存 (all caches) = 1 + 2
        ),
    ],
    
    # 验证命令 (Verification Commands)
    # 检查内存清理效果
    verify_commands=[
        RunbookStep(
            description="Check memory after cleanup",
            command="free -h",  # 再次检查内存使用情况，对比清理效果
            timeout_seconds=10
        ),
    ],
    
    # 冷却时间：10分钟，避免频繁清理缓存影响性能 (Cooldown: 10 minutes, avoid frequent cache clearing affecting performance)
    cooldown_seconds=600,
)
