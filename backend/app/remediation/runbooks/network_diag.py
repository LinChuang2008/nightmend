"""
NightMend 内置 Runbook - 网络连通性诊断
"""
from ..models import RiskLevel, RunbookDefinition, RunbookStep

RUNBOOK = RunbookDefinition(
    name="network_diag",
    description="Diagnose network connectivity issues: DNS, routing, port reachability",
    match_alert_types=["network_unreachable", "ping_timeout", "dns_failure", "port_unreachable"],
    match_keywords=["network", "ping", "dns", "unreachable", "timeout", "网络", "连接超时", "无法连接"],
    risk_level=RiskLevel.AUTO,
    commands=[
        RunbookStep(
            description="Check network interfaces",
            command="ip -br addr show",
            timeout_seconds=5,
        ),
        RunbookStep(
            description="Check default gateway connectivity",
            command="ip route show default && ping -c 3 -W 2 $(ip route show default | awk '/default/ {print $3}' | head -1) 2>&1 || echo 'No default gateway'",
            timeout_seconds=15,
        ),
        RunbookStep(
            description="Check DNS resolution",
            command="dig +short google.com @8.8.8.8 2>/dev/null || nslookup google.com 2>&1 | tail -3",
            timeout_seconds=10,
        ),
        RunbookStep(
            description="Check listening ports",
            command="ss -tlnp | head -20",
            timeout_seconds=5,
        ),
    ],
    verify_commands=[
        RunbookStep(
            description="Quick connectivity test",
            command="ping -c 1 -W 3 8.8.8.8 && echo 'Network OK' || echo 'Network FAILED'",
            timeout_seconds=10,
        ),
    ],
    cooldown_seconds=120,
)
