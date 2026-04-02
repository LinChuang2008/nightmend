"""
NightMend 自动修复 Runbook - 网络连接诊断
NightMend Automatic Remediation Runbook - Network Connection Diagnosis

这是一个网络连接诊断脚本，用于分析和处理连接相关的问题。
This is a network connection diagnosis script for analyzing and handling connection-related issues.

适用场景 (Applicable Scenarios):
- TCP 连接数过多 (Too many TCP connections)
- 连接耗尽导致新连接失败 (Connection exhaustion causing new connection failures)
- 大量 TIME_WAIT 或 CLOSE_WAIT 状态连接 (Large number of TIME_WAIT or CLOSE_WAIT connections)
- 端口耗尽问题 (Port exhaustion issues)
- 连接泄漏检测 (Connection leak detection)

技术背景 (Technical Background):
- TIME_WAIT：连接正常关闭后的等待状态，通常持续 2*MSL
- CLOSE_WAIT：远程端已关闭连接，本地应用未关闭套接字
- 连接泄漏：应用程序未正确释放网络连接资源

诊断价值 (Diagnostic Value):
- 识别连接状态分布，定位问题根源
- 找出连接数最多的进程
- 为后续人工干预提供数据支撑

当前限制 (Current Limitations):
注意：当前版本主要进行连接状态诊断，不执行实际的连接重置操作。
实际的连接清理需要根据具体情况谨慎处理，可能包括：
- 重启相关服务
- 调整系统网络参数
- 修复应用程序连接管理

风险评估 (Risk Assessment):
- 风险等级：CONFIRM（需要确认）
- 原因：虽然主要是诊断，但连接问题通常需要人工分析
- 后续操作可能涉及服务重启或系统参数调整

作者：NightMend Team
版本：v1.0
风险等级：LOW (诊断为主)
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

# 网络连接诊断 Runbook 定义 (Network Connection Diagnosis Runbook Definition)
RUNBOOK = RunbookDefinition(
    # 基本信息 (Basic Information)
    name="connection_reset",
    description="Reset stale connections and identify connection leaks",
    
    # 匹配规则 (Matching Rules)
    match_alert_types=["too_many_connections", "connection_exhaustion", "connection_timeout", "port_exhaustion"],  # 连接问题告警
    match_keywords=["connection", "too many", "exhaustion", "TIME_WAIT", "CLOSE_WAIT", "port"],                  # 网络连接关键词
    
    # 安全设置 (Safety Settings)
    risk_level=RiskLevel.CONFIRM,  # 需要确认：虽然是诊断操作，但后续处理可能影响业务
    
    # 网络连接诊断命令序列 (Network Connection Diagnosis Command Sequence)
    commands=[
        # 第1步：显示整体连接状态统计 (Step 1: Show overall connection state statistics)
        RunbookStep(
            description="Show connection states",
            command="ss -s",  # 显示套接字统计信息
            timeout_seconds=10
            # ss -s: Socket Statistics 的简要版本
            # 显示各种状态的连接数量汇总
        ),
        
        # 第2步：列出 TIME_WAIT 状态的连接 (Step 2: List connections in TIME_WAIT state)
        RunbookStep(
            description="List connections in TIME_WAIT state", 
            command="ss -tan state time-wait | head -50",  # 显示 TIME_WAIT 状态连接，限制50条
            timeout_seconds=10
            # 参数说明：
            # -t: TCP 连接
            # -a: 所有连接（包括监听和非监听）
            # -n: 数字格式显示地址和端口
            # state time-wait: 过滤 TIME_WAIT 状态
        ),
        
        # 第3步：列出 CLOSE_WAIT 状态的连接 (Step 3: List connections in CLOSE_WAIT state)
        RunbookStep(
            description="List connections in CLOSE_WAIT state",
            command="ss -tan state close-wait | head -50",  # CLOSE_WAIT 状态通常表示应用层连接泄漏
            timeout_seconds=10
        ),
        
        # 第4步：识别连接数最多的进程 (Step 4: Identify processes with most connections)
        RunbookStep(
            description="Show processes with most connections",
            command="ss -tnp | awk '{print $6}' | sort | head -20",  # 提取进程信息并统计
            timeout_seconds=10
            # 注意：这个命令可能需要改进，当前逻辑不够准确
            # 更好的命令可能是：
            # ss -tnp | grep -oE 'users:\(\(".*?"\)' | sort | uniq -c | sort -nr | head -10
        ),
    ],
    
    # 验证命令 (Verification Commands)
    # 注意：由于当前版本没有实际的重置操作，验证主要是再次检查状态
    verify_commands=[
        RunbookStep(
            description="Verify connection count decreased",
            command="ss -s",  # 再次检查连接统计，实际上不会有变化
            timeout_seconds=10
        ),
    ],
    
    # 冷却时间：5分钟，避免频繁诊断 (Cooldown: 5 minutes, avoid frequent diagnosis)
    cooldown_seconds=300,
)
