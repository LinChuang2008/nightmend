"""Prometheus rules.yml 同步器 (Prometheus rules.yml Synchronizer)

职责 (Responsibilities):
    - 从 AlertRule 表读取 query_expr 非空的规则，生成 Prometheus 规则文件
    - 原子写入 /etc/prometheus/rules/nightmend.yml（写 tmp + rename）
    - 触发 POST /-/reload 让 sidecar 热加载，无需重启
    - 回填 prom_rule_synced_at 时间戳

产出格式 (Output Format, Prometheus spec):
    groups:
      - name: nightmend_<rule_id>
        rules:
          - alert: <name>
            expr: <query_expr>
            for: <for_duration_seconds>s
            labels:
              severity: <severity>
              nightmend_rule_id: "<id>"
            annotations:
              summary: <description>

调用契机 (When to invoke):
    - AlertRule 创建/更新/删除成功后（由 router 中的 hook 触发）
    - 启动时幂等同步一次（lifespan 钩子可选加）
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.alert import AlertRule

logger = logging.getLogger(__name__)

# 规则文件默认写入位置；docker compose 已把 ./prometheus/rules 挂到 /etc/prometheus/rules。
# 允许通过 env 覆盖，方便开发机/测试跑非容器环境。
DEFAULT_RULES_PATH = os.environ.get(
    "NIGHTMEND_PROM_RULES_PATH",
    "/etc/prometheus/rules/nightmend.yml",
)


def _rule_to_prom_dict(rule: AlertRule) -> dict[str, Any]:
    """单条 AlertRule 转换为 Prometheus 规则 dict。"""
    for_seconds = rule.for_duration_seconds or max(rule.duration_seconds or 0, 60)
    labels: dict[str, str] = {
        "severity": rule.severity or "warning",
        "nightmend_rule_id": str(rule.id),
    }
    if rule.target_type:
        labels["target_type"] = rule.target_type
    annotations: dict[str, str] = {
        "summary": rule.name or f"rule-{rule.id}",
    }
    if rule.description:
        annotations["description"] = rule.description
    return {
        "alert": rule.name or f"nightmend_rule_{rule.id}",
        "expr": rule.query_expr,
        "for": f"{for_seconds}s",
        "labels": labels,
        "annotations": annotations,
    }


def _atomic_write(path: str, content: str) -> None:
    """写 tmp 再 rename，避免 Prometheus 读到半截文件。"""
    directory = os.path.dirname(path) or "."
    Path(directory).mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".nightmend-rules-", suffix=".yml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def _trigger_reload() -> bool:
    """POST /-/reload；失败不抛，因 rules 文件已落盘，Prom 默认也会定期 load。"""
    base = settings.prometheus_remote_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(f"{base}/-/reload")
        if response.status_code == 200:
            return True
        logger.warning(
            "Prometheus reload returned %s: %s", response.status_code, response.text[:200]
        )
        return False
    except httpx.RequestError as exc:
        logger.warning("Prometheus reload request failed: %s", exc)
        return False


def build_rules_yaml(rules: list[AlertRule]) -> str:
    """纯函数：AlertRule 列表 → Prom rules.yml 字符串；便于测试。"""
    # 每条 rule 自成一个 group，方便单条生效/失效不影响其他。
    groups = [
        {
            "name": f"nightmend_{rule.id}",
            "rules": [_rule_to_prom_dict(rule)],
        }
        for rule in rules
        if rule.query_expr and rule.is_enabled
    ]
    payload = {"groups": groups}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


async def sync_rules_to_prometheus(
    db: AsyncSession,
    *,
    rules_path: str | None = None,
    reload_sidecar: bool = True,
) -> dict[str, Any]:
    """同步主入口。返回统计数据，便于 API 层回显。"""
    if not settings.prometheus_remote_enabled:
        # 未启用 sidecar 时不写文件，避免在不跑 Prom 的部署里留 artifact。
        return {"synced": 0, "skipped": True, "reason": "prometheus_remote_disabled"}

    path = rules_path or DEFAULT_RULES_PATH

    result = await db.execute(
        select(AlertRule).where(AlertRule.query_expr.isnot(None)).order_by(AlertRule.id)
    )
    rules = list(result.scalars().all())

    content = build_rules_yaml(rules)
    _atomic_write(path, content)

    now = datetime.now(timezone.utc)
    eligible_ids = [r.id for r in rules if r.query_expr and r.is_enabled]
    if eligible_ids:
        # 只标记实际写入规则的行，失效 / 空 expr 的记录不触碰
        await db.execute(
            AlertRule.__table__.update()
            .where(AlertRule.id.in_(eligible_ids))
            .values(prom_rule_synced_at=now)
        )
        await db.commit()

    reloaded = False
    if reload_sidecar:
        reloaded = await _trigger_reload()

    logger.info(
        "Prometheus rules synced: path=%s rules=%d eligible=%d reloaded=%s",
        path, len(rules), len(eligible_ids), reloaded,
    )
    return {
        "synced": len(eligible_ids),
        "total_with_expr": len(rules),
        "path": path,
        "reloaded": reloaded,
        "skipped": False,
    }
