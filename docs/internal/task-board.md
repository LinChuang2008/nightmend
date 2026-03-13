# Task Board — 共享工作区

## Agent 1: DevOps (告警 + 自动修复测试)
- Status: ✅ 完成
- 测试时间: 2026-02-27 14:35~14:45 CST

### 测试环境
- Ubuntu VM (10.211.55.6): Agent 运行正常，Nginx/MySQL/RabbitMQ 在线
- Backend (10.211.55.2:8000): Docker Compose 正常运行
- Host ubuntu-linux (id=2): 在线，Agent 持续上报 heartbeat/metrics/services

### 测试结果

| 步骤 | 结果 | 详情 |
|------|------|------|
| Agent 上报数据 | ✅ | 心跳、指标、服务状态均正常上报 (每 15-30s) |
| 服务状态检测 | ✅ | 停 Nginx 后，API 返回 nginx status=down |
| 告警规则存在 | ✅ | 内置规则 id=5 "服务不可用" (service_down, target_type=service) |
| **告警触发** | **❌ 失败** | 停 Nginx 等待 75s+，无新告警产生 |
| 自动修复触发 | ❌ 未触发 | 因告警未触发，runbook 未被调用 |
| Nginx 手动恢复 | ✅ | 手动 systemctl start nginx 恢复正常 |

### 🐛 P0 Bug: 服务类告警规则不被评估

**根因**: `backend/app/tasks/alert_engine.py` 的 `alert_engine_loop()` 只调用 `evaluate_host_rules()`，该函数只查询 `target_type == "host"` 的规则。内置的 `service_down` 规则 (`target_type == "service"`) **从未被评估**。

**影响**:
- 所有 service 类型告警规则永远不会触发
- `service_restart` runbook（已正确匹配 service_down）永远不会被调用
- 自动修复功能对服务级别故障完全失效

**修复建议**: 在 `alert_engine.py` 中新增 `evaluate_service_rules()` 函数，遍历 service 类型规则，检查各服务状态，触发/恢复告警。在 `alert_engine_loop()` 中调用。

### 其他观察
- 历史 5 条告警均为 host_offline 类型且已 resolved，说明主机级告警引擎工作正常
- Remediation API 存在 (`/api/v1/remediations`) 但从未有记录
- Runbook `service_restart` 定义完整（检查→重启→验证），风险级别 CONFIRM（需人工审批）

## Agent 2: QA (拓扑图 + 整体 QA)
- Status: ✅ 完成
- 测试时间: 2026-02-27 14:35~14:50 CST

### A. 拓扑图页面 (/topology) — ✅ 正常

| 检查项 | 结果 |
|--------|------|
| 页面加载 | ✅ 正常，15个服务节点、4条依赖连线 |
| 管道布局 | ✅ 正常，按接入层/应用层/中间件/数据层分组 |
| 力导向布局 | ✅ 正常，切换流畅 |
| 节点状态颜色 | ✅ 正常，notification-service 红边标记 down |
| 图例 | ✅ 显示后端/前端/缓存/数据库/业务/消息队列分类 |
| 编辑依赖/保存布局/重置按钮 | ✅ 可见可点击 |
| 前端控制台 JS 错误 | ✅ 无错误 |
| API /api/v1/topology | ✅ 返回 15 nodes + edges 数据完整 |

**结论：拓扑图功能正常，Patrick 反馈的问题可能已修复或需要更具体的复现场景。**

### B. 整体功能 Smoke Test

| 页面 | API 状态 | UI 状态 | 发现 |
|------|----------|---------|------|
| Dashboard (/) | ✅ | ✅ | 健康评分实时变化(59~68)，图表正常 |
| 服务器 (/hosts) | ✅ 1台在线 | ✅ | CPU/内存/磁盘指标正常显示 |
| 服务监控 (/services) | ✅ 19个服务 | ✅ | 18 up / 1 down (notification-service) |
| 告警中心 (/alerts) | ✅ 5条历史告警 | ✅ | 均为 resolved 状态 |
| AI 分析 (/ai-analysis) | ✅ insights + system-summary | ✅ | 对话、洞察列表、分页均正常 |
| 日志管理 (/logs) | ✅ 返回日志数据 | — | info/warning/error 级别日志正常 |
| 数据库监控 (/databases) | ✅ 1个 MySQL | — | healthy，指标完整 |

### C. Bug 列表

| # | 严重度 | 描述 | 详情 |
|---|--------|------|------|
| 1 | **P2** | AI 分析页面服务数量不一致 | API system-summary 显示 18/19 up，但 AI 页面 UI 显示 16/19 健康。可能是统计口径不同或缓存延迟 |
| 2 | **P2** | Dashboard API 路由 404 | `/api/v1/dashboard/stats` 和 `/api/v1/dashboard/overview` 均返回 404。前端 dashboard 正常加载（可能用其他 endpoint 组合），但缺少统一的 dashboard API |
| 3 | **P2** | AI analysis API 路由不一致 | `/api/v1/ai/analysis/history` 返回 404，实际用 `/api/v1/ai/insights`。API 文档可能需更新 |
| 4 | **P1** | 健康评分波动较大 | 短时间内从 68 降到 59，需确认评分算法是否合理稳定 |

### D. 总结
- **拓扑图：完全正常**，两种布局模式都能正确渲染
- **核心功能：基本健康**，所有主要页面可访问，数据加载正常
- **无 P0 级 bug**
- **3 个 P2 + 1 个 P1**，主要是 API 一致性和数据展示问题

---

## QA Patrol — 2026-02-28 04:00 CST

### 🐛 P0 Blocker: Demo 后端服务宕机
- **环境**: http://139.196.210.68:3001
- **现象**: 全部 API 返回 502 Bad Gateway (nginx/1.29.5)
- **影响**: 整个 Demo 站点不可用
- **建议**: 检查 ECS Docker 容器状态，重启后端服务
- **发现者**: QA Patrol (Bach)
- **状态**: 🔴 Open
