"""
VigilOps 自动修复系统 - 核心 Agent 编排器
VigilOps Remediation System - Core Agent Orchestrator

这是 VigilOps 自动修复系统的核心组件，负责端到端的告警处理流程：
This is the core component of VigilOps remediation system, handling end-to-end alert processing flow:

流程 (Flow): 
告警 (Alert) → AI 诊断 (AI Diagnosis) → Runbook 匹配 (Runbook Matching) → 
安全检查 (Safety Check) → 命令执行 (Command Execution) → 验证 (Verification) → 
结果持久化 (Result Persistence)

特性 (Features):
- 多层安全检查：熔断器、限流器、风险评估
- AI 驱动的智能诊断和修复建议
- 可扩展的 Runbook 注册机制
- 完整的审计日志和通知系统
- 异步执行，支持超时控制

作者：VigilOps Team
版本：v1.0
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

UTC = timezone.utc
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.remediation_log import RemediationLog
from app.services.memory_client import memory_client
from app.services.notifier import send_remediation_notification
from .ai_client import RemediationLLMClient
from .command_executor import CommandExecutor
from .models import (
    CommandResult,
    Diagnosis,
    RemediationAlert,
    RemediationResult,
    RiskLevel,
    RunbookDefinition,
    RunbookStep,
)
from .runbook_registry import RunbookRegistry
from .safety import CircuitBreaker, RateLimiter, assess_risk, check_command_safety

logger = logging.getLogger(__name__)


class RemediationAgent:
    """AI 驱动的自动修复 Agent (AI-Driven Automated Remediation Agent)
    
    这是 VigilOps 自动修复系统的核心控制器，负责协调各个子组件完成智能修复任务。
    This is the core controller of VigilOps remediation system, coordinating various sub-components
    to complete intelligent remediation tasks.
    
    主要职责 (Primary Responsibilities):
    1. 接收告警并进行 AI 智能诊断
    2. 匹配合适的 Runbook 执行方案
    3. 执行多层安全检查（熔断、限流、风险评估）
    4. 协调远程命令执行和结果验证
    5. 维护修复记录和发送通知
    
    架构模式 (Architecture Pattern):
    采用责任链模式 (Chain of Responsibility) 和策略模式 (Strategy Pattern)
    每个处理步骤都可以独立替换和扩展
    
    安全机制 (Safety Mechanisms):
    - 熔断器 (Circuit Breaker): 防止故障主机过载
    - 限流器 (Rate Limiter): 控制执行频率
    - 风险评估 (Risk Assessment): 智能判断操作危险性
    - 命令白名单 (Command Whitelist): 防止恶意命令执行
    """

    def __init__(
        self,
        ai_client: RemediationLLMClient,
        executor: Optional[CommandExecutor] = None,
        registry: Optional[RunbookRegistry] = None,
        rate_limiter: Optional[RateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        """初始化修复 Agent (Initialize Remediation Agent)
        
        Args:
            ai_client: AI 诊断客户端 (AI diagnosis client)
            executor: 命令执行器，默认为 dry_run 模式 (Command executor, defaults to dry_run mode)
            registry: Runbook 注册中心 (Runbook registry)
            rate_limiter: 限流器，防止频繁执行 (Rate limiter to prevent frequent execution)  
            circuit_breaker: 熔断器，保护故障主机 (Circuit breaker to protect failing hosts)
        
        注意 (Note):
        所有可选参数都有合理的默认值，支持依赖注入测试
        All optional parameters have reasonable defaults, supporting dependency injection for testing
        """
        self.ai = ai_client
        self.executor = executor or CommandExecutor(dry_run=True)
        self.registry = registry or RunbookRegistry()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    async def handle_alert(
        self,
        alert: RemediationAlert,
        db: AsyncSession,
        context: Optional[dict[str, Any]] = None,
        triggered_by: str = "auto",
        existing_log_id: Optional[int] = None,
    ) -> RemediationResult:
        """主入口：端到端处理告警的完整流程 (Main Entry: End-to-End Alert Processing)

        这是整个自动修复系统的核心方法，负责协调所有子组件完成一次完整的修复任务。
        This is the core method of the entire automated remediation system, coordinating all
        sub-components to complete a full remediation task.

        处理流程 (Processing Flow):
        1. 创建数据库记录，开始审计日志
        2. 熔断器检查：防止对故障主机过度操作
        3. AI 智能诊断：分析告警原因和严重程度
        4. Runbook 匹配：根据诊断结果选择修复方案
        5. 风险评估：评估操作的安全等级
        6. 限流检查：防止短时间内频繁执行
        7. 安全执行：运行修复命令并验证结果
        8. 结果持久化：更新数据库并发送通知

        Args:
            alert: 待处理的告警信息 (Alert information to be processed)
            db: 数据库会话 (Database session)
            context: 额外上下文信息，用于 AI 诊断 (Additional context for AI diagnosis)
            triggered_by: 触发方式："auto"、"manual"、"schedule" (Trigger method)
            existing_log_id: 已有的修复记录 ID，避免重复创建 (Existing log ID to avoid duplicate creation)

        Returns:
            RemediationResult: 包含执行状态、诊断结果、命令输出等完整信息

        异常处理 (Exception Handling):
        所有异常都会被捕获并转换为 RemediationResult，确保系统稳定性
        """
        logger.info("Handling alert: %s", alert.summary())

        # 复用已有记录或创建新记录
        if existing_log_id:
            from sqlalchemy import select
            result = await db.execute(
                select(RemediationLog).where(RemediationLog.id == existing_log_id)
            )
            log = result.scalar_one_or_none()
            if log:
                log.status = "diagnosing"
                await db.flush()
            else:
                log = RemediationLog(
                    alert_id=alert.alert_id,
                    host_id=alert.host_id,
                    status="diagnosing",
                    triggered_by=triggered_by,
                )
                db.add(log)
                await db.flush()
        else:
            log = RemediationLog(
                alert_id=alert.alert_id,
                host_id=alert.host_id,
                status="diagnosing",
                triggered_by=triggered_by,
            )
            db.add(log)
            await db.flush()

        # Step 0: 熔断器检查 - 保护故障主机免受过度操作
        # Step 0: Circuit breaker check - protect failing hosts from excessive operations
        if self.circuit_breaker.is_open(alert.host):
            logger.warning("Circuit breaker OPEN for host %s", alert.host)
            result = RemediationResult(
                alert_id=alert.alert_id,
                success=False,
                blocked_reason=f"Circuit breaker open for host {alert.host}",
                escalated=True,
            )
            await self._update_log(db, log, result, alert)
            return result

        # Step 1: AI 智能诊断 - 分析告警根因和推荐修复方案
        # Step 1: AI intelligent diagnosis - analyze root cause and recommend remediation
        diagnosis = await self._diagnose(alert, context)

        # Step 2: 匹配 Runbook - 根据诊断结果选择合适的修复脚本
        # Step 2: Match Runbook - select appropriate remediation script based on diagnosis
        runbook = self.registry.match(alert, diagnosis)
        if not runbook:
            result = RemediationResult(
                alert_id=alert.alert_id,
                success=False,
                diagnosis=diagnosis,
                blocked_reason="No matching runbook found",
                escalated=True,
            )
            await self._update_log(db, log, result, alert)
            return result

        # Step 3: 风险评估 - 综合考虑 Runbook 危险性、诊断置信度、历史执行频率
        # Step 3: Risk assessment - consider runbook danger, diagnosis confidence, execution history
        recent_count = self.rate_limiter.recent_count(alert.host)
        risk = assess_risk(runbook, diagnosis, recent_count)

        # Step 4: 限流检查 - 防止短时间内频繁执行相同操作
        # Step 4: Rate limiting check - prevent frequent execution of same operation
        if not self.rate_limiter.can_execute(
            alert.host, runbook.name, runbook.cooldown_seconds
        ):
            result = RemediationResult(
                alert_id=alert.alert_id,
                success=False,
                runbook_name=runbook.name,
                diagnosis=diagnosis,
                risk_level=risk,
                blocked_reason=f"Rate limited: {runbook.name} on {alert.host}",
                escalated=True,
            )
            await self._update_log(db, log, result, alert)
            return result

        # Step 5: 基于风险等级决定执行策略
        # Step 5: Determine execution strategy based on risk level
        if risk == RiskLevel.BLOCK:  # 风险过高，禁止自动执行 (Risk too high, block automatic execution)
            result = RemediationResult(
                alert_id=alert.alert_id,
                success=False,
                runbook_name=runbook.name,
                diagnosis=diagnosis,
                risk_level=risk,
                blocked_reason="Risk assessment: BLOCK",
                escalated=True,
            )
            await self._update_log(db, log, result, alert)
            return result

        if risk == RiskLevel.CONFIRM:  # 需要人工确认，进入审批流程 (Requires human confirmation, enter approval process)
            result = RemediationResult(
                alert_id=alert.alert_id,
                success=False,
                runbook_name=runbook.name,
                diagnosis=diagnosis,
                risk_level=risk,
                blocked_reason="Needs human confirmation (risk=confirm)",
                escalated=True,
            )
            log.status = "pending_approval"
            await self._update_log(db, log, result, alert)
            return result

        # risk == AUTO：风险可接受，开始自动执行修复
        # risk == AUTO: Risk acceptable, start automatic remediation execution
        log.status = "executing"  # 更新状态为执行中 (Update status to executing)
        await db.flush()

        result = await self._execute_runbook(alert, diagnosis, runbook, risk)
        await self._update_log(db, log, result, alert)
        return result

    async def _diagnose(
        self, alert: RemediationAlert, context: Optional[dict[str, Any]]
    ) -> Diagnosis:
        """AI 智能诊断告警根因 (AI Intelligent Alert Root Cause Analysis)
        
        调用 AI 客户端分析告警信息，识别可能的根本原因并给出修复建议。
        Call AI client to analyze alert information, identify possible root causes and 
        provide remediation suggestions.
        
        Args:
            alert: 告警信息 (Alert information)
            context: 补充上下文，如系统指标、日志片段等 (Additional context like metrics, log snippets)
            
        Returns:
            Diagnosis: 包含根因分析、置信度、推荐 Runbook 等信息
            
        异常处理 (Exception Handling):
        AI 诊断失败时返回默认诊断结果，确保流程不中断
        """
        try:
            diagnosis = await self.ai.diagnose(alert, context or {})
            logger.info(
                "Diagnosis: cause=%s, confidence=%.2f, suggested=%s",
                diagnosis.root_cause, diagnosis.confidence, diagnosis.suggested_runbook,
            )
            return diagnosis
        except Exception as e:
            logger.error("Diagnosis failed: %s", e)
            return Diagnosis(root_cause="Diagnosis error", confidence=0.0, reasoning=str(e))

    async def _execute_runbook(
        self,
        alert: RemediationAlert,
        diagnosis: Diagnosis,
        runbook: RunbookDefinition,
        risk: RiskLevel,
    ) -> RemediationResult:
        """执行 Runbook 修复脚本 (Execute Runbook Remediation Script)
        
        这是实际执行修复操作的核心方法，包含多层安全检查和结果验证。
        This is the core method for actual remediation execution, including multi-layer 
        security checks and result verification.
        
        执行流程 (Execution Flow):
        1. 逐个检查命令的安全性（防止恶意命令）
        2. 解析命令模板中的变量（如 {host}、{service} 等）
        3. 按顺序执行所有修复命令
        4. 如果定义了验证命令，执行验证确保修复生效
        5. 记录执行历史，更新熔断器状态
        
        Args:
            alert: 告警信息，用于命令变量解析
            diagnosis: AI 诊断结果，用于上下文记录
            runbook: 要执行的 Runbook 定义
            risk: 风险等级，用于审计记录
            
        Returns:
            RemediationResult: 包含执行状态、命令输出、验证结果等
        
        安全机制 (Security Mechanisms):
        - 命令白名单检查：只允许预定义的安全命令
        - 变量替换验证：防止命令注入攻击  
        - 执行超时保护：避免长时间阻塞
        """
        logger.info("Executing runbook: %s on %s", runbook.name, alert.host)

        # 预检查：确保所有命令都通过安全审核
        # Pre-check: ensure all commands pass security audit
        for step in runbook.commands:
            resolved_cmd = self._resolve_command(step.command, alert)  # 解析命令中的变量 (Resolve variables in command)
            is_safe, reason = check_command_safety(resolved_cmd)
            if not is_safe:  # 发现不安全命令，立即中止 (Found unsafe command, abort immediately)
                return RemediationResult(
                    alert_id=alert.alert_id,
                    success=False,
                    runbook_name=runbook.name,
                    diagnosis=diagnosis,
                    risk_level=risk,
                    blocked_reason=f"Unsafe command: {reason}",
                    escalated=True,
                )

        # 构建解析后的执行步骤列表
        # Build list of resolved execution steps  
        resolved_steps = [
            RunbookStep(
                description=s.description,
                command=self._resolve_command(s.command, alert),  # 将 {host}、{service} 等替换为实际值
                timeout_seconds=s.timeout_seconds,
            )
            for s in runbook.commands
        ]
        # 批量执行所有修复命令 (Execute all remediation commands in batch)
        command_results = await self.executor.execute_steps(resolved_steps)

        # 检查是否有命令执行失败 (Check if any command execution failed)
        any_failure = any(r.exit_code != 0 for r in command_results)

        # 执行修复效果验证 (Execute remediation effectiveness verification)
        verification_passed: bool | None = None
        if not any_failure and runbook.verify_commands:  # 只有修复命令成功才进行验证
            # 构建验证命令列表 (Build verification command list)
            resolved_verify = [
                RunbookStep(
                    description=s.description,
                    command=self._resolve_command(s.command, alert),
                    timeout_seconds=s.timeout_seconds,
                )
                for s in runbook.verify_commands
            ]
            verify_results = await self.executor.execute_steps(resolved_verify)
            command_results.extend(verify_results)  # 合并到总结果中 (Merge into total results)
            verification_passed = all(r.exit_code == 0 for r in verify_results)

        # 记录执行历史，用于限流控制 (Record execution history for rate limiting)
        self.rate_limiter.record_execution(alert.host, runbook.name)

        # 综合判断修复是否成功 (Comprehensive success determination)
        success = not any_failure and (verification_passed is not False)
        
        # 更新熔断器状态 (Update circuit breaker status)
        if success:
            self.circuit_breaker.record_success(alert.host)  # 成功则重置失败计数
        else:
            self.circuit_breaker.record_failure(alert.host)  # 失败则增加失败计数，可能触发熔断

        return RemediationResult(
            alert_id=alert.alert_id,
            success=success,
            runbook_name=runbook.name,
            diagnosis=diagnosis,
            risk_level=risk,
            command_results=command_results,
            verification_passed=verification_passed,
        )

    def _resolve_command(self, command: str, alert: RemediationAlert) -> str:
        """解析命令模板中的变量 (Resolve Variables in Command Template)
        
        将命令模板中的占位符替换为实际的告警信息，支持以下变量：
        Replace placeholders in command template with actual alert information, 
        supporting the following variables:
        
        - {host}: 告警主机名或IP (Alert hostname or IP)
        - {service}: 服务名称 (Service name) 
        - {port}: 端口号 (Port number)
        - 以及告警标签中的所有键值对 (And all key-value pairs in alert labels)
        
        Args:
            command: 包含占位符的命令模板 (Command template with placeholders)
            alert: 告警信息，用于变量替换 (Alert info for variable substitution)
            
        Returns:
            str: 解析后的可执行命令 (Resolved executable command)
            
        示例 (Example):
            模板: "systemctl restart {service} on {host}"  
            解析后: "systemctl restart nginx on web01.example.com"
        """
        import shlex
        # 安全: 先验证命令模板本身不包含危险模式（防止模板注入）
        _TEMPLATE_DANGEROUS = ['$(', '${', '`', '|', ';', '&&', '||']
        for pattern in _TEMPLATE_DANGEROUS:
            if pattern in command:
                raise ValueError(f"Command template contains dangerous pattern: {pattern!r}")
        # 首先替换标准的主机名变量，使用 shlex.quote 防止命令注入
        resolved = command.replace("{host}", shlex.quote(alert.host))

        # 然后替换告警标签中的所有自定义变量，同样进行安全转义
        for key, value in alert.labels.items():
            resolved = resolved.replace(f"{{{key}}}", shlex.quote(value))

        return resolved

    async def _update_log(
        self, db: AsyncSession, log: RemediationLog, result: RemediationResult,
        alert: RemediationAlert | None = None,
    ) -> None:
        """更新修复记录并处理后续操作 (Update Remediation Log and Handle Follow-up Actions)
        
        这是修复流程的最后一步，负责：
        This is the last step of remediation process, responsible for:
        
        1. 将执行结果持久化到数据库 (Persist execution results to database)
        2. 异步存储修复经验到记忆系统 (Asynchronously store remediation experience to memory system)
        3. 发送修复结果通知 (Send remediation result notifications)
        4. 完善审计日志链条 (Complete audit log chain)
        
        Args:
            db: 数据库会话 (Database session)
            log: 要更新的修复记录 (Remediation log to update)
            result: 修复执行结果 (Remediation execution result)
            alert: 原始告警信息，用于通知 (Original alert info for notifications)
            
        注意 (Note):
        记忆存储和通知发送都是异步的，不会阻塞主流程完成
        Memory storage and notification sending are asynchronous, won't block main process
        """
        # 根据执行结果更新最终状态 (Update final status based on execution result)
        if result.success:
            log.status = "success"  # 修复成功 (Remediation successful)
        elif result.escalated:
            if log.status != "pending_approval":  # 保持审批状态不被覆盖 (Preserve approval status)
                log.status = "escalated"  # 升级到人工处理 (Escalated to manual handling)
        else:
            log.status = "failed"  # 修复失败 (Remediation failed)

        # 更新详细的执行信息到数据库字段 (Update detailed execution info to database fields)
        log.runbook_name = result.runbook_name  # 使用的 Runbook 名称
        log.risk_level = result.risk_level.value if result.risk_level else None  # 风险等级
        log.diagnosis_json = result.diagnosis.model_dump() if result.diagnosis else None  # AI 诊断结果 (JSON)
        log.command_results_json = [r.model_dump() for r in result.command_results] if result.command_results else None  # 命令执行结果 (JSON)
        log.verification_passed = result.verification_passed  # 验证是否通过
        log.blocked_reason = result.blocked_reason  # 阻止原因（如有）
        log.completed_at = datetime.now(UTC)  # 完成时间戳

        await db.commit()

        # --- 异步存储修复经验到记忆系统（不阻塞主流程） ---
        self._store_remediation_experience(log, result, alert)

        # --- 发送修复结果通知 ---
        await self._notify_result(db, log, result, alert)

    def _store_remediation_experience(
        self, log: RemediationLog, result: RemediationResult,
        alert: RemediationAlert | None,
    ) -> None:
        """存储修复经验到长期记忆系统 (Store Remediation Experience to Long-term Memory System)
        
        将每次修复的关键信息存储到 Engram 系统中，用于：
        Store key information from each remediation to Engram system for:
        
        1. 积累修复模式和最佳实践 (Accumulate remediation patterns and best practices)
        2. 训练和优化 AI 诊断模型 (Train and optimize AI diagnosis models)  
        3. 生成运维洞察报告 (Generate operational insight reports)
        4. 支持故障根因分析 (Support failure root cause analysis)
        
        Args:
            log: 修复记录 (Remediation log)
            result: 修复结果 (Remediation result)
            alert: 原始告警 (Original alert)
            
        实现细节 (Implementation Details):
        使用异步任务避免阻塞主流程，存储失败不影响修复操作
        Uses async task to avoid blocking main process, storage failure doesn't affect remediation
        """
        alert_name = alert.alert_type if alert else "unknown"
        host = alert.host if alert else "unknown"
        status = log.status or "unknown"
        root_cause = result.diagnosis.root_cause if result.diagnosis else "N/A"
        runbook = result.runbook_name or "N/A"

        content = (
            f"修复经验 [{status}]: 告警={alert_name}, 主机={host}\n"
            f"根因: {root_cause}\n"
            f"Runbook: {runbook}\n"
            f"结果: {'成功' if result.success else '失败/升级'}"
        )
        if result.blocked_reason:
            content += f"\n原因: {result.blocked_reason}"

        try:
            asyncio.create_task(memory_client.store(content, source="vigilops-remediation"))
        except Exception:
            logger.debug("Failed to schedule remediation experience storage")

    async def _notify_result(
        self, db: AsyncSession, log: RemediationLog, result: RemediationResult,
        alert: RemediationAlert | None,
    ) -> None:
        """发送修复结果通知 (Send Remediation Result Notifications)
        
        根据系统配置和修复结果，通过已配置的通知渠道发送相应的通知消息。
        Send corresponding notification messages through configured channels based on 
        system configuration and remediation results.
        
        支持的通知场景 (Supported Notification Scenarios):
        1. 修复成功通知：包含耗时、使用的 Runbook 等信息
        2. 需要审批通知：包含审批链接和操作描述  
        3. 修复失败通知：包含失败原因和建议的后续操作
        
        通知渠道 (Notification Channels):
        复用 VigilOps 现有的 5 种通知渠道：钉钉、飞书、企微、邮件、Webhook
        
        Args:
            db: 数据库会话 (Database session)
            log: 修复记录 (Remediation log)
            result: 修复结果 (Remediation result)  
            alert: 原始告警信息 (Original alert information)
            
        配置控制 (Configuration Control):
        通过 settings.agent_notify_on_success 和 agent_notify_on_failure 控制是否发送
        """
        alert_name = alert.alert_type if alert else (result.runbook_name or "unknown")
        host = alert.host if alert else "unknown"

        try:
            # 成功通知：包含修复耗时和使用的 Runbook (Success notification: include duration and runbook used)
            if result.success and settings.agent_notify_on_success:
                duration = ""
                if log.completed_at and log.created_at:
                    delta = log.completed_at - log.created_at
                    duration = f"{delta.total_seconds():.1f}s"  # 计算修复耗时
                await send_remediation_notification(
                    db, kind="success", alert_name=alert_name, host=host,
                    runbook=result.runbook_name or "", duration=duration,
                )
            # 审批通知：需要人工确认的高风险操作 (Approval notification: high-risk operations requiring manual confirmation)
            elif log.status == "pending_approval" and settings.agent_notify_on_failure:
                await send_remediation_notification(
                    db, kind="approval", alert_name=alert_name, host=host,
                    action=result.blocked_reason or "",
                    approval_url=f"/remediation/{log.id}/approve",  # 包含审批页面链接
                )
            # 失败通知：修复失败或被阻止的情况 (Failure notification: remediation failed or blocked)
            elif not result.success and settings.agent_notify_on_failure:
                await send_remediation_notification(
                    db, kind="failure", alert_name=alert_name, host=host,
                    reason=result.blocked_reason or "unknown error",
                )
        except Exception:
            logger.exception("Failed to send remediation notification")
