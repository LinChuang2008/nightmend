"""
NightMend 内置 Runbook - MySQL 健康检查与修复
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

RUNBOOK = RunbookDefinition(
    name="mysql_health",
    description="Check MySQL health, connections, slow queries and restart if needed",
    match_alert_types=["mysql_down", "mysql_connections_high", "mysql_slow", "database_down"],
    match_keywords=["mysql", "mariadb", "database", "数据库", "mysql连接", "慢查询", "slow query"],
    risk_level=RiskLevel.CONFIRM,
    commands=[
        RunbookStep(
            description="Check MySQL container/service status",
            command="docker ps --filter name=mysql --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || systemctl status mysql --no-pager 2>/dev/null || systemctl status mysqld --no-pager",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Check MySQL connection count",
            command="docker exec mysql mysqladmin -u root status 2>/dev/null || mysqladmin -u root status",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Show MySQL process list (top 10)",
            command="docker exec mysql mysql -u root -e 'SHOW PROCESSLIST' 2>/dev/null | head -12 || mysql -u root -e 'SHOW PROCESSLIST' 2>/dev/null | head -12",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Restart MySQL service",
            command="docker restart mysql 2>/dev/null || systemctl restart mysql 2>/dev/null || systemctl restart mysqld",
            timeout_seconds=60,
        ),
    ],
    verify_commands=[
        RunbookStep(
            description="Verify MySQL is running and accepting connections",
            command="docker exec mysql mysqladmin -u root ping 2>/dev/null || mysqladmin -u root ping",
            timeout_seconds=10,
        ),
    ],
    cooldown_seconds=300,
)
