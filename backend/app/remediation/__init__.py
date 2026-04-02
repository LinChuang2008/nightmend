"""
NightMend 自动修复系统 (NightMend Automatic Remediation System)

这是 NightMend 监控平台的智能自动修复模块，实现了基于 AI 的端到端故障自愈能力。
This is the intelligent automatic remediation module of NightMend monitoring platform, 
implementing AI-based end-to-end fault self-healing capabilities.

## 系统架构 (System Architecture)

```
告警事件 (Alert Event)
    ↓
AI 智能诊断 (AI Diagnosis) 
    ↓
Runbook 智能匹配 (Smart Runbook Matching)
    ↓
多层安全检查 (Multi-layer Safety Check)
    ↓
远程命令执行 (Remote Command Execution)
    ↓
修复效果验证 (Remediation Verification)
    ↓
结果持久化 & 通知 (Result Persistence & Notification)
```

## 核心组件 (Core Components)

- **RemediationAgent**: 修复流程的核心编排器
- **AI Client**: DeepSeek API 集成的智能诊断客户端
- **Command Executor**: 安全的远程命令执行引擎
- **Safety Module**: 多重安全防护机制
- **Runbook Registry**: Runbook 管理和匹配系统
- **Alert Listener**: Redis PubSub 事件监听器

## 内置 Runbook (Built-in Runbooks)

1. **disk_cleanup**: 磁盘空间清理
2. **service_restart**: 服务重启修复
3. **zombie_killer**: 僵尸进程清理
4. **memory_pressure**: 内存压力释放
5. **log_rotation**: 日志轮转压缩
6. **connection_reset**: 网络连接重置

## 安全机制 (Safety Mechanisms)

- **命令白名单**: 只允许预定义的安全命令
- **黑名单检查**: 阻止已知的危险操作模式
- **风险评估**: 基于 AI 置信度和历史数据的动态风险评估
- **频率限制**: 防止短时间内频繁执行相同操作
- **熔断保护**: 连续失败时自动停止对故障主机的操作

## 使用示例 (Usage Example)

```python
from app.remediation.agent import RemediationAgent
from app.remediation.ai_client import RemediationLLMClient

# 创建 AI 客户端
ai_client = RemediationLLMClient()

# 创建修复 Agent
agent = RemediationAgent(ai_client=ai_client, dry_run=False)

# 处理告警
result = await agent.handle_alert(alert, db_session)
```

## 配置项 (Configuration)

- `AGENT_ENABLED`: 是否启用自动修复功能
- `AGENT_DRY_RUN`: 是否为测试模式（不实际执行命令）
- `AGENT_NOTIFY_ON_SUCCESS`: 成功时是否发送通知
- `AGENT_NOTIFY_ON_FAILURE`: 失败时是否发送通知

作者：NightMend Team
版本：v1.0
许可证：内部项目
"""
