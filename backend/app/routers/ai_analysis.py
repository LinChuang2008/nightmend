"""
AI 分析路由模块

提供 AI 洞察查询、告警根因分析、日志异常分析等接口。
将原先分散/缺失的 AI 分析端点统一收拢到此路由。
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.ai_insight import AIInsight
from app.models.alert import Alert
from app.models.host import Host
from app.models.user import User
from app.services.llm_client import chat_completion, LLMClientError
from app.schemas.ai_insight import (
    GenerateRunbookRequest,
    GenerateRunbookResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["ai-analysis"])


# ---------- AI 洞察 ----------

@router.get("/insights")
async def list_insights(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    alert_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分页查询 AI 洞察列表。"""
    query = select(AIInsight).order_by(desc(AIInsight.created_at))
    count_q = select(func.count(AIInsight.id))

    if severity:
        query = query.where(AIInsight.severity == severity)
        count_q = count_q.where(AIInsight.severity == severity)
    if status:
        query = query.where(AIInsight.status == status)
        count_q = count_q.where(AIInsight.status == status)
    if alert_id:
        query = query.where(AIInsight.related_alert_id == alert_id)
        count_q = count_q.where(AIInsight.related_alert_id == alert_id)

    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(query.offset(offset).limit(limit))).scalars().all()

    items = [
        {
            "id": r.id,
            "insight_type": r.insight_type,
            "severity": r.severity,
            "title": r.title,
            "summary": r.summary,
            "details": r.details,
            "related_host_id": r.related_host_id,
            "related_alert_id": r.related_alert_id,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "conclusion": r.summary,
        }
        for r in rows
    ]
    return {"total": total, "items": items}


@router.get("/insights/{insight_id}")
async def get_insight(
    insight_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单条 AI 洞察详情。"""
    row = (
        await db.execute(select(AIInsight).where(AIInsight.id == insight_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "洞察不存在")
    return {
        "id": row.id,
        "insight_type": row.insight_type,
        "severity": row.severity,
        "title": row.title,
        "summary": row.summary,
        "details": row.details,
        "related_host_id": row.related_host_id,
        "related_alert_id": row.related_alert_id,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ---------- 告警根因分析 ----------

@router.post("/root-cause")
async def root_cause_analysis(
    alert_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """对指定告警进行 AI 根因分析，返回结构化结果。"""
    alert = (
        await db.execute(select(Alert).where(Alert.id == alert_id))
    ).scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "告警不存在")

    host = None
    if alert.host_id:
        host = (
            await db.execute(select(Host).where(Host.id == alert.host_id))
        ).scalar_one_or_none()

    prompt = (
        "你是资深运维专家。根据以下告警信息进行根因分析，输出 JSON 格式：\n"
        '{"root_cause":"根因描述","impact":"影响范围","suggestions":["建议1","建议2"],"severity":"low|medium|high|critical"}\n'
        "仅输出 JSON，不要包含其他文字。"
    )

    alert_context = (
        f"告警名称: {alert.title}\n"
        f"严重级别: {alert.severity}\n"
        f"触发时间: {alert.fired_at}\n"
        f"告警消息: {alert.message or '无'}\n"
    )
    if host:
        alert_context += f"主机: {host.display_name or host.hostname} ({host.public_ip or host.private_ip or host.ip_address})\n"

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": alert_context},
    ]

    try:
        content = await chat_completion(messages, max_tokens=800, temperature=0.2, feature_key="alert_analysis")
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()
        parsed = json.loads(content)
    except LLMClientError as e:
        raise HTTPException(503, f"AI 服务不可用: {e}")
    except Exception:
        parsed = {
            "root_cause": content if 'content' in dir() else "分析失败",
            "impact": "未知",
            "suggestions": [],
            "severity": "medium",
        }

    insight = AIInsight(
        insight_type="root_cause",
        severity=parsed.get("severity", "info"),
        title=f"根因分析 - {alert.title[:80]}",
        summary=parsed.get("root_cause", ""),
        details=parsed,
        related_alert_id=alert.id,
        related_host_id=alert.host_id,
        status="new",
    )
    db.add(insight)
    await db.commit()

    return parsed


# ---------- 告警快速分析 ----------

@router.get("/analyze")
async def analyze_alert(
    alert_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """对告警进行快速 AI 分析（优先返回缓存的洞察结果）。"""
    existing = (
        await db.execute(
            select(AIInsight)
            .where(AIInsight.related_alert_id == alert_id)
            .order_by(desc(AIInsight.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing:
        return {
            "summary": existing.summary,
            "analysis": existing.details,
            "root_cause": existing.details.get("root_cause") if existing.details else None,
            "cached": True,
        }

    alert = (
        await db.execute(select(Alert).where(Alert.id == alert_id))
    ).scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "告警不存在")

    prompt = (
        "你是运维助手，对以下告警给出简要分析（200字以内），包括可能原因和建议操作。"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"告警: {alert.title}\n级别: {alert.severity}\n消息: {alert.message or '无'}"},
    ]

    try:
        analysis_text = await chat_completion(messages, max_tokens=500, temperature=0.2, feature_key="alert_analysis")
    except LLMClientError as e:
        raise HTTPException(503, f"AI 服务不可用: {e}")

    insight = AIInsight(
        insight_type="quick_analysis",
        severity=alert.severity or "info",
        title=f"快速分析 - {alert.title[:80]}",
        summary=analysis_text.strip(),
        details={"analysis": analysis_text.strip()},
        related_alert_id=alert.id,
        related_host_id=alert.host_id,
        status="new",
    )
    db.add(insight)
    await db.commit()

    return {
        "summary": analysis_text.strip(),
        "analysis": {"analysis": analysis_text.strip()},
        "root_cause": None,
        "cached": False,
    }


# ---------- 日志异常分析（Dashboard 用） ----------

@router.post("/analyze-logs")
async def analyze_logs_on_demand(
    hours: int = Query(1, ge=1, le=24),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按需分析最近异常日志，返回结构化结果。供 Dashboard 日志异常区域使用。"""
    from datetime import datetime, timezone, timedelta
    from app.models.log_entry import LogEntry

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = (
        select(LogEntry)
        .where(
            LogEntry.timestamp >= since,
            LogEntry.level.in_(["WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"]),
        )
        .order_by(LogEntry.timestamp.desc())
        .limit(200)
    )
    entries = (await db.execute(q)).scalars().all()

    if not entries:
        return {"summary": "最近无异常日志", "log_count": 0, "severity": "info", "details": None}

    logs_data = [
        {
            "timestamp": str(e.timestamp),
            "level": e.level,
            "service": e.service,
            "message": (e.message or "")[:300],
        }
        for e in entries
    ]

    prompt = (
        "你是运维异常检测助手。分析以下异常日志，输出 JSON：\n"
        '{"title":"简要标题(30字内)","summary":"分析摘要(200字内)","severity":"info|warning|critical","patterns":["发现的异常模式1","模式2"],"suggestions":["建议1","建议2"]}\n'
        "仅输出 JSON。"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(logs_data[:100], ensure_ascii=False)},
    ]

    try:
        content = await chat_completion(messages, max_tokens=600, temperature=0.1, feature_key="log_analysis")
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()
        parsed = json.loads(content)
    except LLMClientError as e:
        raise HTTPException(503, f"AI 服务不可用: {e}")
    except Exception:
        parsed = {"title": "日志分析", "summary": content if 'content' in dir() else "分析失败", "severity": "warning", "patterns": [], "suggestions": []}

    insight = AIInsight(
        insight_type="log_analysis",
        severity=parsed.get("severity", "info"),
        title=parsed.get("title", "日志异常分析"),
        summary=parsed.get("summary", ""),
        details=parsed,
        status="new",
    )
    db.add(insight)
    await db.commit()

    return {
        "summary": parsed.get("summary", ""),
        "title": parsed.get("title", ""),
        "severity": parsed.get("severity", "info"),
        "log_count": len(entries),
        "patterns": parsed.get("patterns", []),
        "suggestions": parsed.get("suggestions", []),
        "details": parsed,
    }


# ── AI 生成 Runbook 的系统提示 ──────────────────────────────────────────────
GENERATE_RUNBOOK_SYSTEM_PROMPT = """你是 NightMend AI 运维自动化专家，负责根据用户的自然语言描述生成可执行的运维 Runbook。

生成要求：
1. 生成的命令必须安全，禁止使用 rm -rf /、dd if=、mkfs、fdisk、fork bomb 等危险命令
2. 每个步骤应包含清晰的名称和对应的 Linux 命令
3. 命令应使用变量模板（如 {service_name}、{host}）以便复用
4. 合理设置超时时间（简单查询 10 秒，重启操作 60 秒，复杂操作 120 秒）
5. 尽可能为有风险的步骤提供回滚命令
6. 触发关键词应覆盖该场景可能出现的告警关键词
7. 尽可能给出明确的告警类型列表 match_alert_types，用于精确匹配
8. 如适合该场景，请提供 verify_steps 用于执行后校验

请严格以 JSON 格式返回（不要 markdown 代码块）：
{
  "name": "runbook 名称（英文下划线命名，如 nginx_restart）",
  "description": "中文描述此 runbook 的用途",
  "match_alert_types": ["alert_type_1", "alert_type_2"],
  "trigger_keywords": ["关键词1", "关键词2"],
  "risk_level": "auto|confirm|manual|block",
  "steps": [
    {
      "name": "步骤名称",
      "command": "要执行的命令",
      "timeout_sec": 30,
      "rollback_command": "回滚命令（可选，可为 null）"
    }
  ],
  "verify_steps": [
    {
      "name": "验证步骤名称",
      "command": "用于验证修复是否生效的命令",
      "timeout_sec": 30,
      "rollback_command": null
    }
  ]
}"""


@router.post("/generate-runbook", response_model=GenerateRunbookResponse)
async def generate_runbook(
    req: GenerateRunbookRequest,
    _user: User = Depends(get_current_user),
):
    """
    AI 生成 Runbook 接口

    根据自然语言描述，使用 AI 生成可执行的运维 Runbook。
    生成后会进行命令安全检查，标记不安全的命令。
    """
    from app.routers.custom_runbooks import validate_command_safety

    user_msg = f"请为以下运维场景生成一个 Runbook：\n\n{req.description}"
    if req.risk_level:
        user_msg += f"\n\n建议风险级别：{req.risk_level}"

    messages = [
        {"role": "system", "content": GENERATE_RUNBOOK_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    try:
        result_text = await chat_completion(messages, max_tokens=2000, feature_key="runbook_generation")
        # Parse JSON from LLM response (strip markdown fences if present)
        text = result_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()
        runbook_data = json.loads(text)

        # 覆盖风险级别（如果用户指定）
        if req.risk_level:
            runbook_data["risk_level"] = req.risk_level
        runbook_data.setdefault("match_alert_types", [])
        runbook_data.setdefault("trigger_keywords", [])
        runbook_data.setdefault("verify_steps", [])

        # 安全检查每个步骤
        safety_warnings: list[str] = []
        for i, step in enumerate(runbook_data.get("steps", [])):
            cmd = step.get("command", "")
            safe, msg = validate_command_safety(cmd)
            if not safe:
                safety_warnings.append(f"步骤 {i + 1} ({step.get('name', '')}): {msg}")

            rollback = step.get("rollback_command")
            if rollback:
                safe, msg = validate_command_safety(rollback)
                if not safe:
                    safety_warnings.append(f"步骤 {i + 1} 回滚命令: {msg}")
        for i, step in enumerate(runbook_data.get("verify_steps", [])):
            cmd = step.get("command", "")
            safe, msg = validate_command_safety(cmd)
            if not safe:
                safety_warnings.append(f"验证步骤 {i + 1} ({step.get('name', '')}): {msg}")

        return GenerateRunbookResponse(
            success=True,
            runbook=runbook_data,
            safety_warnings=safety_warnings,
        )

    except Exception as e:
        logger.error("AI generate runbook failed: %s", str(e))
        return GenerateRunbookResponse(
            success=False,
            error=f"AI 生成失败：{str(e)}",
        )
