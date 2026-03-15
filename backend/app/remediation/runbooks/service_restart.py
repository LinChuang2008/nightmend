"""
VigilOps 自动修复 Runbook - 服务重启
VigilOps Automatic Remediation Runbook - Service Restart

这是一个服务重启修复脚本，用于处理服务异常或停止运行的告警。
This is a service restart remediation script for handling service failure or stopped service alerts.

适用场景 (Applicable Scenarios):
- 服务进程意外停止 (Service process unexpectedly stopped)
- 服务响应超时或无响应 (Service timeout or unresponsive)
- 服务状态检查失败 (Service status check failed)
- 应用崩溃需要重启 (Application crash requiring restart)

修复原理 (Remediation Principle):
- 使用 systemd 服务管理机制
- 先检查状态，再执行重启，后验证结果
- 支持变量替换，可以指定具体的服务名称

风险评估 (Risk Assessment):
- 风险等级：CONFIRM（需要确认）
- 影响：会导致服务短暂中断（通常几秒到几十秒）
- 数据安全：依赖服务本身的持久化机制
- 恢复时间：通常在30秒内完成重启

变量支持 (Variable Support):
- {service_name}: 从告警标签中获取的服务名称
- 示例：nginx, apache2, mysql, redis-server 等

注意事项 (Important Notes):
- 重启会中断现有连接和会话
- 某些服务重启可能需要较长时间
- 数据库等有状态服务重启需谨慎

作者：VigilOps Team
版本：v1.0
风险等级：MEDIUM
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

# 服务重启 Runbook 定义 (Service Restart Runbook Definition)
RUNBOOK = RunbookDefinition(
    # 基本信息 (Basic Information)
    name="service_restart",
    description="Restart a failed or unresponsive service",
    
    # 匹配规则 (Matching Rules)
    match_alert_types=["service_down", "service_unhealthy", "process_not_running"],  # 服务异常告警类型
    match_keywords=["service", "down", "stopped", "not running", "unresponsive", "crashed", "服务"],  # 服务故障关键词
    
    # 安全设置 (Safety Settings)
    risk_level=RiskLevel.CONFIRM,  # 需要确认：服务重启会导致短暂中断，需要人工审批
    
    # 服务重启命令序列 (Service Restart Command Sequence)
    # 优先尝试 Docker 重启，然后尝试 systemd 重启
    commands=[
        # 第1步：检查是否为 Docker 容器并重启 (Step 1: Check if Docker container and restart)
        RunbookStep(
            description="Check Docker container status",
            command="docker ps -a --filter name={service_name} --format '{{.Status}}'",
            timeout_seconds=10
        ),
        # 第2步：尝试 Docker 重启 (Step 2: Try Docker restart)
        RunbookStep(
            description="Restart Docker container",
            command="docker restart {service_name}",
            timeout_seconds=30
        ),
    ],

    # 验证命令 (Verification Commands)
    verify_commands=[
        RunbookStep(
            description="Verify container is running after restart",
            command="docker ps --filter name={service_name} --format '{{.Status}}'",
            timeout_seconds=10
        ),
    ],
    
    # 冷却时间：5分钟，避免频繁重启 (Cooldown: 5 minutes, avoid frequent restarts)
    cooldown_seconds=300,
)
