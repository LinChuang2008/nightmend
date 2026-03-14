# 更新日志

> 格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## 目录

- [v2026.03.14](#v20260314)
- [v0.9.0 (2026-02-20)](#v090-2026-02-20)
- [v0.8.0 (2026-02-19)](#v080-2026-02-19)
- [v0.7.0 (2026-02-18)](#v070-2026-02-18)
- [v0.6.0 (2026-02-18)](#v060-2026-02-18)
- [v0.5.0 (2026-02-17)](#v050-2026-02-17)
- [v0.4.0 (2026-02-17)](#v040-2026-02-17)
- [v0.3.0 (2026-02-16)](#v030-2026-02-16)
- [v0.2.0 (2026-02-16)](#v020-2026-02-16)
- [v0.1.0 (2026-02-16)](#v010-2026-02-16)

---

## VigilOps 2026.03.14 (v2026.03.14)

> 自本版本起，版本号规则变更为日期制：vYYYY.MM.DD，小版本为 vYYYY.MM.DD-beta.N

### New Features
- PromQL query support: /api/v1/promql/query, /query_range, /metadata
- Helm Chart for Kubernetes deployment (charts/vigilops/)
- Slack and Telegram notification channels
- Alert service test coverage: 26 new test cases

### Security Fixes
- SQL injection fix in ClickHouse log backend (P0)
- Command injection prevention in remediation executor (P1)
- MCP server forced Bearer Token authentication (P1)
- OAuth state migrated from memory to Redis (P1)
- WebSocket authentication + reconnection limits
- Notification channel config sanitization in API responses
- Settings/Remediation endpoints restricted to operator+ role
- CORS headers whitelist tightened
- bcrypt rounds increased to 14

### Bug Fixes
- Service alert rules now respect duration_seconds threshold
- Notification retry with exponential backoff
- Log keyword alert deduplication (60s window)
- Silence window timezone fix (UTC)
- WebSocket send timeout for slow consumers
- Orphaned alert cleanup runs periodically
- Connection leak fixes in MySQL/Redis/Oracle collectors
- Silent error catch blocks replaced with console.warn

---

## [0.9.1] - 2026-03-05

### Security
- **P0** Fixed privilege escalation vulnerability in alert rule delete endpoint (non-admin users could delete any rule)
- **P0** Implemented JWT httpOnly Cookie skeleton (migration from localStorage in progress)
- **P0** Enhanced JWT secret key strength validation (minimum entropy enforcement)
- **P0** Replaced deprecated `asyncio.get_event_loop()` calls for async safety

### Fixed
- Auto-remediation list now correctly displays alert name and host columns
- i18n: Replaced hardcoded Chinese strings with `t()` calls across components
- Added guided alert rule setup prompt after adding a new host

### Improved
- Unified PageHeader component across 6+ pages for consistent UI
- Added PageBreadcrumb navigation to host/service/alert detail pages

---

## v0.9.0 (2026-02-20)

### 新增
- **Agent 一键安装脚本**：`scripts/install-agent.sh`，支持在线安装和离线模式
- **CI/CD 流水线**：GitHub Actions 自动构建、测试、推送 Docker 镜像至 GHCR
- **客户交付 SOP**：完整的部署交付流程文档
- **技术博客**：6 篇中英双语文章（AI 可观测性趋势、5 分钟快速入门、Agentic SRE 自愈架构）
- **Demo 账号**：内置 demo@vigilops.io 演示账号
- **Gitee 镜像**：Agent 安装脚本支持 Gitee 备用源（国内加速）
- **落地页文案**：README 重构为产品落地页风格

### 优化
- README.md 重构，突出 AI Agent 自动修复卖点
- Agent 安装脚本支持本地离线包安装模式

---

## v0.8.0 (2026-02-19)

### 新增
- **多服务器拓扑**：分层钻取视图（L1 全局 → L2 服务器 → L3 服务）
- 拓扑图支持拖拽布局并持久化保存
- AI 推荐服务依赖关系
- 邻接高亮：点击节点自动高亮关联服务
- 服务器分组管理

### 优化
- 大规模服务图的拓扑渲染性能
- 服务器组与拓扑视图深度集成

---

## v0.7.0 (2026-02-18)

### 新增
- **AI 记忆集成**：对接 Engram 系统，AI 分析可召回历史故障经验
- AI 根因分析利用历史事件上下文提升诊断准确率
- 已解决的告警自动存储为运维知识库
- GitHub 开源配套：CONTRIBUTING.md、Issue 模板、PR 模板

### 变更
- AI 引擎启用历史上下文增强异常检测

---

## v0.6.0 (2026-02-18)

### 新增
- **阿里云 ECS 部署**：全栈部署至阿里云（demo.lchuangnet.com）
- Docker Compose 生产环境配置
- 数据库迁移脚本 014

### 修复
- Docker 镜像构建优化，减小体积
- 生产环境变量处理修复

---

## v0.5.0 (2026-02-17)

### 新增
- **SLA 管理**：可用性追踪、错误预算、违规检测
- **审计日志**：完整操作审计追踪
- **通知系统**：5 种渠道（钉钉、飞书、企业微信、邮件、Webhook）
- 通知模板：支持变量替换
- 通知降噪：冷却期 + 静默期机制

---

## v0.4.0 (2026-02-17)

### 新增
- **自动修复系统**：AI 驱动的自愈能力
- 6 个内置 Runbook：磁盘清理、内存压力缓解、服务重启、日志轮转、僵尸进程清除、连接重置
- 安全检查 + 审批流程（危险操作需人工确认）
- SSH 远程命令执行引擎
- 速率限制 + 熔断器保护

---

## v0.3.0 (2026-02-16)

### 新增
- **仪表盘**：实时 WebSocket 推送、健康评分、趋势图表
- **数据库监控**：支持 PostgreSQL、MySQL、Oracle，慢查询 Top10、连接数、QPS
- **日志管理**：采集、全文搜索、实时流式查看
- **运维报告**：自动生成日报/周报

---

## v0.2.0 (2026-02-16)

### 新增
- **AI 分析模块**：集成 DeepSeek API
- AI 对话界面：交互式运维问答
- 一键根因分析：从告警直接触发 AI 诊断
- AI 洞察仪表盘：严重性评分 + 智能建议

---

## v0.1.0 (2026-02-16)

### 新增
- **核心监控**：主机和服务监控，指标采集
- **告警系统**：指标阈值、日志关键字、数据库阈值三种告警规则
- **用户管理**：注册、登录、JWT 认证、RBAC 角色控制
- **Agent**：数据采集代理，HTTP 上报
- FastAPI 后端 + React 前端 + PostgreSQL + Redis 基础架构
