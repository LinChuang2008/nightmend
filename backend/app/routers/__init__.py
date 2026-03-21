"""
VigilOps 路由模块包 (VigilOps Router Module Package)

本包包含 VigilOps 后端 API 的所有路由模块，按功能域进行组织。
每个路由模块负责特定功能领域的 REST API 和 WebSocket 接口。

路由模块组织结构 (Router Module Organization):

=== 核心功能路由 (Core Functionality Routes) ===
- auth.py: 用户认证和授权（登录、注册、JWT令牌管理）
- users.py: 用户管理（CRUD、角色管理、密码重置）
- settings.py: 系统设置管理（配置参数、默认值管理）
- audit_logs.py: 审计日志查询（操作追踪、合规审计）

=== 监控数据路由 (Monitoring Data Routes) ===
- hosts.py: 主机监控（主机管理、指标数据、状态监控）
- servers.py: 服务器管理（服务器注册、详情查看、生命周期管理）
- server_groups.py: 服务分组管理（服务组CRUD、服务器关联管理）
- services.py: 服务监控（服务健康检查、状态管理、依赖关系）
- databases.py: 数据库监控（指标查询、慢查询分析、历史数据）

=== 告警和日志路由 (Alert and Log Routes) ===
- alerts.py: 告警管理（告警查询、状态更新、告警历史）
- alert_rules.py: 告警规则管理（规则CRUD、条件配置、触发管理）
- logs.py: 日志管理（日志搜索、统计分析、实时流推送）

=== 分析和报告路由 (Analysis and Report Routes) ===
- ops.py: AI运维助手（多轮诊断、命令确认、会话管理）
- reports.py: 运维报告（报告生成、查询、删除管理）
- sla.py: SLA管理（规则管理、状态监控、违规检测、可用性报告）

=== 通知和修复路由 (Notification and Remediation Routes) ===
- notifications.py: 通知管理（通知渠道配置、消息发送）
- notification_templates.py: 通知模板（模板CRUD、变量替换）
- remediation.py: 自动修复（修复任务管理、执行历史、安全审批）

=== 拓扑和可视化路由 (Topology and Visualization Routes) ===
- topology.py: 服务拓扑（拓扑图数据、布局管理、依赖关系）
- dashboard.py: 仪表盘数据（概览统计、图表数据）
- dashboard_ws.py: 仪表盘WebSocket（实时数据推送、健康评分）

=== 集成和安全路由 (Integration and Security Routes) ===
- agent.py: Agent数据上报（监控数据接收、Agent管理）
- agent_tokens.py: Agent令牌管理（令牌生成、吊销、权限控制）

路由注册:
所有路由模块在 main.py 中通过 app.include_router() 统一注册，
并按照 RESTful API 标准设置统一的前缀和标签。

API版本控制:
当前所有API使用 v1 版本前缀 (/api/v1/)，
为未来API版本升级预留扩展空间。

Author: VigilOps Team
"""
