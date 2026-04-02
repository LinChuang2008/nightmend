"""
NightMend 自动修复 Runbook - 日志轮转
NightMend Automatic Remediation Runbook - Log Rotation

这是一个日志轮转修复脚本，用于处理日志文件过大导致的磁盘空间问题。
This is a log rotation remediation script for handling disk space issues caused by oversized log files.

适用场景 (Applicable Scenarios):
- 单个日志文件超过设定大小阈值 (Single log file exceeds size threshold)
- 日志增长过快导致磁盘压力 (Rapid log growth causing disk pressure)
- 日志轮转机制失效 (Log rotation mechanism failure)
- 应用程序产生异常大量日志 (Applications generating abnormally large logs)

解决方案 (Solution):
- 强制执行系统日志轮转配置
- 识别并处理超大日志文件
- 保持日志数据的完整性和可追溯性
- 释放磁盘空间同时保留重要日志信息

技术原理 (Technical Principles):
- 利用 logrotate 系统工具进行标准化日志管理
- 遵循系统已配置的轮转策略
- 安全的日志文件处理，不会丢失重要信息

风险评估 (Risk Assessment):
- 风险等级：AUTO（自动执行）
- 安全性：高，使用系统标准工具
- 数据影响：按配置策略保留重要日志
- 可逆性：轮转后的日志文件仍然可访问

预期效果 (Expected Results):
- 大型日志文件被压缩和归档
- 释放显著的磁盘空间
- 恢复正常的日志轮转机制
- 维持系统日志的可管理性

作者：NightMend Team
版本：v1.0
风险等级：LOW
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

# 日志轮转 Runbook 定义 (Log Rotation Runbook Definition)
RUNBOOK = RunbookDefinition(
    # 基本信息 (Basic Information)
    name="log_rotation",
    description="Force log rotation and truncate oversized log files",
    
    # 匹配规则 (Matching Rules)
    match_alert_types=["log_file_too_large", "disk_full", "log_growth"],  # 日志相关问题
    match_keywords=["log", "rotation", "large file", "growing fast"],     # 日志大小关键词
    
    # 安全设置 (Safety Settings)
    risk_level=RiskLevel.AUTO,  # 自动执行：日志轮转是标准系统维护操作
    
    # 日志轮转命令序列 (Log Rotation Command Sequence)
    commands=[
        # 第1步：识别大型日志文件 (Step 1: Identify large log files)
        RunbookStep(
            description="Find large log files",
            command="find /var/log -type f -size +100M -exec ls -lh {} +",  # 查找超过100MB的日志文件
            timeout_seconds=30
            # 参数说明：
            # -type f: 只查找文件
            # -size +100M: 大小超过100MB
            # -exec ls -lh {} +: 以人类可读格式显示文件详情
        ),
        
        # 第2步：强制执行日志轮转 (Step 2: Force log rotation)
        RunbookStep(
            description="Force logrotate on all configs",
            command="logrotate -f /etc/logrotate.conf",  # 强制执行所有日志轮转配置
            timeout_seconds=60
            # 参数说明：
            # -f: 强制轮转，即使轮转条件尚未满足
            # /etc/logrotate.conf: 系统主配置文件，包含所有日志轮转规则
        ),
    ],
    
    # 验证命令 (Verification Commands)
    verify_commands=[
        RunbookStep(
            description="Check log directory size after rotation",
            command="du -sh /var/log",  # 检查日志目录总大小
            timeout_seconds=10
            # du -sh: 显示目录的总大小，s=总结，h=人类可读
        ),
    ],
    
    # 冷却时间：10分钟，避免过于频繁的日志轮转 (Cooldown: 10 minutes, avoid too frequent log rotation)
    cooldown_seconds=600,
)
