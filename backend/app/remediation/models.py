"""
NightMend 自动修复系统 - 数据模型定义
NightMend Remediation System - Data Model Definitions

这个模块定义了自动修复系统中所有核心数据结构的 Pydantic 模型。
This module defines Pydantic models for all core data structures in the remediation system.

设计理念 (Design Philosophy):
- 类型安全：使用 Pydantic 提供运行时类型检查和验证
- 数据一致性：统一的数据结构确保模块间的正确交互
- 序列化友好：支持 JSON 序列化，便于 API 交互和存储
- 文档自动生成：利用 Pydantic 的 schema 生成能力

模型分类 (Model Categories):
1. 枚举类型：风险等级等固定值集合
2. 诊断相关：AI 分析结果和推理过程
3. Runbook 相关：修复脚本定义和执行步骤
4. 执行相关：命令执行结果和状态信息
5. 告警相关：输入数据和处理结果

与 ORM 的关系 (Relationship with ORM):
- SQLAlchemy ORM：数据库持久化层
- Pydantic Models：业务逻辑数据传输层
- 两者互补，各司其职

技术特性 (Technical Features):
- 自动数据验证：字段类型和约束检查
- 默认值处理：合理的默认值设置
- 嵌套模型：支持复杂的数据结构组合
- 时间处理：统一使用 UTC 时区

作者：NightMend Team
版本：v1.0
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

UTC = timezone.utc
from typing import Any, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, enum.Enum):
    """修复操作风险等级 (Remediation Operation Risk Level)
    
    这是自动修复系统的核心安全分类，定义了三个风险等级来控制操作的执行策略。
    This is the core safety classification of the remediation system, defining three risk levels 
    to control operation execution strategies.
    
    风险等级说明 (Risk Level Descriptions):
    - AUTO: 自动执行，系统直接执行修复操作
    - CONFIRM: 需要确认，必须经过人工审批才能执行
    - BLOCK: 禁止执行，系统拒绝执行该操作
    
    决策依据 (Decision Criteria):
    - 操作的潜在影响范围
    - AI 诊断的置信度
    - 历史执行的成功率
    - 系统当前的健康状态
    
    应用场景 (Application Scenarios):
    - Runbook 定义时设置基础风险等级
    - 运行时根据诊断结果动态调整
    - 安全检查和审批流程的控制依据
    """
    AUTO = "auto"        # 自动执行 - 低风险操作，系统可以直接执行
    CONFIRM = "confirm"  # 需要确认 - 中等风险操作，需要人工审批
    BLOCK = "block"      # 禁止执行 - 高风险操作，系统拒绝执行


class Diagnosis(BaseModel):
    """AI 智能诊断结果 (AI Intelligent Diagnosis Result)
    
    封装了 AI 模型对告警进行分析后得出的诊断结论和相关信息。
    Encapsulates the diagnosis conclusions and related information obtained after 
    AI model analysis of alerts.
    
    数据结构说明 (Data Structure Description):
    - root_cause: 问题根本原因的简洁描述
    - confidence: AI 对诊断结果的置信度 (0.0-1.0)
    - suggested_runbook: AI 推荐的修复 Runbook 名称
    - reasoning: AI 的推理过程和依据
    - additional_context: 补充的上下文信息
    
    置信度指导原则 (Confidence Guidelines):
    - 0.8-1.0: 高置信度，AI 非常确定问题原因
    - 0.5-0.7: 中等置信度，AI 有合理的判断依据
    - 0.0-0.4: 低置信度，AI 不确定或缺乏足够信息
    
    使用场景 (Use Cases):
    - 风险评估：置信度影响最终的风险等级
    - Runbook 选择：优先使用 AI 推荐的 Runbook
    - 审计日志：记录 AI 的分析过程用于后续分析
    - 人工复核：低置信度的诊断需要人工确认
    """
    root_cause: str  # 根本原因描述 (Root cause description)
    confidence: float = Field(ge=0.0, le=1.0)  # 置信度，范围 0.0-1.0 (Confidence level, range 0.0-1.0)
    suggested_runbook: Optional[str] = None     # AI 推荐的 Runbook 名称 (AI recommended Runbook name)
    reasoning: str = ""                         # AI 推理过程 (AI reasoning process)
    additional_context: dict[str, Any] = Field(default_factory=dict)  # 额外上下文信息 (Additional context info)


class RunbookStep(BaseModel):
    """Runbook 执行步骤 (Runbook Execution Step)
    
    定义了 Runbook 中的单个执行步骤，包含命令内容、描述和执行配置。
    Defines a single execution step in a Runbook, including command content, 
    description and execution configuration.
    
    字段说明 (Field Descriptions):
    - description: 步骤的人类可读描述，用于日志和审计
    - command: 要执行的具体命令，支持变量替换
    - timeout_seconds: 命令执行超时时间，防止长时间阻塞
    
    命令变量替换 (Command Variable Substitution):
    支持以下占位符变量：
    - {host}: 告警主机名或 IP
    - {service}: 服务名称
    - 以及告警标签中的其他自定义变量
    
    超时设计 (Timeout Design):
    - 默认 30 秒适合大部分运维命令
    - 可根据具体命令特性调整
    - 超时后系统会强制终止命令进程
    
    使用示例 (Usage Examples):
    - 重启服务: "systemctl restart {service}"
    - 清理日志: "find /var/log -name '*.log' -mtime +7 -delete"
    - 检查状态: "systemctl status {service}"
    """
    description: str           # 步骤描述 (Step description)
    command: str              # 执行命令 (Command to execute)
    rollback_command: Optional[str] = None  # 回滚命令 (Rollback command)
    timeout_seconds: int = 30 # 超时时间，默认 30 秒 (Timeout in seconds, default 30)


class RunbookDefinition(BaseModel):
    """Runbook 完整定义 (Complete Runbook Definition)
    
    这是自动修复系统中最重要的数据结构，定义了一个完整的修复脚本。
    This is the most important data structure in the remediation system, defining 
    a complete remediation script.
    
    Runbook 组成要素 (Runbook Components):
    1. 基本信息：名称、描述
    2. 匹配规则：告警类型、关键词
    3. 安全设置：风险等级、冷却时间
    4. 执行流程：修复命令、验证命令
    
    匹配机制 (Matching Mechanism):
    - match_alert_types: 精确匹配告警类型
    - match_keywords: 模糊匹配告警内容中的关键词
    - 支持多种匹配条件的组合使用
    
    执行流程 (Execution Flow):
    1. 按顺序执行 commands 中的所有步骤
    2. 如果所有命令成功，执行 verify_commands 进行验证
    3. 验证通过后修复流程完成
    
    安全控制 (Safety Control):
    - risk_level: 控制执行策略（自动/确认/阻止）
    - cooldown_seconds: 防止频繁执行的冷却时间
    - 所有命令都要通过安全检查
    
    设计原则 (Design Principles):
    - 幂等性：多次执行应该产生相同结果
    - 原子性：要么全部成功，要么全部回滚
    - 可观测性：详细记录执行过程和结果
    """
    name: str                                           # Runbook 唯一名称 (Unique Runbook name)
    description: str                                    # Runbook 功能描述 (Runbook function description)
    match_alert_types: list[str]                       # 匹配的告警类型列表 (List of matching alert types)
    match_keywords: list[str] = Field(default_factory=list)  # 匹配的关键词列表 (List of matching keywords)
    safety_checks: list[str] = Field(default_factory=list)   # 执行前预检规则 (Execution preflight checks)
    risk_level: RiskLevel = RiskLevel.CONFIRM          # 风险等级，默认需要确认 (Risk level, default requires confirmation)
    commands: list[RunbookStep]                        # 修复命令步骤列表 (List of remediation command steps)
    verify_commands: list[RunbookStep] = Field(default_factory=list)  # 验证命令步骤列表 (List of verification command steps)
    cooldown_seconds: int = 300                        # 冷却时间，默认 5 分钟 (Cooldown time, default 5 minutes)


class CommandResult(BaseModel):
    """命令执行结果 (Command Execution Result)
    
    记录了单条命令执行的完整信息，包括输出、错误、性能指标等。
    Records complete information about single command execution, including 
    output, errors, performance metrics, etc.
    
    字段含义 (Field Meanings):
    - command: 实际执行的命令内容（已解析变量）
    - exit_code: 命令退出码，0 表示成功，非 0 表示失败
    - stdout: 标准输出内容，截断到合理长度
    - stderr: 标准错误输出内容，包含错误信息
    - executed: 是否真实执行，false 表示 dry-run 或被阻止
    - duration_ms: 命令执行耗时，毫秒为单位
    
    退出码规范 (Exit Code Conventions):
    - 0: 命令成功执行
    - 正数 (1-255): 命令执行失败，具体含义由命令决定
    - -1: 系统级错误（超时、权限不足、命令不存在等）
    
    性能分析 (Performance Analysis):
    通过 duration_ms 可以分析：
    - 命令执行的性能特征
    - 系统负载对执行时间的影响
    - 超时设置是否合理
    
    故障诊断 (Troubleshooting):
    - exit_code 非零时查看 stderr 获取错误信息
    - 长时间执行的命令可能需要优化
    - stdout 可以提供命令执行的详细信息
    """
    command: str           # 执行的命令内容 (Executed command content)
    exit_code: int = 0     # 命令退出码 (Command exit code)
    stdout: str = ""       # 标准输出 (Standard output)
    stderr: str = ""       # 标准错误输出 (Standard error output)
    executed: bool = True  # 是否真实执行 (Whether actually executed)
    duration_ms: int = 0   # 执行耗时（毫秒） (Execution duration in milliseconds)


class RemediationAlert(BaseModel):
    """修复告警数据模型 (Remediation Alert Data Model)
    
    这是自动修复系统的输入数据结构，从 NightMend 告警系统传入的标准化告警信息。
    This is the input data structure for the remediation system, standardized alert 
    information passed from the NightMend alert system.
    
    数据来源转换 (Data Source Conversion):
    从 SQLAlchemy ORM Alert 模型转换而来，保留修复系统需要的关键字段。
    Converted from SQLAlchemy ORM Alert model, preserving key fields needed by remediation system.
    
    字段用途 (Field Usage):
    - alert_id: 告警的唯一标识符，用于跟踪和审计
    - alert_type: 告警类型，用于 Runbook 匹配
    - severity: 严重程度，影响修复优先级
    - host/host_id: 主机信息，命令执行的目标
    - message: 告警详情，用于 AI 分析和关键词匹配
    - labels: 自定义标签，支持变量替换和扩展信息
    - timestamp: 告警时间，用于时间窗口分析
    
    严重程度分类 (Severity Classification):
    - critical: 严重故障，需要立即处理
    - warning: 警告信息，可以自动处理
    - info: 信息提示，通常不需要修复
    
    标签系统 (Label System):
    labels 字段支持任意键值对，常见用途：
    - service: 服务名称
    - port: 端口号
    - environment: 环境标识（prod/test/dev）
    - team: 负责团队
    """
    alert_id: int                                    # 告警 ID (Alert ID)
    alert_type: str                                  # 告警类型 (Alert type)
    severity: str = "warning"                        # 严重程度 (Severity level)
    host: str = "unknown"                           # 主机名或 IP (Hostname or IP)
    host_id: Optional[int] = None                   # 主机 ID（可选） (Host ID, optional)
    message: str = ""                               # 告警消息 (Alert message)
    labels: dict[str, str] = Field(default_factory=dict)  # 自定义标签 (Custom labels)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))  # 告警时间 (Alert timestamp)

    def summary(self) -> str:
        """生成告警摘要字符串 (Generate Alert Summary String)
        
        Returns:
            str: 格式化的告警摘要，用于日志记录和显示
            
        格式 (Format):
        [severity] alert_type on host: message
        
        示例 (Example):
        [warning] high_cpu on web01: CPU usage above 80%
        """
        return f"[{self.severity}] {self.alert_type} on {self.host}: {self.message}"


class RemediationResult(BaseModel):
    """修复结果数据模型 (Remediation Result Data Model)
    
    这是自动修复系统的输出数据结构，包含了一次完整修复流程的所有关键信息。
    This is the output data structure of the remediation system, containing all key 
    information from a complete remediation process.
    
    结果分类 (Result Categories):
    1. 成功执行：success=True，所有步骤正常完成
    2. 执行失败：success=False，命令执行或验证失败
    3. 被阻止执行：blocked_reason 不为空，安全检查拒绝
    4. 升级处理：escalated=True，需要人工干预
    
    数据完整性 (Data Integrity):
    - 包含完整的执行链路：诊断→匹配→执行→验证
    - 保留所有中间结果，便于故障分析和优化
    - 支持序列化存储，可以完整重现执行过程
    
    状态判断逻辑 (Status Determination Logic):
    - success 的判断基于命令执行结果和验证结果
    - escalated 表示需要人工处理的情况
    - blocked_reason 记录阻止执行的具体原因
    
    审计和监控 (Audit and Monitoring):
    通过这个结果可以进行：
    - 修复成功率统计
    - 失败原因分析
    - 性能指标计算
    - 安全事件追踪
    
    与数据库的关系 (Relationship with Database):
    这个模型的数据会被持久化到 RemediationLog 表中
    """
    alert_id: int                                    # 关联的告警 ID (Associated alert ID)
    success: bool                                    # 修复是否成功 (Whether remediation succeeded)
    runbook_name: Optional[str] = None              # 使用的 Runbook 名称 (Used Runbook name)
    diagnosis: Optional[Diagnosis] = None           # AI 诊断结果 (AI diagnosis result)
    risk_level: Optional[RiskLevel] = None          # 评估的风险等级 (Assessed risk level)
    command_results: list[CommandResult] = Field(default_factory=list)  # 命令执行结果列表 (Command execution results list)
    verification_passed: Optional[bool] = None     # 验证是否通过 (Whether verification passed)
    blocked_reason: Optional[str] = None           # 阻止执行的原因 (Reason for blocking execution)
    escalated: bool = False                        # 是否升级到人工处理 (Whether escalated to manual handling)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))  # 结果生成时间 (Result generation time)

    def summary(self) -> str:
        """生成修复结果摘要字符串 (Generate Remediation Result Summary String)
        
        Returns:
            str: 格式化的结果摘要，用于日志记录和通知
            
        摘要格式 (Summary Format):
        - 被阻止: "BLOCKED: reason"
        - 正常执行: "SUCCESS/FAILED via runbook=name, verified=true/false/null"
        
        示例 (Examples):
        - "SUCCESS via runbook=service_restart, verified=True"
        - "FAILED via runbook=disk_cleanup, verified=False"
        - "BLOCKED: Command not in allowed prefix list"
        """
        if self.blocked_reason:
            # 修复被阻止，显示阻止原因 (Remediation blocked, show blocking reason)
            return f"BLOCKED: {self.blocked_reason}"
            
        # 正常执行流程，显示状态和详情 (Normal execution flow, show status and details)
        status = "SUCCESS" if self.success else "FAILED"
        rb = self.runbook_name or "none"  # Runbook 名称，无则显示 "none"
        return f"{status} via runbook={rb}, verified={self.verification_passed}"
