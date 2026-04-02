"""
NightMend 自动修复 Runbook - 磁盘空间清理
NightMend Automatic Remediation Runbook - Disk Space Cleanup

这是一个自动化的磁盘空间清理脚本，用于处理磁盘空间不足的告警。
This is an automated disk space cleanup script for handling disk space shortage alerts.

适用场景 (Applicable Scenarios):
- 磁盘使用率超过阈值 (Disk usage exceeds threshold)
- 剩余磁盘空间不足 (Insufficient remaining disk space)
- inode 使用率过高 (High inode usage)
- 临时文件占用过多空间 (Temporary files consuming too much space)

清理策略 (Cleanup Strategy):
1. 安全优先：只清理临时文件和过期日志，不删除用户数据
2. 时间限制：清理超过指定天数的文件，避免误删最近文件
3. 系统友好：使用系统标准命令，兼容性好
4. 效果验证：清理后检查磁盘使用情况

风险评估 (Risk Assessment):
- 风险等级：AUTO（自动执行）
- 安全性：高，只清理临时文件和过期日志
- 影响范围：限制在特定目录，不影响用户数据
- 恢复性：删除的都是可重新生成的文件

预期效果 (Expected Results):
- 释放 /tmp 目录中的过期临时文件
- 清理系统日志和轮转日志文件
- 释放包管理器缓存空间
- 通常可释放 100MB - 10GB 空间（取决于系统使用情况）

作者：NightMend Team
版本：v1.0
风险等级：LOW
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

# 磁盘清理 Runbook 定义 (Disk Cleanup Runbook Definition)
RUNBOOK = RunbookDefinition(
    # 基本信息 (Basic Information)
    name="disk_cleanup",
    description="Clean up disk space by removing temp files, old logs, and package caches",
    
    # 匹配规则 (Matching Rules)
    match_alert_types=["disk_full", "disk_space_low", "disk_usage_high", "disk_percent"],  # 精确匹配的告警类型
    match_keywords=["disk", "space", "full", "no space left", "inode", "磁盘"],    # 关键词匹配（模糊匹配）
    
    # 安全设置 (Safety Settings)
    risk_level=RiskLevel.AUTO,  # 自动执行：磁盘清理是安全的低风险操作
    
    # 修复命令序列 (Remediation Command Sequence)
    # 按安全性从高到低的顺序执行，确保最安全的清理优先
    commands=[
        # 第1步：清理临时文件目录中7天前的文件 (Step 1: Clean temp files older than 7 days)
        RunbookStep(
            description="Remove temp files older than 7 days",
            command="find /tmp -type f -mtime +7 -delete",  # -type f 只删文件，-mtime +7 超过7天
            timeout_seconds=60  # 给足时间处理大量小文件
        ),
        
        # 第2步：清理系统日志，只保留最近3天的 (Step 2: Clean system logs, keep only last 3 days)
        RunbookStep(
            description="Clean old journal logs (keep last 3 days)",
            command="journalctl --vacuum-time=3d",  # systemd 日志清理，保留3天
            timeout_seconds=30
        ),
        
        # 第3步：清理轮转的压缩日志文件 (Step 3: Clean rotated compressed log files)
        RunbookStep(
            description="Remove old rotated logs",
            command="find /var/log -name '*.gz' -mtime +7 -delete",  # 清理7天前的 .gz 压缩日志
            timeout_seconds=60
        ),
        
        # 第4步：清理包管理器缓存 (Step 4: Clean package manager cache)
        RunbookStep(
            description="Clean package manager cache",
            command="apt clean",  # APT 包缓存清理，可以安全重新下载
            timeout_seconds=60
        ),
    ],
    
    # 验证命令 (Verification Commands)
    # 清理完成后检查效果
    verify_commands=[
        RunbookStep(
            description="Check disk usage after cleanup",
            command="df -h /",  # 显示根分区的可读磁盘使用情况
            timeout_seconds=10
        ),
    ],
    
    # 冷却时间：10分钟，避免频繁清理 (Cooldown: 10 minutes, avoid frequent cleanup)
    cooldown_seconds=600,
)
