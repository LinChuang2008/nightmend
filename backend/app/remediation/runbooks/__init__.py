"""
NightMend 自动修复系统 - Runbook 定义包
NightMend Remediation System - Runbook Definition Package

这个包包含了 NightMend 系统内置的所有标准修复脚本（Runbook）定义。
This package contains all built-in standard remediation script (Runbook) definitions for NightMend system.

## 内置 Runbook 列表 (Built-in Runbook List)

### 1. disk_cleanup.py - 磁盘空间清理
- **用途**: 清理临时文件、旧日志、包缓存
- **风险等级**: AUTO（自动执行）
- **适用场景**: 磁盘空间不足、使用率过高
- **清理内容**: /tmp、日志文件、apt缓存

### 2. memory_pressure.py - 内存压力缓解
- **用途**: 清理系统缓存，缓解内存压力
- **风险等级**: CONFIRM（需要确认）
- **适用场景**: 内存使用率高、OOM 警告
- **操作内容**: 清理页面缓存、识别内存大户

### 3. service_restart.py - 服务重启修复
- **用途**: 重启故障或无响应的系统服务
- **风险等级**: CONFIRM（需要确认）
- **适用场景**: 服务停止、无响应、崩溃
- **影响**: 会导致服务短暂中断

### 4. log_rotation.py - 日志轮转
- **用途**: 强制执行日志轮转，处理超大日志文件
- **风险等级**: AUTO（自动执行）
- **适用场景**: 日志文件过大、日志快速增长
- **操作内容**: 压缩归档日志、释放磁盘空间

### 5. zombie_killer.py - 僵尸进程清理
- **用途**: 识别和诊断僵尸进程问题
- **风险等级**: AUTO（自动执行）
- **适用场景**: 僵尸进程过多、进程表接近满载
- **操作性质**: 主要是诊断，实际清理需谨慎

### 6. connection_reset.py - 网络连接诊断
- **用途**: 诊断网络连接状态，识别连接问题
- **风险等级**: CONFIRM（需要确认）
- **适用场景**: 连接数过多、连接耗尽、端口耗尽
- **操作性质**: 主要是诊断分析

## 使用方式 (Usage)

每个 Runbook 都导出一个 `RUNBOOK` 常量，包含完整的 `RunbookDefinition`：

```python
from app.remediation.runbooks.disk_cleanup import RUNBOOK as DISK_CLEANUP
from app.remediation.runbook_registry import RunbookRegistry

# 注册到系统中
registry = RunbookRegistry()
registry.register(DISK_CLEANUP)
```

## 扩展开发 (Extension Development)

要添加新的 Runbook：

1. 创建新的 Python 文件（如 `custom_fix.py`）
2. 定义 `RunbookDefinition` 对象
3. 导出为 `RUNBOOK` 常量
4. 在 `RunbookRegistry` 中注册

## 安全考虑 (Security Considerations)

- 所有命令都会经过安全检查（白名单/黑名单）
- 风险等级决定执行策略（自动/确认/阻止）
- 支持 dry-run 模式用于测试验证
- 完整的审计日志和执行历史记录

作者：NightMend Team
版本：v1.0
最后更新：2026-02-21
"""
