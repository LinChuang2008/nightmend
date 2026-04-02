#!/usr/bin/env python3
"""
告警风暴模拟数据生成脚本 (Alert Storm Seed Script)

生成 200+ 条原始告警模拟真实告警风暴场景，触发去重聚合后压缩到 15-20 条。
使用 Demo 账号通过 API 直接写入数据库。

Usage:
    python scripts/seed_demo_alerts.py [--api-url http://localhost:8001] [--clean]
"""
import argparse
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# ── 配置 ──────────────────────────────────────────────
DEFAULT_API = "http://localhost:8001"
DEMO_EMAIL = "demo@nightmend.io"
DEMO_PASS = "demo123"

# ── 告警场景模板 ──────────────────────────────────────
# 每个场景会生成大量重复告警，去重后归为 1 组
SCENARIOS = [
    # === CPU 告警风暴 (同一主机反复触发) ===
    {
        "title_tpl": "CPU 使用率过高 - {host}",
        "message_tpl": "主机 {host} CPU 使用率 {value:.1f}% 超过阈值 {threshold}%，持续 {duration} 秒",
        "metric": "cpu_percent",
        "severity": "critical",
        "threshold": 90.0,
        "hosts": ["web-server-01"],
        "repeat": 30,  # 同一主机 30 次 → 去重为 1
        "value_range": (91.0, 99.5),
    },
    {
        "title_tpl": "CPU 使用率过高 - {host}",
        "message_tpl": "主机 {host} CPU 使用率 {value:.1f}% 超过阈值 {threshold}%，持续 {duration} 秒",
        "metric": "cpu_percent",
        "severity": "critical",
        "threshold": 90.0,
        "hosts": ["web-server-02"],
        "repeat": 25,
        "value_range": (90.5, 98.0),
    },
    {
        "title_tpl": "CPU 使用率过高 - {host}",
        "message_tpl": "主机 {host} CPU 使用率 {value:.1f}% 超过阈值 {threshold}%，持续 {duration} 秒",
        "metric": "cpu_percent",
        "severity": "warning",
        "threshold": 80.0,
        "hosts": ["web-server-03"],
        "repeat": 20,
        "value_range": (80.5, 89.0),
    },
    # === 内存告警风暴 ===
    {
        "title_tpl": "内存使用率过高 - {host}",
        "message_tpl": "主机 {host} 内存使用率 {value:.1f}% 超过阈值 {threshold}%",
        "metric": "memory_percent",
        "severity": "critical",
        "threshold": 95.0,
        "hosts": ["db-master-01"],
        "repeat": 25,
        "value_range": (95.2, 99.8),
    },
    {
        "title_tpl": "内存使用率过高 - {host}",
        "message_tpl": "主机 {host} 内存使用率 {value:.1f}% 超过阈值 {threshold}%",
        "metric": "memory_percent",
        "severity": "warning",
        "threshold": 85.0,
        "hosts": ["app-server-01", "app-server-02"],
        "repeat": 12,  # 每台 12 次
        "value_range": (85.5, 94.0),
    },
    # === 磁盘告警风暴 ===
    {
        "title_tpl": "磁盘使用率过高 - {host}",
        "message_tpl": "主机 {host} 磁盘 /data 使用率 {value:.1f}% 超过阈值 {threshold}%",
        "metric": "disk_percent",
        "severity": "critical",
        "threshold": 95.0,
        "hosts": ["db-master-01"],
        "repeat": 15,
        "value_range": (95.5, 99.0),
    },
    {
        "title_tpl": "磁盘使用率过高 - {host}",
        "message_tpl": "主机 {host} 磁盘 /var/log 使用率 {value:.1f}% 超过阈值 {threshold}%",
        "metric": "disk_percent",
        "severity": "warning",
        "threshold": 85.0,
        "hosts": ["log-server-01"],
        "repeat": 10,
        "value_range": (85.0, 94.0),
    },
    # === 网络告警风暴 ===
    {
        "title_tpl": "网络延迟过高 - {host}",
        "message_tpl": "主机 {host} 网络延迟 {value:.0f}ms 超过阈值 {threshold}ms",
        "metric": "network_latency_ms",
        "severity": "warning",
        "threshold": 200.0,
        "hosts": ["web-server-01", "web-server-02", "web-server-03"],
        "repeat": 8,
        "value_range": (210.0, 500.0),
    },
    {
        "title_tpl": "网络丢包率过高 - {host}",
        "message_tpl": "主机 {host} 网络丢包率 {value:.1f}% 超过阈值 {threshold}%",
        "metric": "network_packet_loss",
        "severity": "critical",
        "threshold": 5.0,
        "hosts": ["web-server-01"],
        "repeat": 12,
        "value_range": (5.5, 15.0),
    },
    # === 数据库连接池告警 ===
    {
        "title_tpl": "数据库连接池满 - {host}",
        "message_tpl": "主机 {host} 数据库连接池使用率 {value:.1f}% 超过阈值 {threshold}%",
        "metric": "db_connections",
        "severity": "critical",
        "threshold": 90.0,
        "hosts": ["db-master-01"],
        "repeat": 18,
        "value_range": (90.5, 100.0),
    },
    # === 响应时间告警 ===
    {
        "title_tpl": "HTTP 响应时间过长 - {host}",
        "message_tpl": "主机 {host} 平均响应时间 {value:.0f}ms 超过阈值 {threshold}ms",
        "metric": "http_response_time",
        "severity": "warning",
        "threshold": 3000.0,
        "hosts": ["web-server-01", "web-server-02"],
        "repeat": 10,
        "value_range": (3200.0, 8000.0),
    },
    # === OOM 告警 ===
    {
        "title_tpl": "OOM Kill 检测 - {host}",
        "message_tpl": "主机 {host} 检测到 OOM Kill 事件，进程被系统杀死",
        "metric": "oom_kill",
        "severity": "critical",
        "threshold": 1.0,
        "hosts": ["app-server-01", "app-server-02"],
        "repeat": 5,
        "value_range": (1.0, 3.0),
    },
    # === 慢查询告警 ===
    {
        "title_tpl": "数据库慢查询过多 - {host}",
        "message_tpl": "主机 {host} 慢查询数量 {value:.0f} 超过阈值 {threshold}",
        "metric": "slow_queries",
        "severity": "warning",
        "threshold": 50.0,
        "hosts": ["db-master-01"],
        "repeat": 15,
        "value_range": (55.0, 200.0),
    },
]


def login(api_url):
    """登录获取 token"""
    resp = requests.post(
        f"{api_url}/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASS},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"❌ 登录失败: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json().get("access_token")
    print(f"✅ 登录成功，获取 token")
    return token


def get_or_create_rule(api_url, headers, scenario):
    """获取或创建告警规则，返回 rule_id"""
    # 先获取已有规则
    resp = requests.get(f"{api_url}/api/v1/alert-rules", headers=headers, timeout=10)
    if resp.status_code == 200:
        rules = resp.json()
        if isinstance(rules, dict):
            rules = rules.get("items", rules.get("rules", []))
        for rule in rules:
            if rule.get("metric") == scenario["metric"]:
                return rule["id"]

    # 创建新规则
    rule_data = {
        "name": f"{scenario['metric']} 告警规则",
        "metric": scenario["metric"],
        "operator": ">",
        "threshold": scenario["threshold"],
        "severity": scenario["severity"],
        "duration_seconds": 60,
        "rule_type": "metric",
        "is_enabled": True,
    }
    resp = requests.post(
        f"{api_url}/api/v1/alert-rules",
        json=rule_data,
        headers=headers,
        timeout=10,
    )
    if resp.status_code in (200, 201):
        return resp.json()["id"]
    return 1  # fallback


def seed_alerts(api_url, token):
    """生成告警风暴数据"""
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc)
    total_created = 0
    rule_cache = {}

    print(f"\n🌊 开始生成告警风暴...")
    print(f"   场景数: {len(SCENARIOS)}")

    for i, scenario in enumerate(SCENARIOS):
        metric = scenario["metric"]
        if metric not in rule_cache:
            rule_cache[metric] = get_or_create_rule(api_url, headers, scenario)
        rule_id = rule_cache[metric]

        for host in scenario["hosts"]:
            for j in range(scenario["repeat"]):
                value = random.uniform(*scenario["value_range"])
                # 告警时间分布在过去 30 分钟内
                fired_at = now - timedelta(seconds=random.randint(30, 1800))
                duration = random.randint(60, 600)

                alert_data = {
                    "rule_id": rule_id,
                    "severity": scenario["severity"],
                    "status": "firing",
                    "title": scenario["title_tpl"].format(host=host),
                    "message": scenario["message_tpl"].format(
                        host=host,
                        value=value,
                        threshold=scenario["threshold"],
                        duration=duration,
                    ),
                    "metric_value": round(value, 2),
                    "threshold": scenario["threshold"],
                    "fired_at": fired_at.isoformat(),
                }

                # 尝试通过告警 API 创建
                resp = requests.post(
                    f"{api_url}/api/v1/alerts",
                    json=alert_data,
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    total_created += 1
                elif resp.status_code == 405:
                    # 如果没有 POST /alerts，直接用数据库方式
                    print(f"   ⚠️  POST /alerts 不可用，切换到数据库直插模式")
                    return seed_alerts_via_db(api_url, token)

        host_str = ", ".join(scenario["hosts"])
        count = len(scenario["hosts"]) * scenario["repeat"]
        print(f"   [{i+1}/{len(SCENARIOS)}] {metric} ({host_str}): {count} 条")

    print(f"\n✅ 共创建 {total_created} 条原始告警")
    return total_created


def seed_alerts_via_db(api_url, token):
    """直接通过数据库插入告警（如果 API 不支持 POST）"""
    # 使用 SQL 直插方式，通过 admin API 或直接数据库连接
    print("   📝 使用数据库直插模式...")

    # 构造 SQL 批量插入
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc)
    total = 0

    for scenario in SCENARIOS:
        for host in scenario["hosts"]:
            for j in range(scenario["repeat"]):
                value = random.uniform(*scenario["value_range"])
                fired_at = now - timedelta(seconds=random.randint(30, 1800))

                # 尝试通过内部 agent API
                alert_data = {
                    "rule_id": 1,
                    "severity": scenario["severity"],
                    "status": "firing",
                    "title": scenario["title_tpl"].format(host=host),
                    "message": scenario["message_tpl"].format(
                        host=host,
                        value=value,
                        threshold=scenario["threshold"],
                        duration=random.randint(60, 600),
                    ),
                    "metric_value": round(value, 2),
                    "threshold": scenario["threshold"],
                    "fired_at": fired_at.isoformat(),
                }

                resp = requests.post(
                    f"{api_url}/api/v1/agent/alert",
                    json=alert_data,
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    total += 1

    print(f"\n✅ 共创建 {total} 条原始告警")
    return total


def trigger_dedup(api_url, token):
    """查看去重统计"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{api_url}/api/v1/alert-deduplication/statistics",
        headers=headers,
        timeout=10,
    )
    if resp.status_code == 200:
        stats = resp.json()
        print(f"\n📊 去重统计:")
        print(f"   活跃去重记录: {stats.get('active_dedup_records', 'N/A')}")
        print(f"   活跃告警组: {stats.get('active_alert_groups', 'N/A')}")
        print(f"   24h 去重率: {stats.get('deduplication_rate_24h', 'N/A')}%")
        print(f"   24h 抑制告警: {stats.get('suppressed_alerts_24h', 'N/A')}")
        print(f"   24h 总告警次数: {stats.get('total_alert_occurrences_24h', 'N/A')}")
    else:
        print(f"   ⚠️  获取统计失败: {resp.status_code}")


def show_groups(api_url, token):
    """展示聚合组"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{api_url}/api/v1/alert-deduplication/groups?limit=30",
        headers=headers,
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        groups = data.get("groups", [])
        total = data.get("total", 0)
        print(f"\n📦 告警聚合组 (共 {total} 组):")
        for g in groups:
            print(f"   [{g['severity'].upper():8s}] {g['title']} — {g['alert_count']} 条告警")
    else:
        print(f"   ⚠️  获取聚合组失败: {resp.status_code}")


def main():
    parser = argparse.ArgumentParser(description="NightMend 告警风暴模拟数据生成")
    parser.add_argument("--api-url", default=DEFAULT_API, help="后端 API 地址")
    parser.add_argument("--clean", action="store_true", help="生成前清理旧的去重记录")
    args = parser.parse_args()

    print("=" * 60)
    print("  NightMend 告警风暴模拟数据生成器")
    print("=" * 60)
    print(f"  API: {args.api_url}")
    print(f"  账号: {DEMO_EMAIL}")

    # 1. 登录
    token = login(args.api_url)

    # 2. 可选清理
    if args.clean:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(
            f"{args.api_url}/api/v1/alert-deduplication/cleanup",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            print("🧹 已清理旧记录")
        else:
            print(f"⚠️  清理失败（可能权限不足）: {resp.status_code}")

    # 3. 生成告警
    total = seed_alerts(args.api_url, token)

    # 4. 预计压缩效果
    expected_groups = len(SCENARIOS)  # ~14 个场景 → ~14-20 个组
    if total > 0:
        rate = (1 - expected_groups / total) * 100
        print(f"\n🎯 预期降噪效果:")
        print(f"   原始告警: {total} 条")
        print(f"   预计聚合组: {expected_groups} 组")
        print(f"   预计降噪率: {rate:.1f}%")

    # 5. 查看实际统计
    trigger_dedup(args.api_url, token)
    show_groups(args.api_url, token)

    print(f"\n{'=' * 60}")
    print("  ✅ 完成！请访问前端查看降噪效果")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
