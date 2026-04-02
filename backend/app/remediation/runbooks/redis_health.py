"""
NightMend 内置 Runbook - Redis 健康检查与修复
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

RUNBOOK = RunbookDefinition(
    name="redis_health",
    description="Check Redis health, memory usage, and restart if unresponsive",
    match_alert_types=["redis_down", "redis_memory_high", "redis_connections"],
    match_keywords=["redis", "缓存", "cache", "redis连接", "redis内存"],
    risk_level=RiskLevel.CONFIRM,
    commands=[
        RunbookStep(
            description="Check Redis container/service status",
            command="docker ps -a --filter name=redis --format 'table {{.Names}}\t{{.Status}}'",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Redis ping check",
            command="docker exec redis redis-cli ping 2>/dev/null || redis-cli ping",
            timeout_seconds=5,
        ),
        RunbookStep(
            description="Show Redis memory and stats",
            command="docker exec redis redis-cli info memory 2>/dev/null | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation' || redis-cli info memory 2>/dev/null | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation'",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Restart Redis",
            command="docker restart redis 2>/dev/null || systemctl restart redis",
            timeout_seconds=30,
        ),
    ],
    verify_commands=[
        RunbookStep(
            description="Verify Redis is responding",
            command="docker exec redis redis-cli ping 2>/dev/null || redis-cli ping",
            timeout_seconds=5,
        ),
    ],
    cooldown_seconds=300,
)
