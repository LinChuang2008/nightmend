"""
NightMend 内置 Runbook - Docker 资源清理
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

RUNBOOK = RunbookDefinition(
    name="docker_cleanup",
    description="Clean up unused Docker resources (stopped containers, dangling images, unused volumes)",
    match_alert_types=["docker_disk", "container_cleanup"],
    match_keywords=["docker", "container", "image", "容器", "镜像", "dangling"],
    risk_level=RiskLevel.CONFIRM,
    commands=[
        RunbookStep(
            description="Show Docker disk usage summary",
            command="docker system df",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="List stopped containers",
            command="docker ps -a --filter status=exited --format 'table {{.Names}}\t{{.Status}}\t{{.Size}}'",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Remove stopped containers",
            command="docker container prune -f",
            timeout_seconds=30,
        ),
        RunbookStep(
            description="Remove dangling images",
            command="docker image prune -f",
            timeout_seconds=60,
        ),
    ],
    verify_commands=[
        RunbookStep(
            description="Show Docker disk usage after cleanup",
            command="docker system df",
            timeout_seconds=10,
        ),
    ],
    cooldown_seconds=600,
)
