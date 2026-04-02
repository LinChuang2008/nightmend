"""
修复日志模型 (Remediation Log Model)

记录每次自动修复的完整轨迹和生命周期，包括诊断结果、执行命令、验证结果等。
为自动修复系统提供审计跟踪、风险管控和执行状态监控功能。

Records the complete trace and lifecycle of each automatic remediation,
including diagnosis results, executed commands, verification results, etc.
Provides audit tracking, risk control, and execution status monitoring for the auto-remediation system.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RemediationLog(Base):
    """
    修复日志表 (Remediation Log Table)
    
    记录每次自动修复任务的完整生命周期，从告警触发到修复完成的全过程。
    包含风险评估、审批流程、执行状态、验证结果等关键信息，确保修复过程的可追溯性和安全性。
    
    Table for recording the complete lifecycle of each auto-remediation task,
    from alert triggering to remediation completion. Includes risk assessment,
    approval processes, execution status, verification results, and other key information.
    """
    __tablename__ = "remediation_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)  # 主键 ID (Primary Key ID)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)  # 修复会话 ID，用于关联同一修复流程的多条记录 (Remediation Session ID for correlating records in the same remediation flow)
    alert_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)  # 触发告警 ID (Triggering Alert ID)
    host_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)  # 目标主机 ID (Target Host ID)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # 修复状态：等待/诊断/执行/验证/成功/失败/升级/待审批/已批准/已拒绝 (Status: pending/diagnosing/executing/verifying/success/failed/escalated/pending_approval/approved/rejected)
    risk_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 风险级别：自动/确认/阻止 (Risk Level: auto/confirm/block)
    runbook_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 使用的 Runbook 名称 (Used Runbook Name)
    diagnosis_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # AI 诊断结果 JSON 数据 (AI Diagnosis Results JSON)
    command_results_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # 命令执行结果列表 JSON (Command Execution Results JSON)
    verification_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # 修复验证是否通过 (Verification Passed)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 阻止修复的原因 (Blocked Reason)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")  # 触发方式：自动/手动 (Triggered By: auto/manual)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 审批人用户 ID (Approver User ID)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # 审批时间 (Approval Time)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 修复开始时间 (Remediation Start Time)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # 修复完成时间 (Remediation Completion Time)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # 记录创建时间 (Record Creation Time)
