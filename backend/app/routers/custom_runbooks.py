"""
自定义 Runbook CRUD API (Custom Runbook CRUD API)

提供自定义 Runbook 的创建、查询、更新、删除、导入/导出和 dry-run 功能。
"""
import json
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.user import User
from app.models.custom_runbook import CustomRunbook
from app.schemas.custom_runbook import (
    CustomRunbookCreate,
    CustomRunbookUpdate,
    CustomRunbookResponse,
    RunbookListResponse,
    DryRunRequest,
    DryRunResponse,
    DryRunStepResult,
)
from app.remediation.safety import check_command_safety, FORBIDDEN_PATTERNS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runbooks/custom", tags=["Custom Runbooks"])

# 额外的命令黑名单 (针对自定义 Runbook 更严格)
CUSTOM_RUNBOOK_FORBIDDEN = [
    r"rm\s+-rf",
    r"rm\s+-r\s+/",
    r"dd\s+if=",
    r"mkfs",
    r"fdisk",
    r"parted",
    r":\(\)\{",  # fork bomb
    r">\s*/dev/sd",
    r">\s*/dev/null\s*2>&1\s*&",  # background hidden exec
    r"nohup\s+.*&",
    r"eval\s+",
    r"\bexec\s+",
    r"python\s+-c",
    r"perl\s+-e",
    r"ruby\s+-e",
]
_CUSTOM_FORBIDDEN_RE = [re.compile(p, re.IGNORECASE) for p in CUSTOM_RUNBOOK_FORBIDDEN]


def validate_command_safety(command: str) -> tuple[bool, str]:
    """对自定义 Runbook 的命令执行双重安全检查"""
    # 检查 1: 自定义 Runbook 额外黑名单
    for pattern in _CUSTOM_FORBIDDEN_RE:
        if pattern.search(command):
            return False, f"Command matches forbidden pattern for custom runbooks: {pattern.pattern}"
    # 检查 2: 系统级安全检查
    safe, msg = check_command_safety(command)
    if not safe:
        return False, msg
    return True, "OK"


def validate_all_steps(steps: list) -> None:
    """验证所有步骤中的命令安全性"""
    for i, step in enumerate(steps):
        cmd = step.command if hasattr(step, "command") else step.get("command", "")
        safe, msg = validate_command_safety(cmd)
        if not safe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Step {i + 1} ({step.name if hasattr(step, 'name') else step.get('name', '')}): {msg}",
            )
        # 检查 rollback 命令
        rollback = step.rollback_command if hasattr(step, "rollback_command") else step.get("rollback_command")
        if rollback:
            safe, msg = validate_command_safety(rollback)
            if not safe:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Step {i + 1} rollback command: {msg}",
                )


@router.get("", response_model=List[CustomRunbookResponse])
async def list_custom_runbooks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取自定义 Runbook 列表"""
    query = select(CustomRunbook)
    if active_only:
        query = query.where(CustomRunbook.is_active == True)
    query = query.order_by(CustomRunbook.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/all", response_model=RunbookListResponse)
async def list_all_runbooks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取所有 Runbook (内置 + 自定义)"""
    from app.remediation.runbook_registry import RunbookRegistry
    registry = RunbookRegistry()

    # 内置 Runbook
    builtins = []
    for rb in registry.list_all():
        builtins.append({
            "id": None,
            "name": rb.name,
            "description": rb.description,
            "source": "builtin",
            "risk_level": rb.risk_level.value,
            "match_keywords": rb.match_keywords,
            "match_alert_types": rb.match_alert_types,
            "steps_count": len(rb.commands),
            "is_active": True,
        })

    # 自定义 Runbook
    result = await db.execute(
        select(CustomRunbook).order_by(CustomRunbook.created_at.desc())
    )
    customs = []
    for cr in result.scalars().all():
        customs.append({
            "id": cr.id,
            "name": cr.name,
            "description": cr.description,
            "source": "custom",
            "risk_level": cr.risk_level,
            "trigger_keywords": cr.trigger_keywords,
            "steps_count": len(cr.steps) if cr.steps else 0,
            "is_active": cr.is_active,
            "created_at": cr.created_at.isoformat() if cr.created_at else None,
        })

    items = builtins + customs
    return RunbookListResponse(items=items, total=len(items))


@router.get("/{runbook_id}", response_model=CustomRunbookResponse)
async def get_custom_runbook(
    runbook_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取单个自定义 Runbook 详情"""
    result = await db.execute(
        select(CustomRunbook).where(CustomRunbook.id == runbook_id)
    )
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Custom runbook not found")
    return runbook


@router.post("", response_model=CustomRunbookResponse, status_code=201)
async def create_custom_runbook(
    data: CustomRunbookCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    """创建自定义 Runbook"""
    # 检查名称唯一性
    existing = await db.execute(
        select(CustomRunbook).where(CustomRunbook.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Runbook with name '{data.name}' already exists")

    # 安全验证所有步骤命令
    validate_all_steps(data.steps)

    runbook = CustomRunbook(
        name=data.name,
        description=data.description,
        trigger_keywords=data.trigger_keywords,
        risk_level=data.risk_level,
        steps=[s.model_dump() for s in data.steps],
        safety_checks=data.safety_checks,
        created_by=user.id,
        is_active=data.is_active,
    )
    db.add(runbook)
    await db.commit()
    await db.refresh(runbook)
    logger.info("Created custom runbook '%s' by user %s", data.name, user.id)
    return runbook


@router.put("/{runbook_id}", response_model=CustomRunbookResponse)
async def update_custom_runbook(
    runbook_id: int,
    data: CustomRunbookUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
):
    """更新自定义 Runbook"""
    result = await db.execute(
        select(CustomRunbook).where(CustomRunbook.id == runbook_id)
    )
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Custom runbook not found")

    update_data = data.model_dump(exclude_unset=True)

    # 如果更新了名称，检查唯一性
    if "name" in update_data and update_data["name"] != runbook.name:
        existing = await db.execute(
            select(CustomRunbook).where(CustomRunbook.name == update_data["name"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Runbook with name '{update_data['name']}' already exists")

    # 如果更新了步骤，执行安全检查
    if "steps" in update_data and update_data["steps"]:
        validate_all_steps(data.steps)
        update_data["steps"] = [s.model_dump() for s in data.steps]

    for key, value in update_data.items():
        setattr(runbook, key, value)

    await db.commit()
    await db.refresh(runbook)
    logger.info("Updated custom runbook '%s' (id=%d) by user %s", runbook.name, runbook_id, user.id)
    return runbook


@router.delete("/{runbook_id}", status_code=204)
async def delete_custom_runbook(
    runbook_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """删除自定义 Runbook (仅管理员)"""
    result = await db.execute(
        select(CustomRunbook).where(CustomRunbook.id == runbook_id)
    )
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Custom runbook not found")

    await db.delete(runbook)
    await db.commit()
    logger.info("Deleted custom runbook '%s' (id=%d) by user %s", runbook.name, runbook_id, user.id)


@router.post("/{runbook_id}/dry-run", response_model=DryRunResponse)
async def dry_run_runbook(
    runbook_id: int,
    data: DryRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dry-run 模式：验证 Runbook 步骤的安全性并显示将执行的命令"""
    result = await db.execute(
        select(CustomRunbook).where(CustomRunbook.id == runbook_id)
    )
    runbook = result.scalar_one_or_none()
    if not runbook:
        raise HTTPException(status_code=404, detail="Custom runbook not found")

    step_results = []
    all_safe = True

    for step in runbook.steps:
        # 变量替换
        resolved_cmd = step["command"]
        for var_name, var_value in data.variables.items():
            resolved_cmd = resolved_cmd.replace(f"{{{var_name}}}", str(var_value))

        # 安全检查
        safe, msg = validate_command_safety(resolved_cmd)
        if not safe:
            all_safe = False

        rollback = step.get("rollback_command")
        if rollback:
            for var_name, var_value in data.variables.items():
                rollback = rollback.replace(f"{{{var_name}}}", str(var_value))

        step_results.append(DryRunStepResult(
            step_name=step["name"],
            resolved_command=resolved_cmd,
            timeout_sec=step.get("timeout_sec", 30),
            rollback_command=rollback,
            safety_check_passed=safe,
            safety_message=msg,
        ))

    return DryRunResponse(
        runbook_name=runbook.name,
        risk_level=runbook.risk_level,
        total_steps=len(step_results),
        steps=step_results,
        all_safe=all_safe,
    )


@router.get("/export/all")
async def export_runbooks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出所有自定义 Runbook 为 JSON"""
    result = await db.execute(
        select(CustomRunbook).order_by(CustomRunbook.created_at.asc())
    )
    runbooks = result.scalars().all()
    export_data = []
    for rb in runbooks:
        export_data.append({
            "name": rb.name,
            "description": rb.description,
            "trigger_keywords": rb.trigger_keywords,
            "risk_level": rb.risk_level,
            "steps": rb.steps,
            "safety_checks": rb.safety_checks,
            "is_active": rb.is_active,
        })
    return JSONResponse(
        content={"version": "1.0", "runbooks": export_data},
        headers={"Content-Disposition": "attachment; filename=custom_runbooks.json"},
    )


@router.post("/import")
async def import_runbooks(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """导入自定义 Runbook (JSON 格式，仅管理员)"""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only JSON files are accepted")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    runbooks_data = data.get("runbooks", [])
    if not isinstance(runbooks_data, list):
        raise HTTPException(status_code=400, detail="Invalid format: 'runbooks' must be a list")

    imported = 0
    skipped = 0
    errors = []

    for i, rb_data in enumerate(runbooks_data):
        name = rb_data.get("name", "").strip()
        if not name:
            errors.append(f"Item {i}: missing name")
            continue

        # 检查是否已存在
        existing = await db.execute(
            select(CustomRunbook).where(CustomRunbook.name == name)
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        steps = rb_data.get("steps", [])
        if not steps:
            errors.append(f"Item {i} ({name}): no steps defined")
            continue

        # 安全检查
        try:
            for j, step in enumerate(steps):
                cmd = step.get("command", "")
                safe, msg = validate_command_safety(cmd)
                if not safe:
                    raise ValueError(f"Step {j + 1}: {msg}")
        except ValueError as e:
            errors.append(f"Item {i} ({name}): {e}")
            continue

        runbook = CustomRunbook(
            name=name,
            description=rb_data.get("description", ""),
            trigger_keywords=rb_data.get("trigger_keywords", []),
            risk_level=rb_data.get("risk_level", "manual"),
            steps=steps,
            safety_checks=rb_data.get("safety_checks", []),
            created_by=user.id,
            is_active=rb_data.get("is_active", True),
        )
        db.add(runbook)
        imported += 1

    if imported > 0:
        await db.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }
