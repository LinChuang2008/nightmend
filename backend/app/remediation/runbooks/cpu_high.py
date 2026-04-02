"""
NightMend 内置 Runbook - CPU 使用率过高排查
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

RUNBOOK = RunbookDefinition(
    name="cpu_high",
    description="Investigate and mitigate high CPU usage by identifying top processes",
    match_alert_types=["cpu_high", "cpu_usage_high", "cpu_percent", "high_cpu", "cpu_load"],
    match_keywords=["cpu", "load", "负载", "CPU", "处理器"],
    risk_level=RiskLevel.AUTO,
    commands=[
        RunbookStep(
            description="Show system load averages",
            command="uptime",
            timeout_seconds=5,
        ),
        RunbookStep(
            description="List top 10 CPU-consuming processes",
            command="ps aux --sort=-%cpu | head -12",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Show per-CPU usage breakdown",
            command="mpstat -P ALL 1 1 2>/dev/null || top -bn1 | head -5",
            timeout_seconds=15,
        ),
        RunbookStep(
            description="Check for runaway processes (CPU > 80%)",
            command="ps aux | awk '$3 > 80 {print $0}'",
            timeout_seconds=10,
        ),
    ],
    verify_commands=[
        RunbookStep(
            description="Verify current load average",
            command="cat /proc/loadavg",
            timeout_seconds=5,
        ),
    ],
    cooldown_seconds=300,
)
