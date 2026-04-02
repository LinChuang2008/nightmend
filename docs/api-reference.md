# NightMend API Reference

> Auto-generated from backend router source code.
> Base URL: `http://<host>:8001`
> 自动生成自后端路由源码。基础地址：`http://<host>:8001`

---

## Table of Contents / 目录

1. [Authentication / 认证](#1-authentication--认证)
2. [User Management / 用户管理](#2-user-management--用户管理)
3. [Host Management / 主机管理](#3-host-management--主机管理)
4. [Server Management / 服务器管理](#4-server-management--服务器管理)
5. [Server Groups / 服务组管理](#5-server-groups--服务组管理)
6. [Service Monitoring / 服务监控](#6-service-monitoring--服务监控)
7. [Service Topology / 服务拓扑](#7-service-topology--服务拓扑)
8. [Dashboard / 仪表盘](#8-dashboard--仪表盘)
9. [Alerts / 告警管理](#9-alerts--告警管理)
10. [Alert Rules / 告警规则](#10-alert-rules--告警规则)
11. [Logs / 日志管理](#11-logs--日志管理)
12. [Database Monitoring / 数据库监控](#12-database-monitoring--数据库监控)
13. [AI Analysis / AI 智能分析](#13-ai-analysis--ai-智能分析)
14. [Notifications / 通知管理](#14-notifications--通知管理)
15. [Notification Templates / 通知模板](#15-notification-templates--通知模板)
16. [Auto Remediation / 自动修复](#16-auto-remediation--自动修复)
17. [Reports / 运维报告](#17-reports--运维报告)
18. [SLA Management / SLA 管理](#18-sla-management--sla-管理)
19. [System Settings / 系统设置](#19-system-settings--系统设置)
20. [Audit Logs / 审计日志](#20-audit-logs--审计日志)
21. [Agent Data Reporting / Agent 数据上报](#21-agent-data-reporting--agent-数据上报)
22. [Agent Tokens / Agent 令牌管理](#22-agent-tokens--agent-令牌管理)
23. [Webhooks / 外部告警接入](#23-webhooks--外部告警接入)
24. [Demo / 演示接口](#24-demo--演示接口)
25. [Custom Runbooks / 自定义 Runbook](#25-custom-runbooks--自定义-runbook)

---

## Authentication / 认证说明

Most endpoints require a **JWT Bearer token** in the `Authorization` header:
大多数接口需要在 `Authorization` 请求头中携带 **JWT Bearer Token**：

```
Authorization: Bearer <access_token>
```

- **Public endpoints / 公开接口**: `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`
- **Admin-only endpoints / 仅管理员**: User CRUD, audit logs, agent tokens, settings update
- **Agent endpoints / Agent 接口**: Use `X-Agent-Token` header instead of JWT

---

## 1. Authentication / 认证

### POST `/api/v1/auth/register`
**Register / 用户注册**

Register a new user. The first registered user automatically becomes admin.
注册新用户。第一个注册的用户自动成为管理员。

- **Auth**: None / 无需认证

**Request Body:**
```json
{
  "email": "user@example.com",
  "name": "张三",
  "password": "securepassword"
}
```

**Response** `201`:
```json
{
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG..."
}
```

---

### POST `/api/v1/auth/login`
**Login / 用户登录**

Authenticate with email and password.
使用邮箱和密码登录。

- **Auth**: None / 无需认证

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response** `200`:
```json
{
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG..."
}
```

**Errors**: `401` Invalid credentials, `403` Account disabled

---

### POST `/api/v1/auth/refresh`
**Refresh Token / 刷新令牌**

Get a new access token using a refresh token.
使用刷新令牌获取新的访问令牌。

- **Auth**: None / 无需认证

**Request Body:**
```json
{
  "refresh_token": "eyJhbG..."
}
```

**Response** `200`:
```json
{
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG..."
}
```

---

### GET `/api/v1/auth/me`
**Get Current User / 获取当前用户信息**

- **Auth**: Bearer Token

**Response** `200`:
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "张三",
  "role": "admin",
  "is_active": true
}
```

---

## 2. User Management / 用户管理

> All endpoints require **admin** role.
> 所有接口需要 **管理员** 角色。

### GET `/api/v1/users`
**List Users / 用户列表**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页数量 (max 100) |

**Response** `200`:
```json
{
  "items": [{"id": 1, "email": "...", "name": "...", "role": "admin", "is_active": true}],
  "total": 10,
  "page": 1,
  "page_size": 20
}
```

---

### POST `/api/v1/users`
**Create User / 创建用户**

**Request Body:**
```json
{
  "email": "new@example.com",
  "name": "李四",
  "password": "password123",
  "role": "operator"
}
```
Roles: `admin`, `operator`, `viewer`

**Response** `201`: User object

---

### GET `/api/v1/users/{user_id}`
**Get User / 获取用户详情**

**Response** `200`: User object

---

### PUT `/api/v1/users/{user_id}`
**Update User / 编辑用户**

**Request Body** (partial update):
```json
{
  "name": "新名字",
  "role": "operator",
  "is_active": false
}
```

**Response** `200`: Updated user object

---

### DELETE `/api/v1/users/{user_id}`
**Delete User / 删除用户**

Admin cannot delete themselves. 管理员不能删除自己。

**Response** `204`: No content

---

### PUT `/api/v1/users/{user_id}/password`
**Reset Password / 重置密码**

**Request Body:**
```json
{
  "new_password": "newpassword123"
}
```

**Response** `200`: `{"status": "ok"}`

---

## 3. Host Management / 主机管理

> Auth: Bearer Token (any role)
> 认证：Bearer Token（任意角色）

### GET `/api/v1/hosts`
**List Hosts / 主机列表**

| Param | Type | Description |
|-------|------|-------------|
| page | int | 页码 (default 1) |
| page_size | int | 每页数量 (default 20, max 100) |
| status | string | 按状态筛选 (online/offline) |
| group_name | string | 按分组筛选 |
| search | string | 按主机名搜索 |

**Response** `200`:
```json
{
  "items": [{
    "id": 1, "hostname": "web-01", "ip_address": "10.0.0.1",
    "status": "online", "os": "CentOS", "cpu_cores": 8,
    "latest_metrics": {"cpu_percent": 45.2, "memory_percent": 62.1}
  }],
  "total": 5, "page": 1, "page_size": 20
}
```

---

### GET `/api/v1/hosts/{host_id}`
**Get Host Detail / 主机详情**

Returns host info with latest metrics from Redis cache.
返回主机信息及 Redis 缓存的最新指标。

**Response** `200`: Host object with `latest_metrics`

---

### GET `/api/v1/hosts/{host_id}/metrics`
**Get Host Metrics / 主机历史指标**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| hours | int | 1 | 时间范围 (1-720 hours) |
| interval | string | "raw" | 聚合模式: `raw`, `5min`, `1h`, `1d` |

**Response** `200`: Array of metric data points

---

## 4. Server Management / 服务器管理

> Auth: Bearer Token
> 认证：Bearer Token

### GET `/api/v1/servers`
**List Servers / 服务器列表 (L1 视图)**

| Param | Type | Description |
|-------|------|-------------|
| page | int | 页码 |
| page_size | int | 每页数量 |
| status | string | 按状态筛选 |
| search | string | 按 hostname/label/IP 搜索 |

**Response** `200`:
```json
{
  "items": [{
    "id": 1, "hostname": "prod-01", "ip_address": "10.0.0.1",
    "label": "生产服务器", "status": "online",
    "service_count": 12, "cpu_avg": 35.5, "mem_avg": 1024.0
  }],
  "total": 3, "page": 1, "page_size": 20
}
```

---

### GET `/api/v1/servers/{server_id}`
**Get Server Detail / 服务器详情 (L2 钻取)**

Returns server info + running services + nginx upstreams.
返回服务器信息 + 运行的服务列表 + nginx upstream 列表。

**Response** `200`:
```json
{
  "server": {"id": 1, "hostname": "...", ...},
  "services": [{"id": 1, "port": 8080, "status": "running", "group_name": "web", ...}],
  "nginx_upstreams": [{"upstream_name": "backend", "backend_address": "10.0.0.2:8001", ...}]
}
```

---

### POST `/api/v1/servers`
**Create Server / 注册服务器**

**Request Body:**
```json
{
  "hostname": "prod-02",
  "ip_address": "10.0.0.2",
  "label": "生产服务器2",
  "os": "CentOS Stream 9"
}
```

**Response** `201`: Server object

---

### PUT `/api/v1/servers/{server_id}`
**Update Server / 更新服务器**

**Request Body**: Same as create

**Response** `200`: Updated server object

---

### DELETE `/api/v1/servers/{server_id}`
**Delete Server / 删除服务器**

Cascades to delete associated server_services and nginx_upstreams.
级联删除关联的服务和 nginx upstream。

**Response** `200`: `{"detail": "服务器 'xxx' 已删除"}`

---

## 5. Server Groups / 服务组管理

> Auth: Bearer Token

### GET `/api/v1/server-groups`
**List Service Groups / 服务组列表**

| Param | Type | Description |
|-------|------|-------------|
| page | int | 页码 (default 1) |
| page_size | int | 每页数量 (default 50, max 200) |
| category | string | 按分类筛选 |

**Response** `200`:
```json
{
  "items": [{"id": 1, "name": "PostgreSQL", "category": "database", "server_count": 2}],
  "total": 8, "page": 1, "page_size": 50
}
```

---

### GET `/api/v1/server-groups/{group_id}`
**Get Service Group Detail / 服务组详情**

Returns group info with associated servers list.
返回服务组信息及关联的服务器列表。

---

### POST `/api/v1/server-groups`
**Create Service Group / 创建服务组**

```json
{ "name": "Redis", "category": "cache" }
```

**Response** `201`: ServiceGroup object

---

### PUT `/api/v1/server-groups/{group_id}`
**Update Service Group / 更新服务组**

---

### DELETE `/api/v1/server-groups/{group_id}`
**Delete Service Group / 删除服务组**

Cascades to delete associated server_services.

---

### POST `/api/v1/server-groups/{group_id}/servers`
**Add Server to Group / 添加服务器到服务组**

```json
{
  "server_id": 1,
  "port": 5432,
  "pid": 12345,
  "status": "running",
  "cpu_percent": 15.3,
  "mem_mb": 256.0
}
```

**Response** `201`: ServerService object

---

### DELETE `/api/v1/server-groups/{group_id}/servers/{server_id}`
**Remove Server from Group / 从服务组移除服务器**

**Response** `200`: `{"detail": "已移除"}`

---

## 6. Service Monitoring / 服务监控

> Auth: Bearer Token

### GET `/api/v1/services`
**List Services / 服务列表**

| Param | Type | Description |
|-------|------|-------------|
| page | int | 页码 |
| page_size | int | 每页数量 |
| status | string | 按状态筛选 (up/down) |
| category | string | 按分类筛选 (middleware/business/infrastructure) |
| host_id | int | 按主机筛选 |
| group_by_host | bool | 按主机分组返回 |

**Response** `200`:
```json
{
  "items": [{
    "id": 1, "name": "backend-api", "type": "http",
    "status": "up", "category": "business",
    "uptime_percent": 99.95,
    "host_info": {"id": 1, "hostname": "web-01", "ip": "10.0.0.1"}
  }],
  "total": 20, "page": 1, "page_size": 20,
  "stats": {"total": 20, "healthy": 18, "unhealthy": 2, "middleware": 5, "business": 10, "infrastructure": 5},
  "host_groups": []
}
```

---

### GET `/api/v1/services/{service_id}`
**Get Service Detail / 服务详情**

**Response** `200`: Service object with `uptime_percent`

---

### GET `/api/v1/services/{service_id}/checks`
**Get Service Health Checks / 服务健康检查历史**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| hours | int | 24 | 时间范围 (1-720) |

**Response** `200`: Array of ServiceCheck objects

---

## 7. Service Topology / 服务拓扑

> Auth: Bearer Token

### GET `/api/v1/topology`
**Get Topology Graph / 获取拓扑图数据**

Returns nodes, edges, saved layout positions, and host list.
返回节点、边、保存的布局位置和主机列表。

**Response** `200`:
```json
{
  "nodes": [{"id": 1, "name": "backend-api", "type": "http", "status": "up", "group": "api"}],
  "edges": [{"source": 1, "target": 2, "type": "depends_on", "description": "数据依赖"}],
  "hosts": [{"id": 1, "name": "web-01"}],
  "saved_positions": {"1": {"x": 100, "y": 200}},
  "has_custom_deps": false
}
```

---

### POST `/api/v1/topology/layout`
**Save Layout / 保存布局**

```json
{
  "name": "default",
  "positions": {"1": {"x": 100, "y": 200}, "2": {"x": 300, "y": 400}}
}
```

---

### DELETE `/api/v1/topology/layout`
**Reset Layout / 重置布局**

---

### POST `/api/v1/topology/dependencies`
**Create Dependency / 创建依赖关系**

```json
{
  "source_service_id": 1,
  "target_service_id": 2,
  "dependency_type": "calls",
  "description": "API 调用"
}
```

---

### DELETE `/api/v1/topology/dependencies/{dep_id}`
**Delete Dependency / 删除依赖关系**

---

### DELETE `/api/v1/topology/dependencies`
**Clear All Dependencies / 清空所有自定义依赖**

Reverts to auto-inferred edges. 回退到自动推断的依赖。

---

### POST `/api/v1/topology/ai-suggest`
**AI Suggest Dependencies / AI 推荐依赖关系**

Uses DeepSeek to analyze services and suggest dependency relationships.
使用 DeepSeek 分析服务列表，智能推荐依赖关系。

**Response** `200`:
```json
{
  "suggestions": [{"source": 1, "target": 2, "type": "depends_on", "description": "数据库依赖"}],
  "total": 3,
  "message": "AI 分析了 15 个服务，推荐 3 条新依赖关系"
}
```

---

### POST `/api/v1/topology/ai-suggest/apply`
**Apply AI Suggestions / 批量应用 AI 推荐**

**Request Body**: Array of DependencyCreate objects

**Response** `200`: `{"detail": "已应用 3 条依赖关系", "created": 3}`

---

### GET `/api/v1/topology/multi-server`
**Multi-Server Topology / 多服务器拓扑概览**

Returns all server nodes + nginx upstream-derived edges + summary stats.
返回所有服务器节点 + nginx upstream 推导的边 + 统计摘要。

**Response** `200`:
```json
{
  "servers": [{"id": 1, "hostname": "...", "service_count": 12, "cpu_avg": 35.5}],
  "edges": [{"from_server": "web-01", "to_server": "db-01", "via": "nginx_upstream"}],
  "summary": {"server_count": 3, "online_count": 2, "offline_count": 1, "service_group_count": 8, "edge_count": 5}
}
```

---

### GET `/api/v1/topology/servers`
**List Servers (Topology) / 服务器列表（拓扑视图）**

Legacy endpoint under topology prefix. Returns servers with summary metrics.

---

### GET `/api/v1/topology/servers/{server_id}`
**Server Detail (Topology) / 服务器详情（拓扑视图）**

Returns server + services + upstreams + summary metrics.

---

### POST `/api/v1/topology/servers`
**Create Server (Topology) / 注册服务器（拓扑）**

---

### DELETE `/api/v1/topology/servers/{server_id}`
**Delete Server (Topology) / 删除服务器（拓扑）**

---

### GET `/api/v1/topology/service-groups`
**List Service Groups (Topology) / 服务组列表（拓扑视图）**

Returns groups with per-server service distribution details.

---

## 8. Dashboard / 仪表盘

> Auth: Bearer Token

### GET `/api/v1/dashboard/trends`
**Get Trends / 获取趋势数据**

Returns 24-hour hourly aggregated metrics.
返回最近 24 小时每小时的聚合指标。

**Response** `200`:
```json
{
  "trends": [{
    "hour": "2026-02-20T14:00:00+00:00",
    "avg_cpu": 45.2,
    "avg_mem": 62.1,
    "alert_count": 3,
    "error_log_count": 12
  }]
}
```

---

### WebSocket `/api/v1/ws/dashboard`
**Dashboard Real-time Push / 仪表盘实时推送**

Pushes summary data every 30 seconds.
每 30 秒推送一次仪表盘汇总数据。

- **Auth**: None (WebSocket)

**Push Message:**
```json
{
  "timestamp": "2026-02-20T14:30:00+00:00",
  "hosts": {"total": 5, "online": 4, "offline": 1},
  "services": {"total": 20, "up": 18, "down": 2},
  "alerts": {"total": 3, "firing": 1},
  "recent_1h": {"alert_count": 3, "error_log_count": 12},
  "avg_usage": {"cpu_percent": 45.2, "memory_percent": 62.1, "disk_percent": 55.0},
  "health_score": 78
}
```

---

## 9. Alerts / 告警管理

> Auth: Bearer Token

### GET `/api/v1/alerts`
**List Alerts / 告警列表**

| Param | Type | Description |
|-------|------|-------------|
| status | string | firing / acknowledged / resolved |
| severity | string | critical / warning / info |
| host_id | int | 按主机筛选 |
| page | int | 页码 |
| page_size | int | 每页数量 |

**Response** `200`: Paginated alert list

---

### GET `/api/v1/alerts/{alert_id}`
**Get Alert Detail / 告警详情**

---

### POST `/api/v1/alerts/{alert_id}/ack`
**Acknowledge Alert / 确认告警**

Marks alert as acknowledged with timestamp and operator.

**Response** `200`: Updated alert object

**Errors**: `400` Alert already resolved

---

## 10. Alert Rules / 告警规则

> Auth: Bearer Token

### GET `/api/v1/alert-rules`
**List Alert Rules / 告警规则列表**

| Param | Type | Description |
|-------|------|-------------|
| is_enabled | bool | 按启用状态筛选 |

**Response** `200`: Array of AlertRule objects

---

### POST `/api/v1/alert-rules`
**Create Alert Rule / 创建告警规则**

Supports 3 rule types: `metric` (指标), `log_keyword` (日志关键字), `db_metric` (数据库指标).

**Request Body:**
```json
{
  "name": "CPU 高于 90%",
  "rule_type": "metric",
  "metric": "cpu_percent",
  "operator": ">",
  "threshold": 90,
  "severity": "critical",
  "is_enabled": true
}
```

**Response** `201`: AlertRule object

---

### GET `/api/v1/alert-rules/{rule_id}`
**Get Alert Rule / 获取告警规则**

---

### PUT `/api/v1/alert-rules/{rule_id}`
**Update Alert Rule / 更新告警规则**

Partial update, only updates provided fields.

---

### DELETE `/api/v1/alert-rules/{rule_id}`
**Delete Alert Rule / 删除告警规则**

Built-in rules cannot be deleted. 内置规则禁止删除。

**Response** `204`: No content

---

## 11. Logs / 日志管理

> Auth: Bearer Token

### GET `/api/v1/logs`
**Search Logs / 日志搜索**

| Param | Type | Description |
|-------|------|-------------|
| q | string | 全文搜索关键词 |
| host_id | int | 按主机筛选 |
| service | string | 按服务筛选 |
| level | string | 按级别筛选 (逗号分隔, e.g. "ERROR,WARN") |
| start_time | datetime | 开始时间 |
| end_time | datetime | 结束时间 |
| page | int | 页码 |
| page_size | int | 每页数量 (max 200) |

**Response** `200`:
```json
{
  "items": [{
    "id": 1, "host_id": 1, "hostname": "web-01",
    "service": "backend", "level": "ERROR",
    "message": "Connection refused", "timestamp": "2026-02-20T14:30:00Z"
  }],
  "total": 150, "page": 1, "page_size": 50
}
```

---

### GET `/api/v1/logs/stats`
**Log Statistics / 日志统计**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| host_id | int | - | 按主机筛选 |
| service | string | - | 按服务筛选 |
| period | string | "1h" | 时间分桶: `1h` or `1d` |
| start_time | datetime | - | 开始时间 |
| end_time | datetime | - | 结束时间 |

**Response** `200`:
```json
{
  "by_level": [{"level": "ERROR", "count": 45}, {"level": "INFO", "count": 1200}],
  "by_time": [{"time_bucket": "2026-02-20T14:00:00Z", "count": 120}]
}
```

---

### WebSocket `/ws/logs`
**Real-time Log Stream / 实时日志流**

| Param | Type | Description |
|-------|------|-------------|
| host_id | int | 按主机过滤 |
| service | string | 按服务过滤 |
| level | string | 按级别过滤 |

Streams log entries as JSON objects in real-time.
实时推送日志条目（JSON 格式）。

---

## 12. Database Monitoring / 数据库监控

> Auth: Bearer Token
> Supports: PostgreSQL, MySQL, Oracle

### GET `/api/v1/databases`
**List Databases / 数据库列表**

| Param | Type | Description |
|-------|------|-------------|
| host_id | int | 按主机筛选 |

**Response** `200`:
```json
{
  "databases": [{
    "id": 1, "name": "nightmend", "db_type": "postgres", "status": "healthy",
    "latest_metrics": {
      "connections_total": 50, "connections_active": 12,
      "database_size_mb": 1024, "slow_queries": 3,
      "qps": 150, "tablespace_used_pct": 45.2
    }
  }],
  "total": 3
}
```

---

### GET `/api/v1/databases/{database_id}`
**Get Database Detail / 数据库详情**

---

### GET `/api/v1/databases/{database_id}/slow-queries`
**Get Slow Queries / 慢查询列表**

Returns latest slow query details (primarily for Oracle).

---

### GET `/api/v1/databases/{database_id}/metrics`
**Get Database Metrics / 数据库历史指标**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| period | string | "1h" | 时间周期: `1h`, `24h`, `7d`, etc. |

---

## 13. AI Analysis / AI 智能分析

> Auth: Bearer Token
> Backend: DeepSeek API

### POST `/api/v1/ai/analyze-logs`
**Analyze Logs / AI 日志分析**

**Request Body:**
```json
{
  "hours": 1,
  "host_id": 1,
  "level": "ERROR"
}
```

**Response** `200`:
```json
{
  "success": true,
  "analysis": {
    "title": "数据库连接异常",
    "severity": "warning",
    "summary": "检测到多次数据库连接超时...",
    "recommendations": ["检查数据库连接池配置", "排查网络延迟"]
  },
  "log_count": 45
}
```

---

### GET `/api/v1/ai/insights`
**List AI Insights / AI 洞察列表**

| Param | Type | Description |
|-------|------|-------------|
| page | int | 页码 |
| page_size | int | 每页数量 |
| severity | string | info / warning / critical |
| status | string | new / reviewed / dismissed |

---

### POST `/api/v1/ai/chat`
**AI Chat / AI 对话**

Natural language Q&A based on current system context (logs, metrics, alerts, services).
基于当前系统上下文（日志、指标、告警、服务状态）的自然语言问答。

**Request Body:**
```json
{
  "question": "为什么服务器 CPU 持续偏高？"
}
```

**Response** `200`:
```json
{
  "answer": "根据最近 1 小时的监控数据分析...",
  "sources": ["metrics", "logs"],
  "memory_context": []
}
```

---

### POST `/api/v1/ai/root-cause`
**Root Cause Analysis / 根因分析**

| Param | Type | Description |
|-------|------|-------------|
| alert_id | int | **Required** 告警 ID |

Analyzes metrics and logs within ±30 minutes of the alert.
分析告警前后 30 分钟的指标和日志数据。

**Response** `200`:
```json
{
  "alert_id": 42,
  "analysis": {
    "root_cause": "磁盘 I/O 饱和导致服务响应超时",
    "evidence": ["磁盘使用率 95%", "I/O wait 持续 > 30%"],
    "recommendations": ["扩容磁盘", "清理日志文件"]
  }
}
```

---

### GET `/api/v1/ai/system-summary`
**System Summary / 系统概览**

Returns a snapshot of current system health for AI frontend display.
返回当前系统健康快照，用于 AI 前端展示。

**Response** `200`:
```json
{
  "hosts": {"total": 5, "online": 4, "offline": 1},
  "services": {"total": 20, "up": 18, "down": 2},
  "recent_1h": {"alert_count": 3, "error_log_count": 12},
  "avg_usage": {"cpu_percent": 45.2, "memory_percent": 62.1}
}
```

---

## 14. Notifications / 通知管理

> Auth: Bearer Token
> Channels: DingTalk (钉钉), Feishu (飞书), WeCom (企微), Email (邮件), Webhook

### GET `/api/v1/notification-channels`
**List Channels / 通知渠道列表**

**Response** `200`: Array of NotificationChannel objects

---

### POST `/api/v1/notification-channels`
**Create Channel / 创建通知渠道**

**Request Body:**
```json
{
  "name": "运维钉钉群",
  "channel_type": "dingtalk",
  "config": {"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx"},
  "is_enabled": true
}
```

**Response** `201`: NotificationChannel object

---

### PUT `/api/v1/notification-channels/{channel_id}`
**Update Channel / 更新通知渠道**

---

### DELETE `/api/v1/notification-channels/{channel_id}`
**Delete Channel / 删除通知渠道**

**Response** `204`: No content

---

### GET `/api/v1/notification-channels/logs`
**List Notification Logs / 通知发送日志**

| Param | Type | Description |
|-------|------|-------------|
| alert_id | int | 按告警 ID 筛选 |
| limit | int | 返回数量 (default 50, max 200) |

---

## 15. Notification Templates / 通知模板

> Auth: **Admin** role required
> 认证：需要 **管理员** 角色

### GET `/api/v1/notification-templates`
**List Templates / 模板列表**

---

### POST `/api/v1/notification-templates`
**Create Template / 创建模板**

```json
{
  "name": "告警通知-钉钉",
  "channel_type": "dingtalk",
  "title_template": "【{{severity}}】{{title}}",
  "body_template": "告警内容：{{message}}\n主机：{{hostname}}",
  "is_default": true
}
```

Setting `is_default=true` clears default for same channel_type.
设为默认时，自动取消同类型其他模板的默认标记。

---

### PUT `/api/v1/notification-templates/{template_id}`
**Update Template / 更新模板**

---

### DELETE `/api/v1/notification-templates/{template_id}`
**Delete Template / 删除模板**

---

## 16. Auto Remediation / 自动修复

> Auth: Bearer Token
> Built-in Runbooks: disk_cleanup, memory_pressure, service_restart, log_rotation, zombie_killer, connection_reset

### GET `/api/v1/remediations`
**List Remediations / 修复日志列表**

| Param | Type | Description |
|-------|------|-------------|
| status | string | pending / pending_approval / approved / executing / success / failed / rejected |
| host_id | int | 按主机筛选 |
| triggered_by | string | auto / manual |
| page | int | 页码 |
| page_size | int | 每页数量 |

---

### GET `/api/v1/remediations/stats`
**Remediation Stats / 修复统计**

**Response** `200`:
```json
{
  "total": 100, "success": 85, "failed": 10, "pending": 5,
  "success_rate": 85.0,
  "avg_duration_seconds": 45.3,
  "today_count": 3, "week_count": 15
}
```

---

### GET `/api/v1/remediations/{remediation_id}`
**Get Remediation Detail / 修复详情**

---

### POST `/api/v1/remediations/{remediation_id}/approve`
**Approve Remediation / 审批修复**

```json
{ "comment": "确认执行" }
```

Only works when status is `pending_approval`.

---

### POST `/api/v1/remediations/{remediation_id}/reject`
**Reject Remediation / 拒绝修复**

```json
{ "comment": "风险太高，拒绝执行" }
```

---

### POST `/api/v1/alerts/{alert_id}/remediate`
**Trigger Remediation / 手动触发修复**

Manually trigger remediation for a specific alert.
手动触发对指定告警的修复流程。

**Response** `200`: RemediationLog object

**Errors**: `409` Remediation already in progress

---

## 17. Reports / 运维报告

> Auth: Bearer Token

### GET `/api/v1/reports`
**List Reports / 报告列表**

| Param | Type | Description |
|-------|------|-------------|
| report_type | string | daily / weekly |
| page | int | 页码 |
| page_size | int | 每页数量 |

---

### GET `/api/v1/reports/{report_id}`
**Get Report Detail / 报告详情**

---

### POST `/api/v1/reports/generate`
**Generate Report / 生成报告**

**Request Body:**
```json
{
  "report_type": "daily",
  "period_start": "2026-02-19T00:00:00+08:00",
  "period_end": "2026-02-20T00:00:00+08:00"
}
```

If period not specified, defaults to yesterday (daily) or last 7 days (weekly).
未指定时间段时，默认为昨天（日报）或过去 7 天（周报）。

**Response** `200`: Report object

---

### DELETE `/api/v1/reports/{report_id}`
**Delete Report / 删除报告**

Admin only. 仅管理员可操作。

---

## 18. SLA Management / SLA 管理

> Auth: Bearer Token

### GET `/api/v1/sla/rules`
**List SLA Rules / SLA 规则列表**

**Response** `200`: Array of SLARule objects with service_name

---

### POST `/api/v1/sla/rules`
**Create SLA Rule / 创建 SLA 规则**

```json
{
  "service_id": 1,
  "name": "Backend API SLA",
  "target_percent": 99.9,
  "calculation_window": "monthly"
}
```

`calculation_window`: `daily`, `weekly`, `monthly`

**Errors**: `400` Service already has an SLA rule

---

### DELETE `/api/v1/sla/rules/{rule_id}`
**Delete SLA Rule / 删除 SLA 规则**

---

### GET `/api/v1/sla/status`
**SLA Status Board / SLA 状态看板**

Calculates real-time availability and error budget for each SLA rule.
计算每个 SLA 规则的实时可用率和错误预算。

**Response** `200`:
```json
[{
  "rule_id": 1, "service_id": 1, "service_name": "backend-api",
  "target_percent": 99.9, "actual_percent": 99.95,
  "is_met": true,
  "error_budget_remaining_minutes": 38.5,
  "calculation_window": "monthly",
  "total_checks": 43200, "down_checks": 22
}]
```

---

### GET `/api/v1/sla/violations`
**List SLA Violations / SLA 违规事件**

| Param | Type | Description |
|-------|------|-------------|
| start_date | string | 开始日期 YYYY-MM-DD |
| end_date | string | 结束日期 YYYY-MM-DD |

---

### GET `/api/v1/sla/report`
**SLA Availability Report / 可用性报告**

| Param | Type | Description |
|-------|------|-------------|
| service_id | int | **Required** 服务 ID |
| period | string | monthly (default) |
| start_date | string | 开始日期 |
| end_date | string | 结束日期 |

**Response** `200`:
```json
{
  "service_id": 1, "service_name": "backend-api",
  "target_percent": 99.9,
  "period_start": "2026-01-21", "period_end": "2026-02-20",
  "overall_availability": 99.95,
  "daily_trend": [{"date": "2026-02-20", "availability": 100.0}],
  "violations": [],
  "total_downtime_minutes": 21.6,
  "summary": "服务 backend-api 在报告期间内可用率 99.95%，达到 SLA 目标 99.9%。"
}
```

---

## 19. System Settings / 系统设置

> Auth: Bearer Token (read), Admin (write)

### GET `/api/v1/settings`
**Get Settings / 获取系统设置**

Returns all settings with defaults fallback.

**Response** `200`:
```json
{
  "metrics_retention_days": {"value": "90", "description": "指标数据保留天数"},
  "alert_check_interval": {"value": "60", "description": "告警检查间隔(秒)"},
  "heartbeat_timeout": {"value": "120", "description": "心跳超时时间(秒)"},
  "webhook_retry_count": {"value": "3", "description": "Webhook 重试次数"}
}
```

---

### PUT `/api/v1/settings`
**Update Settings / 更新系统设置**

Admin only. 仅管理员。

**Request Body:**
```json
{
  "metrics_retention_days": "180",
  "alert_check_interval": "30"
}
```

**Response** `200`: `{"status": "ok"}`

---

## 20. Audit Logs / 审计日志

> Auth: **Admin** role required

### GET `/api/v1/audit-logs`
**List Audit Logs / 审计日志列表**

| Param | Type | Description |
|-------|------|-------------|
| user_id | int | 按用户筛选 |
| action | string | 按操作类型筛选 (login, create_user, update_settings, etc.) |
| resource_type | string | 按资源类型筛选 (user, alert, settings, etc.) |
| page | int | 页码 |
| page_size | int | 每页数量 |

**Response** `200`:
```json
{
  "items": [{
    "id": 1, "user_id": 1, "action": "login",
    "resource_type": "user", "resource_id": 1,
    "detail": null, "ip_address": "10.0.0.1",
    "created_at": "2026-02-20T14:30:00"
  }],
  "total": 100, "page": 1, "page_size": 20
}
```

---

## 21. Agent Data Reporting / Agent 数据上报

> Auth: `X-Agent-Token` header
> 认证：`X-Agent-Token` 请求头（Agent 令牌）

### POST `/api/v1/agent/register`
**Register Agent / Agent 注册**

Idempotent: updates if exists, creates if not.
幂等操作：已存在则更新，不存在则新建。

**Request Body:**
```json
{
  "hostname": "web-01",
  "ip_address": "10.0.0.1",
  "os": "CentOS Stream",
  "os_version": "9",
  "arch": "x86_64",
  "cpu_cores": 8,
  "memory_total_mb": 15360,
  "agent_version": "1.0.0",
  "tags": ["production", "web"],
  "group_name": "web-servers"
}
```

**Response** `200`:
```json
{
  "host_id": 1,
  "hostname": "web-01",
  "status": "online",
  "created": true
}
```

---

### POST `/api/v1/agent/heartbeat`
**Agent Heartbeat / Agent 心跳**

```json
{ "host_id": 1 }
```

Updates host online status and writes to Redis (300s TTL) for offline detection.

**Response** `200`: `{"status": "ok", "server_time": "2026-02-20T14:30:00Z"}`

---

### POST `/api/v1/agent/metrics`
**Report Metrics / 上报主机指标**

```json
{
  "host_id": 1,
  "cpu_percent": 45.2,
  "cpu_load_1": 2.1, "cpu_load_5": 1.8, "cpu_load_15": 1.5,
  "memory_used_mb": 8192, "memory_percent": 62.1,
  "disk_used_mb": 51200, "disk_total_mb": 102400, "disk_percent": 50.0,
  "net_bytes_sent": 1048576, "net_bytes_recv": 2097152,
  "net_send_rate_kb": 100.5, "net_recv_rate_kb": 200.3,
  "net_packet_loss_rate": 0.01,
  "timestamp": "2026-02-20T14:30:00Z"
}
```

**Response** `201`: `{"status": "ok", "metric_id": 42}`

---

### POST `/api/v1/agent/services/register`
**Register Service / 注册服务**

Idempotent. Auto-classifies into middleware/business/infrastructure.

```json
{
  "name": "backend-api",
  "type": "http",
  "target": "http://localhost:8001/health",
  "host_id": 1,
  "check_interval": 60,
  "timeout": 10
}
```

**Response** `200`: `{"service_id": 1, "created": true}`

---

### POST `/api/v1/agent/services`
**Report Service Check / 上报服务检查结果**

```json
{
  "service_id": 1,
  "status": "up",
  "response_time_ms": 45,
  "status_code": 200,
  "checked_at": "2026-02-20T14:30:00Z"
}
```

**Response** `201`: `{"status": "ok", "check_id": 123}`

---

### POST `/api/v1/agent/db-metrics`
**Report Database Metrics / 上报数据库指标**

Auto-creates MonitoredDatabase record if not exists. Triggers db_metric alert rules.
自动创建被监控数据库记录。触发数据库指标告警规则检查。

```json
{
  "host_id": 1,
  "db_name": "nightmend",
  "db_type": "postgres",
  "connections_total": 50,
  "connections_active": 12,
  "database_size_mb": 1024,
  "slow_queries": 3,
  "tables_count": 45,
  "transactions_committed": 15000,
  "transactions_rolled_back": 5,
  "qps": 150,
  "tablespace_used_pct": 45.2,
  "slow_queries_detail": [{"query": "SELECT ...", "duration_ms": 5000}]
}
```

**Response** `201`: `{"status": "ok", "database_id": 1, "metric_id": 42}`

---

### POST `/api/v1/agent/logs`
**Batch Ingest Logs / 批量写入日志**

Also broadcasts to WebSocket subscribers and checks log keyword alert rules.
同时广播到 WebSocket 订阅者并检查日志关键字告警规则。

```json
{
  "logs": [
    {
      "host_id": 1,
      "service": "backend",
      "level": "ERROR",
      "message": "Connection refused to database",
      "timestamp": "2026-02-20T14:30:00Z"
    }
  ]
}
```

**Response** `201`: `{"received": 5}`

---

## 22. Agent Tokens / Agent 令牌管理

> Auth: **Admin** role required

### POST `/api/v1/agent-tokens`
**Create Agent Token / 创建 Agent 令牌**

```json
{ "name": "Production Agent" }
```

**Response** `201`:
```json
{
  "id": 1,
  "name": "Production Agent",
  "token_prefix": "vop_a1b2",
  "token": "vop_a1b2c3d4e5f6...",
  "is_active": true,
  "created_by": 1,
  "created_at": "2026-02-20T14:30:00Z"
}
```

> ⚠️ The full `token` value is only returned once at creation time!
> ⚠️ 完整的 `token` 值仅在创建时返回一次！

---

### GET `/api/v1/agent-tokens`
**List Agent Tokens / Agent 令牌列表**

Returns tokens without full token value (only prefix).

---

### DELETE `/api/v1/agent-tokens/{token_id}`
**Revoke Agent Token / 吊销 Agent 令牌**

Sets `is_active = false` (soft delete).

**Response** `204`: No content

---

## 23. Webhooks / 外部告警接入

> Auth: Bearer Token (in `Authorization` header)
> Added in v2026.03.29

### POST `/api/v1/webhooks/alertmanager`
**AlertManager Webhook / AlertManager 告警接收**

Receives alerts from Prometheus AlertManager. Supports HMAC signature verification and Redis deduplication.
接收 Prometheus AlertManager 推送的告警，支持 HMAC 签名验证和 Redis 去重。

**Headers:**
```
Authorization: Bearer <ALERTMANAGER_WEBHOOK_TOKEN>
X-Vigilops-Signature: sha256=<hmac_hex>  (optional)
```

**Request Body:** Standard AlertManager webhook payload.

**Response** `200`:
```json
{
  "status": "ok",
  "received": 3,
  "deduplicated": 1,
  "processed": 2
}
```

---

## 24. Demo / 演示接口

> Auth: None (public)
> Added in v2026.03.29

### GET `/api/v1/demo/alerts/stream`
**Alert Diagnosis SSE Stream / 告警诊断 SSE 流**

Server-Sent Events endpoint for real-time alert diagnosis display. Requires `ENABLE_REMEDIATION=false`.

**Response:** SSE stream with events:
```
event: alert
data: {"alert_id": 1, "title": "HighCPU", "severity": "warning", ...}

event: diagnosis
data: {"alert_id": 1, "root_cause": "Memory leak in Java process", "confidence": 0.92, ...}
```

---

## 25. Custom Runbooks / 自定义 Runbook

> Auth: Bearer Token (Admin/Operator)
> Added in v2026.03.29

### GET `/api/v1/custom-runbooks`
**List Custom Runbooks / 自定义 Runbook 列表**

### POST `/api/v1/custom-runbooks`
**Create Custom Runbook / 创建自定义 Runbook**

```json
{
  "name": "nginx_restart",
  "description": "Restart nginx when upstream errors detected",
  "match_alert_types": ["service_down"],
  "trigger_keywords": ["nginx", "upstream"],
  "risk_level": "confirm",
  "safety_checks": ["require_label:service"],
  "steps": [
    {"name": "Check status", "command": "systemctl status nginx", "timeout_sec": 10},
    {"name": "Restart", "command": "systemctl restart nginx", "timeout_sec": 30, "rollback_command": "systemctl start nginx"}
  ],
  "verify_steps": [
    {"name": "Verify", "command": "curl -f http://localhost:80/health", "timeout_sec": 10}
  ]
}
```

### PUT `/api/v1/custom-runbooks/{runbook_id}`
**Update Custom Runbook / 更新自定义 Runbook**

### DELETE `/api/v1/custom-runbooks/{runbook_id}`
**Delete Custom Runbook / 删除自定义 Runbook**

### POST `/api/v1/ai/generate-runbook`
**AI Generate Runbook / AI 生成 Runbook**

Uses AI to generate a runbook from natural language description.

```json
{
  "description": "当 Redis 内存超过 80% 时自动清理过期 key",
  "risk_level": "confirm"
}
```

---

## Error Response Format / 错误响应格式

All errors follow FastAPI's standard format:
```json
{
  "detail": "Error message description"
}
```

Common HTTP status codes:
| Code | Meaning |
|------|---------|
| 400 | Bad Request / 请求参数错误 |
| 401 | Unauthorized / 未认证 |
| 403 | Forbidden / 无权限 |
| 404 | Not Found / 资源不存在 |
| 409 | Conflict / 资源冲突 |
| 500 | Internal Server Error / 服务器内部错误 |
| 502 | Bad Gateway / AI 服务调用失败 |
