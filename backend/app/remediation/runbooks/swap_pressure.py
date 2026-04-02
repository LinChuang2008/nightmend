"""
NightMend 内置 Runbook - Swap 使用率过高排查
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

RUNBOOK = RunbookDefinition(
    name="swap_pressure",
    description="Investigate high swap usage and identify memory-hungry processes",
    match_alert_types=["swap_high", "swap_usage_high"],
    match_keywords=["swap", "交换分区", "交换空间"],
    risk_level=RiskLevel.AUTO,
    commands=[
        RunbookStep(
            description="Show memory and swap usage",
            command="free -h",
            timeout_seconds=5,
        ),
        RunbookStep(
            description="Top 10 memory-consuming processes",
            command="ps aux --sort=-%mem | head -12",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Show per-process swap usage",
            command="for pid in $(ls /proc/ | grep -E '^[0-9]+$' | head -50); do awk '/VmSwap/{print \"'$pid'\", $2, $3}' /proc/$pid/status 2>/dev/null; done | sort -k2 -rn | head -10",
            timeout_seconds=15,
        ),
        RunbookStep(
            description="Drop filesystem caches to relieve pressure",
            command="sync && echo 1 > /proc/sys/vm/drop_caches",
            timeout_seconds=10,
        ),
    ],
    verify_commands=[
        RunbookStep(
            description="Check swap usage after cleanup",
            command="free -h | grep Swap",
            timeout_seconds=5,
        ),
    ],
    cooldown_seconds=600,
)
