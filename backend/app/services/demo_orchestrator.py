"""
Demo Orchestrator — Autopilot Demo 编排器

负责：预填充示例数据、延时故障注入、自动创建 OpsSession 并启动 AI 诊断。
仅在 DEMO_MODE=true 时激活。
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session as AsyncSessionLocal
from app.core.redis import get_redis

logger = logging.getLogger("nightmend.demo")

# Demo 状态（进程内单例 + Redis 共享，兼容多 worker）
_demo_state = {
    "phase": "idle",        # idle | seeding | exploring | injecting | diagnosing | complete
    "session_id": None,
    "host_id": None,
    "alert_id": None,
    "started_at": None,
}

_DEMO_STATE_KEY = "nightmend:demo:state"


async def _sync_state_to_redis():
    """将进程内 demo 状态同步到 Redis，供其他 worker 读取。"""
    try:
        redis = await get_redis()
        data = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in _demo_state.items()}
        await redis.set(_DEMO_STATE_KEY, json.dumps(data), ex=3600)
    except Exception:
        pass


async def _read_state_from_redis() -> dict | None:
    """从 Redis 读取共享 demo 状态。"""
    try:
        redis = await get_redis()
        raw = await redis.get(_DEMO_STATE_KEY)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


async def _update_demo_state(**kwargs):
    """更新进程内状态并同步到 Redis。"""
    _demo_state.update(kwargs)
    await _sync_state_to_redis()


async def get_demo_status() -> dict:
    """返回当前 Demo 阶段和相关 ID（优先从 Redis 读取，兼容多 worker）。"""
    redis_state = await _read_state_from_redis()
    state = redis_state if redis_state else dict(_demo_state)
    started_at = state.get("started_at")
    if started_at:
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        state["elapsed_s"] = round(elapsed, 1)
    else:
        state["elapsed_s"] = 0
    state["demo_mode"] = settings.demo_mode
    return state


async def seed_demo_data():
    """
    预填充 Demo 示例数据：3 台主机、告警规则、服务依赖。
    幂等：如果 demo 主机已存在则跳过。
    """
    from app.models.host import Host
    from app.models.alert_rule import AlertRule
    from app.models.service import Service
    from app.models.service_dependency import ServiceDependency
    from app.models.host_metric import HostMetric

    await _update_demo_state(phase="seeding")
    logger.info("Demo: seeding sample data...")

    async with AsyncSessionLocal() as db:
        # 检查幂等性
        existing = await db.execute(
            select(Host).where(Host.hostname == "demo-nginx-01")
        )
        if existing.scalar_one_or_none():
            logger.info("Demo: sample data already exists, skipping seed")
            await _update_demo_state(phase="exploring")
            return

        # 创建 3 台 demo 主机
        hosts = []
        for hostname, display, ip in [
            ("demo-nginx-01", "Demo Nginx", "10.0.1.10"),
            ("demo-app-01", "Demo App Server", "10.0.1.11"),
            ("demo-postgres-01", "Demo PostgreSQL", "10.0.1.12"),
        ]:
            h = Host(
                hostname=hostname,
                display_name=display,
                ip_address=ip,
                os_type="Linux",
                os_version="Ubuntu 22.04",
                status="online",
                agent_version="1.0.0-demo",
                last_seen=datetime.now(timezone.utc),
            )
            db.add(h)
            hosts.append(h)

        await db.flush()

        # 记住主机 ID
        await _update_demo_state(host_id=hosts[0].id)
        demo_host_ids = [h.id for h in hosts]

        # 为每台主机添加正常 metrics
        now = datetime.now(timezone.utc)
        for h in hosts:
            for i in range(5):
                metric = HostMetric(
                    host_id=h.id,
                    cpu_percent=15.0 + i * 2,
                    memory_percent=40.0 + i,
                    disk_percent=35.0,
                    network_in_bytes=1024 * 100,
                    network_out_bytes=1024 * 50,
                    timestamp=now - timedelta(minutes=5 - i),
                )
                db.add(metric)

        # 创建告警规则：磁盘使用率 > 90%
        rule = AlertRule(
            name="Disk Usage Critical",
            description="Disk usage exceeds 90%",
            metric="disk_percent",
            operator=">",
            threshold=90.0,
            severity="critical",
            duration_seconds=0,
            is_enabled=True,
        )
        db.add(rule)

        # 创建服务
        svc_nginx = Service(
            name="nginx-proxy",
            display_name="Nginx Reverse Proxy",
            service_type="web",
            host_id=hosts[0].id,
            status="running",
            port=80,
        )
        svc_app = Service(
            name="nightmend-app",
            display_name="NightMend Application",
            service_type="app",
            host_id=hosts[1].id,
            status="running",
            port=8000,
        )
        svc_pg = Service(
            name="postgresql",
            display_name="PostgreSQL Database",
            service_type="database",
            host_id=hosts[2].id,
            status="running",
            port=5432,
        )
        db.add_all([svc_nginx, svc_app, svc_pg])
        await db.flush()

        # 创建服务依赖
        db.add(ServiceDependency(
            source_service_id=svc_nginx.id,
            target_service_id=svc_app.id,
            dependency_type="http",
        ))
        db.add(ServiceDependency(
            source_service_id=svc_app.id,
            target_service_id=svc_pg.id,
            dependency_type="tcp",
        ))

        await db.commit()
        logger.info("Demo: seeded %d hosts, alert rule, 3 services, 2 dependencies", len(hosts))

    # 设置 Redis 中的正常 metrics
    redis = await get_redis()
    for hid in demo_host_ids:
        normal_metrics = json.dumps({
            "cpu_percent": 12.5,
            "memory_percent": 45.0,
            "disk_percent": 35.0,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        await redis.set(f"metrics:latest:{hid}", normal_metrics, ex=3600)

    await _update_demo_state(phase="exploring")
    logger.info("Demo: seed complete, entering exploration phase")


async def inject_fault():
    """
    注入故障：将 demo-nginx-01 的磁盘使用率设为 96%。
    alert_engine 下一次循环会检测到并触发告警。
    """
    await _update_demo_state(phase="injecting")
    host_id = _demo_state["host_id"]
    if not host_id:
        logger.error("Demo: no host_id, cannot inject fault")
        return

    logger.info("Demo: injecting disk fault on host %d", host_id)

    # 更新 Redis metrics
    redis = await get_redis()
    fault_metrics = json.dumps({
        "cpu_percent": 15.0,
        "memory_percent": 48.0,
        "disk_percent": 96.2,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    await redis.set(f"metrics:latest:{host_id}", fault_metrics, ex=3600)

    # 同时写入 DB metrics 让 alert_engine 能检测到
    from app.models.host_metric import HostMetric
    async with AsyncSessionLocal() as db:
        metric = HostMetric(
            host_id=host_id,
            cpu_percent=15.0,
            memory_percent=48.0,
            disk_percent=96.2,
            network_in_bytes=1024 * 100,
            network_out_bytes=1024 * 50,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(metric)
        await db.commit()

    # 发布事件通知前端
    await redis.publish("nightmend:demo:fault_injected", json.dumps({
        "host_id": host_id,
        "metric": "disk_percent",
        "value": 96.2,
    }))

    logger.info("Demo: fault injected, waiting for alert engine detection")


async def start_auto_diagnosis(alert_id: int):
    """
    自动创建 OpsSession 并启动 AI 诊断。
    由 alert_engine 触发告警后调用。
    """
    from app.models.ops_session import OpsSession
    from app.models.user import User

    await _update_demo_state(phase="diagnosing", alert_id=alert_id)
    host_id = _demo_state["host_id"]

    logger.info("Demo: starting auto-diagnosis for alert %d on host %d", alert_id, host_id)

    async with AsyncSessionLocal() as db:
        # 获取或创建 demo 用户
        result = await db.execute(
            select(User).where(User.email == "demo@vigilops.io")
        )
        demo_user = result.scalar_one_or_none()
        if not demo_user:
            # fallback: 用第一个 admin 用户
            result = await db.execute(
                select(User).where(User.role == "admin").limit(1)
            )
            demo_user = result.scalar_one_or_none()

        if not demo_user:
            logger.error("Demo: no demo user found, cannot start diagnosis")
            return

        # 创建 demo session
        session_id = str(uuid.uuid4())
        session = OpsSession(
            id=session_id,
            user_id=demo_user.id,
            title="Autopilot Demo — 磁盘告警自动诊断",
            status="active",
        )
        db.add(session)
        await db.commit()

        await _update_demo_state(session_id=session_id)

    # 发布 session 创建事件，通知前端
    redis = await get_redis()
    await redis.publish("nightmend:demo:session_created", json.dumps({
        "session_id": session_id,
        "host_id": host_id,
        "alert_id": alert_id,
    }))

    # 启动 AI 诊断（后台任务）
    asyncio.create_task(_run_diagnosis(session_id, demo_user.id, host_id))


async def _run_diagnosis(session_id: str, user_id: int, host_id: int):
    """运行 AI 诊断流程。"""
    from app.services.ops_agent_loop import OpsAgentLoop

    try:
        loop = OpsAgentLoop(session_id, user_id)
        # 设置 auto_approve 标记
        loop._demo_auto_approve = True

        user_message = (
            "系统检测到 demo-nginx-01 磁盘使用率 96.2%（critical 级别告警）。"
            "请诊断根因并执行修复。"
        )

        redis = await get_redis()
        ws_channel = f"ops_ws:{session_id}"

        async for event in loop.run(
            user_message=user_message,
            host_id=host_id,
        ):
            # 将事件推送到 WebSocket channel，前端自动接收
            await redis.publish(ws_channel, json.dumps(event, default=str))

        await _update_demo_state(phase="complete")
        logger.info("Demo: diagnosis complete for session %s", session_id)

        # 发布完成事件
        await redis.publish("nightmend:demo:complete", json.dumps({
            "session_id": session_id,
            "host_id": host_id,
        }))

    except Exception as e:
        logger.error("Demo: diagnosis failed: %s", e, exc_info=True)
        await _update_demo_state(phase="error")


async def _find_demo_alert() -> int | None:
    """查找 demo 主机上最新的 firing 状态告警。"""
    from app.models.alert import Alert
    host_id = _demo_state["host_id"]
    if not host_id:
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert)
            .where(Alert.host_id == host_id, Alert.status == "firing")
            .order_by(Alert.id.desc())
            .limit(1)
        )
        alert = result.scalar_one_or_none()
        return alert.id if alert else None


async def run_demo_flow():
    """
    Demo 主流程：seed → 等待 → 注入故障 → 触发告警引擎。
    在 main.py lifespan 中作为后台任务启动。
    """
    await _update_demo_state(started_at=datetime.now(timezone.utc))

    try:
        # Step 1: Seed data
        await seed_demo_data()

        # Step 2: 等待用户探索产品
        delay = settings.demo_fault_delay_seconds
        logger.info("Demo: exploration phase, fault injection in %ds", delay)
        await asyncio.sleep(delay)

        # Step 3: 注入故障
        await inject_fault()

        # Step 4: 立即触发一次告警引擎评估（不等 60 秒循环）
        from app.tasks.alert_engine import evaluate_host_rules
        logger.info("Demo: triggering immediate alert evaluation")
        await evaluate_host_rules()

        # 查找新创建的告警
        alert_id = await _find_demo_alert()
        if alert_id:
            await start_auto_diagnosis(alert_id)
        else:
            logger.warning("Demo: no alert after first eval, retrying in 10s")
            await asyncio.sleep(10)
            await evaluate_host_rules()
            alert_id = await _find_demo_alert()
            if alert_id:
                await start_auto_diagnosis(alert_id)
            else:
                logger.error("Demo: fault injection did not trigger alert after retry")
                await _update_demo_state(phase="error")

    except Exception as e:
        logger.error("Demo: flow failed: %s", e, exc_info=True)
        await _update_demo_state(phase="error")
