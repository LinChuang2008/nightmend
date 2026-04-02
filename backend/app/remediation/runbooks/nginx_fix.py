"""
NightMend 内置 Runbook - Nginx 排查与修复
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

RUNBOOK = RunbookDefinition(
    name="nginx_fix",
    description="Diagnose and fix Nginx issues: config test, error log check, reload/restart",
    match_alert_types=["nginx_down", "http_502", "http_503", "http_5xx"],
    match_keywords=["nginx", "502", "503", "bad gateway", "gateway timeout", "web服务", "反向代理"],
    risk_level=RiskLevel.CONFIRM,
    commands=[
        RunbookStep(
            description="Check Nginx service status",
            command="docker ps --filter name=nginx --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || systemctl status nginx --no-pager",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Test Nginx configuration",
            command="docker exec nginx nginx -t 2>&1 || nginx -t 2>&1",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Check recent Nginx error log",
            command="docker logs --tail 20 nginx 2>&1 || tail -20 /var/log/nginx/error.log",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Reload Nginx (graceful)",
            command="docker exec nginx nginx -s reload 2>/dev/null || nginx -s reload 2>/dev/null || systemctl reload nginx",
            timeout_seconds=15,
        ),
    ],
    verify_commands=[
        RunbookStep(
            description="Verify Nginx is responding",
            command="curl -s -o /dev/null -w '%{http_code}' http://localhost/ --connect-timeout 5 --max-time 10",
            timeout_seconds=15,
        ),
    ],
    cooldown_seconds=120,
)
