#!/usr/bin/env python3
"""
VigilOps Demo 数据种子脚本 (Demo Seed Data Script)

插入合理的示例数据，让 Demo 用户能看到产品最大卖点：
- 自动修复执行记录（Runbook 执行历史）
- 告警升级记录
- 告警中心"修复状态"列有真实数据

Usage:
    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --clean  # 清理后重新插入
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")

import asyncio
import asyncpg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://vigilops:vigilops@localhost:5432/vigilops"
)

if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DSN = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
elif DATABASE_URL.startswith("postgresql://"):
    DSN = DATABASE_URL
else:
    DSN = DATABASE_URL


async def get_existing_alerts(conn):
    rows = await conn.fetch("SELECT id, title, severity, status FROM alerts ORDER BY id LIMIT 20")
    return rows


async def get_existing_hosts(conn):
    rows = await conn.fetch("SELECT id, hostname FROM hosts ORDER BY id LIMIT 10")
    return rows


async def get_existing_alert_rules(conn):
    rows = await conn.fetch("SELECT id, name, metric FROM alert_rules ORDER BY id LIMIT 10")
    return rows


async def clean_demo_data(conn):
    print("🧹 清理已有 Demo 数据...")
    await conn.execute("DELETE FROM remediation_logs WHERE runbook_name IS NOT NULL")
    await conn.execute("DELETE FROM alert_escalations WHERE message LIKE '%Demo%' OR message LIKE '%demo%'")
    await conn.execute("DELETE FROM escalation_rules WHERE name LIKE '%演示%'")
    print("✅ 清理完成")


async def seed_remediation_logs(conn, alerts, hosts):
    print("\n📋 插入自动修复执行记录...")
    now = datetime.now(timezone.utc)
    host_id = hosts[0]["id"] if hosts else 1
    host2_id = hosts[1]["id"] if len(hosts) > 1 else host_id

    def get_alert_id(idx):
        if alerts and idx < len(alerts):
            return alerts[idx]["id"]
        return idx + 1

    scenarios = [
        {
            "alert_id": get_alert_id(0),
            "host_id": host_id,
            "status": "success",
            "risk_level": "auto",
            "runbook_name": "high_memory_nginx_reload",
            "triggered_by": "auto",
            "started_at": now - timedelta(hours=2, minutes=30),
            "completed_at": now - timedelta(hours=2, minutes=28),
            "verification_passed": True,
            "diagnosis": {
                "issue": "Nginx 内存占用过高（87%），超过阈值 80%",
                "root_cause": "Nginx worker 进程内存泄漏，长时间运行未释放",
                "confidence": 0.92,
                "recommendation": "执行 nginx reload 以重启 worker 进程，释放内存",
            },
            "commands": [
                {"cmd": "systemctl status nginx", "exit_code": 0, "output": "nginx.service - active (running)"},
                {"cmd": "nginx -t", "exit_code": 0, "output": "configuration test is successful"},
                {"cmd": "systemctl reload nginx", "exit_code": 0, "output": ""},
                {"cmd": "free -m", "exit_code": 0, "output": "Mem: 7934 3841 3100 after reload"},
            ],
        },
        {
            "alert_id": get_alert_id(1),
            "host_id": host_id,
            "status": "success",
            "risk_level": "auto",
            "runbook_name": "high_disk_clean_logs",
            "triggered_by": "auto",
            "started_at": now - timedelta(hours=5, minutes=10),
            "completed_at": now - timedelta(hours=5, minutes=6),
            "verification_passed": True,
            "diagnosis": {
                "issue": "磁盘 /var/log 使用率 93%，超过阈值 90%",
                "root_cause": "应用日志未及时轮转，7天内积累大量日志文件",
                "confidence": 0.98,
                "recommendation": "清理 30 天前的日志文件并压缩近期日志",
            },
            "commands": [
                {"cmd": "df -h /var/log", "exit_code": 0, "output": "/dev/sda1 50G 46G 4G 93% /var/log"},
                {"cmd": "find /var/log -name '*.log' -mtime +30 -delete", "exit_code": 0, "output": "Deleted 127 files, freed 8.3GB"},
                {"cmd": "find /var/log -name '*.log' -mtime +7 -exec gzip {} \\;", "exit_code": 0, "output": "Compressed 43 files"},
                {"cmd": "df -h /var/log", "exit_code": 0, "output": "/dev/sda1 50G 32G 18G 64% /var/log"},
            ],
        },
        {
            "alert_id": get_alert_id(2),
            "host_id": host2_id,
            "status": "success",
            "risk_level": "confirm",
            "runbook_name": "service_restart",
            "triggered_by": "auto",
            "started_at": now - timedelta(hours=8),
            "completed_at": now - timedelta(hours=7, minutes=57),
            "verification_passed": True,
            "approved_by": 1,
            "approved_at": now - timedelta(hours=7, minutes=59),
            "diagnosis": {
                "issue": "应用服务 app-server 响应超时，连续 3 次健康检查失败",
                "root_cause": "Java OOM 导致进程假死，GC overhead limit exceeded",
                "confidence": 0.88,
                "recommendation": "重启应用服务，并增加 JVM 内存配置",
            },
            "commands": [
                {"cmd": "systemctl status app-server", "exit_code": 0, "output": "app-server.service - degraded"},
                {"cmd": "journalctl -u app-server -n 5", "exit_code": 0, "output": "java.lang.OutOfMemoryError: GC overhead limit exceeded"},
                {"cmd": "systemctl restart app-server", "exit_code": 0, "output": ""},
                {"cmd": "curl -s http://localhost:8080/health", "exit_code": 0, "output": '{"status":"ok"}'},
            ],
        },
        {
            "alert_id": get_alert_id(3),
            "host_id": host_id,
            "status": "success",
            "risk_level": "auto",
            "runbook_name": "high_cpu_kill_zombie",
            "triggered_by": "auto",
            "started_at": now - timedelta(days=1, hours=3),
            "completed_at": now - timedelta(days=1, hours=2, minutes=58),
            "verification_passed": True,
            "diagnosis": {
                "issue": "CPU 使用率持续 95% 超过 10 分钟，僵尸进程积累",
                "root_cause": "大量僵尸进程消耗 CPU 调度资源，来自定时任务异常退出",
                "confidence": 0.85,
                "recommendation": "清理僵尸进程，重启父进程 cron",
            },
            "commands": [
                {"cmd": "ps aux | grep -c Z", "exit_code": 0, "output": "23"},
                {"cmd": "kill zombie processes", "exit_code": 0, "output": "Killed 23 zombie processes"},
                {"cmd": "systemctl restart cron", "exit_code": 0, "output": ""},
                {"cmd": "top -bn1 | grep Cpu", "exit_code": 0, "output": "Cpu(s): 12.3%us, 84.6%id"},
            ],
        },
        {
            "alert_id": get_alert_id(4),
            "host_id": host2_id,
            "status": "failed",
            "risk_level": "block",
            "runbook_name": "db_connection_pool_reset",
            "triggered_by": "auto",
            "started_at": now - timedelta(days=1, hours=6),
            "completed_at": now - timedelta(days=1, hours=5, minutes=55),
            "verification_passed": False,
            "blocked_reason": "数据库连接池重置需要停服 2 分钟，当前处于业务高峰期（18:00-20:00），风险评估为高。已升级给值班人员处理。",
            "diagnosis": {
                "issue": "PostgreSQL 连接池使用率 98%，新连接请求被拒绝",
                "root_cause": "应用层连接未正确释放，连接泄漏导致连接池耗尽",
                "confidence": 0.94,
                "recommendation": "重置连接池，建议在业务低峰期执行",
            },
            "commands": [
                {"cmd": "psql -c 'SELECT count(*) FROM pg_stat_activity'", "exit_code": 0, "output": "count: 198/200"},
                {"cmd": "pg_terminate_backend", "exit_code": 1, "output": "ERROR: permission denied"},
            ],
        },
    ]

    inserted = 0
    for s in scenarios:
        try:
            await conn.execute(
                """
                INSERT INTO remediation_logs
                    (alert_id, host_id, status, risk_level, runbook_name,
                     diagnosis_json, command_results_json, verification_passed,
                     blocked_reason, triggered_by, approved_by, approved_at,
                     started_at, completed_at, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                """,
                s["alert_id"],
                s["host_id"],
                s["status"],
                s["risk_level"],
                s["runbook_name"],
                json.dumps(s["diagnosis"], ensure_ascii=False),
                json.dumps(s["commands"], ensure_ascii=False),
                s.get("verification_passed"),
                s.get("blocked_reason"),
                s["triggered_by"],
                s.get("approved_by"),
                s.get("approved_at"),
                s["started_at"],
                s.get("completed_at"),
                s["started_at"],
            )
            inserted += 1
            print(f"  ✅ [{s['status']:8s}] {s['runbook_name']} (alert_id={s['alert_id']})")
        except Exception as e:
            print(f"  ❌ 插入失败 {s['runbook_name']}: {e}")

    print(f"\n  共插入 {inserted} 条修复记录")
    return inserted


async def seed_escalation_rules(conn, alert_rules):
    print("\n📋 插入告警升级规则...")
    rule_id = alert_rules[0]["id"] if alert_rules else 1

    name = "演示-CPU告警升级策略"
    row = await conn.fetchrow("SELECT id FROM escalation_rules WHERE name = $1", name)
    if row:
        print(f"  ⏭️  已存在: {name}")
        return 0

    levels = json.dumps([
        {"level": 1, "delay_minutes": 5, "notify": ["oncall"], "severity": "warning"},
        {"level": 2, "delay_minutes": 15, "notify": ["manager", "oncall"], "severity": "critical"},
        {"level": 3, "delay_minutes": 30, "notify": ["director"], "severity": "critical"},
    ], ensure_ascii=False)

    try:
        await conn.execute(
            "INSERT INTO escalation_rules (alert_rule_id, name, is_enabled, escalation_levels) VALUES ($1,$2,$3,$4)",
            rule_id, name, True, levels,
        )
        print(f"  ✅ 升级规则: {name}")
        return 1
    except Exception as e:
        print(f"  ❌ 插入失败: {e}")
        return 0


async def seed_escalation_history(conn, alerts):
    print("\n📋 插入告警升级历史记录...")
    now = datetime.now(timezone.utc)

    def get_alert_id(idx):
        if alerts and idx < len(alerts):
            return alerts[idx]["id"]
        return idx + 1

    histories = [
        {
            "alert_id": get_alert_id(0),
            "from_severity": "warning",
            "to_severity": "critical",
            "escalation_level": 1,
            "escalated_at": now - timedelta(hours=1, minutes=45),
            "escalated_by_system": True,
            "message": "告警持续 5 分钟未处理，自动升级为 critical（Demo：CPU 使用率持续超阈值）",
        },
        {
            "alert_id": get_alert_id(1),
            "from_severity": "critical",
            "to_severity": "critical",
            "escalation_level": 2,
            "escalated_at": now - timedelta(hours=4, minutes=20),
            "escalated_by_system": True,
            "message": "告警升级至第2级，已通知值班经理（Demo：磁盘告警未在15分钟内处理）",
        },
        {
            "alert_id": get_alert_id(2),
            "from_severity": "warning",
            "to_severity": "critical",
            "escalation_level": 1,
            "escalated_at": now - timedelta(days=1, hours=2),
            "escalated_by_system": False,
            "message": "手动升级：运维工程师判断服务中断影响超过预期（Demo：手动升级示例）",
        },
    ]

    inserted = 0
    for h in histories:
        try:
            await conn.execute(
                """
                INSERT INTO alert_escalations
                    (alert_id, escalation_rule_id, from_severity, to_severity,
                     escalation_level, escalated_at, escalated_by_system, message)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                h["alert_id"],
                None,
                h["from_severity"],
                h["to_severity"],
                h["escalation_level"],
                h["escalated_at"],
                h["escalated_by_system"],
                h["message"],
            )
            inserted += 1
            print(f"  ✅ 升级: {h['from_severity']}→{h['to_severity']} level={h['escalation_level']} (alert_id={h['alert_id']})")
        except Exception as e:
            print(f"  ❌ 插入失败: {e}")

    print(f"\n  共插入 {inserted} 条升级记录")
    return inserted


async def main(clean=False):
    print("=" * 60)
    print("  VigilOps Demo 数据种子脚本")
    print("=" * 60)

    try:
        conn = await asyncpg.connect(DSN)
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        sys.exit(1)

    print("✅ 数据库连接成功")

    try:
        if clean:
            await clean_demo_data(conn)

        alerts = await get_existing_alerts(conn)
        hosts = await get_existing_hosts(conn)
        alert_rules = await get_existing_alert_rules(conn)

        print(f"\n📊 已有数据: 告警 {len(alerts)} 条 | 主机 {len(hosts)} 台 | 规则 {len(alert_rules)} 条")
        for a in alerts[:5]:
            print(f"    告警[{a['id']}]: {a['title'][:50]} ({a['status']})")
        for h in hosts[:3]:
            print(f"    主机[{h['id']}]: {h['hostname']}")

        r1 = await seed_remediation_logs(conn, alerts, hosts)
        r2 = await seed_escalation_rules(conn, alert_rules)
        r3 = await seed_escalation_history(conn, alerts)

        print(f"\n{'=' * 60}")
        print(f"  ✅ 种子数据插入完成！")
        print(f"     修复记录: {r1} 条 | 升级规则: {r2} 条 | 升级历史: {r3} 条")
        print(f"{'=' * 60}")
        print(f"\n  请访问: https://demo.lchuangnet.com")
        print(f"  账号: demo@vigilops.io / demo123")

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(clean=args.clean))
