# VigilOps — Product Requirements Document

> Version: 1.0 | Date: 2026-02-15 | Status: Draft

---

## 1. 产品概述

### 1.1 定位

**VigilOps** 是一个开源的、AI 驱动的一站式智能运维监控平台。面向中小型技术团队，提供服务器监控、应用服务监控、日志管理、数据库监控和 LLM API 管理能力，并通过 AI 实现智能日志分析、告警降噪和根因定位。

一句话：**Prometheus + Grafana 的功能覆盖 + Datadog 的易用性 + AI 原生的智能分析，一个 `docker compose up` 搞定。**

### 1.2 目标用户

中小型技术团队（5-50 人），具备以下特征：

- 管理 2-50 台服务器（云服务器、物理机、虚拟机）
- 部署了多个微服务 / API 服务
- 使用 MySQL / PostgreSQL 等关系型数据库
- 可能使用 LLM API（OpenAI / Anthropic / DeepSeek 等）
- 用不起 Datadog（$15/主机/月），觉得 Prometheus+Grafana 门槛高
- 没有专职运维，开发兼运维

**用户画像：**

| 角色 | 核心需求 |
|------|---------|
| **技术负责人 / CTO** | 全局视图，了解所有服务器和服务状态，费用控制 |
| **后端开发** | 快速定位线上问题，查日志，排查慢查询 |
| **运维 / SRE** | 告警管理，服务器资源规划，日志归档 |
| **AI 工程师** | LLM API 费用追踪，模型可用性监控 |

### 1.3 核心价值

1. **一站式** — 服务器、服务、日志、数据库、LLM，全在一个平台
2. **AI 原生** — 不只是展示数据，AI 帮你分析问题、定位根因、给出建议
3. **轻量易部署** — `docker compose up` 一键启动，Agent 一键安装
4. **开源免费** — 核心功能全开源，社区驱动

### 1.4 竞品对比

| 能力 | Datadog | Prometheus + Grafana | 云智慧 | Zabbix | **VigilOps** |
|------|---------|---------------------|--------|--------|-------------|
| 服务器监控 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 服务健康监控 | ✅ | ✅（需配置） | ✅ | ✅ | ✅ |
| 日志采集与搜索 | ✅（贵） | ❌（需 Loki） | ✅ | ❌ | ✅ |
| AI 智能日志分析 | 部分 | ❌ | ❌ | ❌ | ✅ |
| 数据库监控 | ✅（贵） | ❌（需 exporter） | ✅ | ✅ | ✅ |
| LLM API 管理 | ❌ | ❌ | ❌ | ❌ | ✅ |
| AI 告警降噪 | ✅（贵） | ❌ | 部分 | ❌ | ✅ |
| 根因定位 | ✅（贵） | ❌ | 部分 | ❌ | ✅ |
| 自部署 | ❌ | ✅（门槛高） | ❌ | ✅ | ✅ |
| 易用性 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| 价格 | $15/主机/月 | 免费 | 商业 | 免费 | 免费 |

---

## 2. 系统架构

### 2.1 整体架构

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ 服务器 A  │  │ 服务器 B  │  │ 服务器 C  │
│  Agent   │  │  Agent   │  │  Agent   │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │
     └──────────────┼──────────────┘
                    │ HTTPS / WebSocket
                    ▼
          ┌─────────────────┐
          │   VigilOps Server │
          │                   │
          │  ┌─────────────┐  │
          │  │  API Server  │  │
          │  │  (FastAPI)   │  │
          │  └──────┬──────┘  │
          │         │         │
          │  ┌──────┴──────┐  │
          │  │  数据存储层   │  │
          │  │ PostgreSQL   │  │
          │  │ Redis        │  │
          │  │ ClickHouse*  │  │
          │  └──────┬──────┘  │
          │         │         │
          │  ┌──────┴──────┐  │
          │  │  AI 分析引擎  │  │
          │  │ LLM 集成     │  │
          │  └─────────────┘  │
          │                   │
          │  ┌─────────────┐  │
          │  │  前端 (React) │  │
          │  └─────────────┘  │
          └─────────────────┘
```

### 2.2 Agent（数据采集端）

部署在每台被监控的服务器上，轻量级后台进程。

**职责：**
- 采集服务器指标（CPU / 内存 / 磁盘 / 网络）
- 采集指定日志文件（tail -f 模式，实时推送）
- 执行服务健康检查（HTTP / TCP 拨测）
- 采集数据库指标（连接数、慢查询、QPS）
- 定时上报数据到 Server

**要求：**
- 资源占用极低（< 50MB 内存，< 1% CPU）
- 支持 Linux（主要）、macOS（开发环境）
- 一键安装：`curl -sSL https://raw.githubusercontent.com/LinChuang2008/vigilops/main/scripts/install-agent.sh | VIGILOPS_SERVER=https://your-server AGENT_TOKEN=your-token bash`
- 配置文件指定 Server 地址、采集项目、日志路径等
- 断线自动重连，本地缓存未发送数据

**Agent 配置示例：**
```yaml
# /etc/vigilops/agent.yaml
server:
  url: https://vigilops.example.com
  token: "agent-token-xxx"

host:
  name: "web-server-01"
  tags: ["production", "web"]

metrics:
  interval: 15s  # 采集间隔

logs:
  - path: /var/log/nginx/access.log
    service: nginx
    type: access
  - path: /var/log/app/api.log
    service: api-server
    type: application

services:
  - name: "API Server"
    type: http
    url: http://localhost:8000/health
    interval: 30s
  - name: "Redis"
    type: tcp
    host: localhost
    port: 6379
    interval: 30s

databases:
  - name: "主数据库"
    type: postgresql
    host: localhost
    port: 5432
    username: monitor
    password: "xxx"
    slow_query_threshold: 1000ms  # 慢查询阈值
```

### 2.3 Server（监控中心）

接收、存储、分析所有 Agent 上报的数据，提供 Web UI 和 API。

**组件：**
- **API Server**（FastAPI）— REST API + WebSocket 实时推送
- **PostgreSQL** — 元数据、配置、告警规则、用户信息
- **Redis** — 缓存、实时指标暂存、Agent 心跳
- **ClickHouse**（可选，MVP 用 PostgreSQL）— 大量指标和日志的时序存储
- **前端**（React + TypeScript + Ant Design + ECharts）— Web 仪表盘
- **AI 引擎** — 调用 LLM API 进行日志分析、根因定位

---

## 3. 功能模块

### 3.1 服务器监控

#### 3.1.1 指标采集

| 指标类别 | 具体指标 |
|---------|---------|
| **CPU** | 使用率、负载（1/5/15min）、核心数、各核使用率 |
| **内存** | 总量、已用、可用、使用率、Swap 使用率 |
| **磁盘** | 各分区总量/已用/可用/使用率、IO 读写速率、IOPS |
| **网络** | 各网卡收发速率、收发包数、错误包数、连接数 |
| **进程** | 进程总数、Top 10 CPU/内存消耗进程 |
| **系统** | 运行时间（uptime）、操作系统版本、内核版本 |

#### 3.1.2 服务器管理

- 服务器列表（名称、IP、标签、状态、Agent 版本、最后心跳）
- 分组管理（按环境：生产/测试/开发，按业务：支付/用户/订单）
- 标签系统（自定义 key-value 标签，用于筛选和分组）
- 服务器详情页（实时指标图表 + 历史趋势）
- Agent 在线/离线状态，心跳超时自动告警

#### 3.1.3 全局视图

- 所有服务器概览仪表盘（卡片式 / 列表式切换）
- 资源使用率热力图（快速发现资源紧张的服务器）
- 按分组/标签筛选查看

### 3.2 应用服务监控

#### 3.2.1 服务健康检查（主动拨测）

- **HTTP 检查** — 定时请求指定 URL，检查状态码、响应时间、响应内容
- **TCP 检查** — 定时连接指定 host:port，检查是否可达
- **自定义脚本**（后续）— 执行自定义脚本，检查退出码

每次检查记录：
- 状态（正常 / 异常 / 超时）
- 响应时间（ms）
- 状态码（HTTP）
- 错误信息

#### 3.2.2 服务管理

- 服务列表（名称、类型、所在服务器、当前状态、可用率）
- 服务详情页（可用率趋势、响应时间图表、最近检查记录）
- 可用率统计（日 / 周 / 月 SLA 报告）
- 状态变更历史（什么时候挂了、什么时候恢复的）

#### 3.2.3 状态页（可选）

- 公开的服务状态页面（可分享给团队/客户）
- 显示各服务当前状态和历史可用率

### 3.3 日志管理

#### 3.3.1 日志采集

- Agent 以 tail -f 模式实时采集指定日志文件
- 支持多日志源（每台服务器可配多个日志文件）
- 每条日志附带元数据：服务器、服务名、日志文件路径、时间戳
- 支持多行日志合并（如 Java stack trace）
- 断线重连后从上次位置继续采集（记录 offset）

#### 3.3.2 日志存储与归档

- 实时日志存入数据库（热数据，保留可配置天数，默认 7 天）
- 过期日志自动压缩归档（gzip，按天打包）
- 归档文件可存储在本地磁盘或对象存储（S3 兼容）
- 支持配置保留策略（热数据天数 + 归档保留天数）

#### 3.3.3 日志搜索与查看

- 实时日志流（类 `tail -f`，WebSocket 推送）
- 全文搜索（关键字、正则表达式）
- 多维度筛选（时间范围、服务器、服务、日志级别）
- 上下文查看（点击某条日志，查看前后 N 行）
- 日志级别识别与着色（ERROR 红色、WARN 黄色等）

#### 3.3.4 🧠 AI 智能日志分析

这是 VigilOps 的核心差异化能力。

**异常检测**
- AI 自动识别日志中的异常模式（不依赖手写规则）
- 检测频率突变（某类错误突然增多）
- 检测新出现的错误类型

**错误自动归类**
- 同一个 bug 导致的大量日志自动归为一个事件
- 去重后只展示独立事件，附带出现次数和时间分布
- 类似 Sentry 的 Issue 概念

**根因定位**
- 关联多个服务器、多个服务的日志
- 分析因果链（如：数据库连接池满 → API 超时 → 前端 502）
- 给出根因分析报告

**自然语言查询**
- 运维人员用自然语言提问："昨天凌晨 3 点支付服务为什么报错？"
- AI 从日志中检索相关内容，生成分析报告

**修复建议**
- 基于错误类型和上下文，AI 给出可能的修复方案
- 常见问题可积累知识库，加速后续诊断

**故障预测**
- 分析日志趋势，提前预警
- 如：磁盘写入速度异常增长，预计 N 小时后磁盘满
- 如：某类错误频率逐渐上升，可能即将爆发

**运维摘要**
- AI 自动生成每日 / 每周运维报告
- 包括：关键事件、资源使用趋势、告警统计、建议操作

### 3.4 数据库监控

#### 3.4.1 支持的数据库

| 数据库 | 优先级 | 采集方式 |
|--------|--------|---------|
| **PostgreSQL** | P0（MVP） | `pg_stat_activity`, `pg_stat_statements` |
| **MySQL** | P0（MVP） | `SHOW PROCESSLIST`, `performance_schema` |
| Redis | P1 | `INFO` 命令 |
| MongoDB | P2 | `serverStatus` |

#### 3.4.2 监控指标

**连接监控**
- 当前连接数 / 最大连接数 / 连接使用率
- 活跃连接 vs 空闲连接
- 按来源 IP / 用户 / 数据库分组的连接数
- 连接数趋势图

**慢查询监控**
- 慢查询列表（SQL、执行时间、扫描行数、时间戳）
- 慢查询统计（Top N 最慢查询、最频繁慢查询）
- 慢查询趋势（每小时/天慢查询数量变化）
- 可配置慢查询阈值（默认 1000ms）
- AI 分析慢查询原因并建议优化（如：缺少索引）

**性能指标**
- QPS（每秒查询数）
- TPS（每秒事务数）
- 缓存命中率（Buffer Cache Hit Ratio）
- 锁等待 / 死锁检测
- 表大小 / 索引大小

#### 3.4.3 数据库管理

- 数据库实例列表（名称、类型、所在服务器、状态）
- 实例详情页（实时指标 + 慢查询列表 + 连接分析）
- 只读连接，不对数据库做任何写操作

### 3.5 LLM API 管理

沿用 TokenFlow 的核心功能，作为 VigilOps 的一个模块。

#### 3.5.1 统一代理网关

- 单一 OpenAI 兼容端点：`POST /v1/chat/completions`
- 支持模型列表查询：`GET /v1/models`
- 支持 SSE 流式响应
- 认证方式：VigilOps API Key（`Bearer vg-xxx`）

#### 3.5.2 Provider 管理

- 支持多个 LLM Provider（OpenAI、Anthropic、DeepSeek、Qwen、Ollama）
- Provider API Key 加密存储（AES-256）
- 模型自动发现 + 内置定价表
- 向导式添加流程

#### 3.5.3 费用管理

- 每次请求自动记录 token 用量和费用
- 费用仪表盘（总费用、趋势图、Top 模型、Top 项目）
- 多维度分析（按项目 / 模型 / 成员）
- 预算告警（可选）

### 3.6 告警中心

#### 3.6.1 告警规则

- **内置规则**（开箱即用）：
  - 服务器：CPU > 90%、内存 > 90%、磁盘 > 85%、Agent 离线
  - 服务：服务不可达、响应时间 > 阈值
  - 数据库：连接数 > 80%、出现死锁、慢查询突增
  - 日志：ERROR 级别日志突增
- **自定义规则**：
  - 支持基于指标的阈值告警
  - 支持基于日志关键字的告警
  - 告警条件：阈值 + 持续时间（如 CPU > 90% 持续 5 分钟）

#### 3.6.2 🧠 AI 告警降噪

- 自动合并重复告警（同一问题只通知一次）
- 告警关联分析（多个告警可能是同一根因，合并展示）
- 告警优先级自动分类（Critical / Warning / Info）
- 告警抑制（已确认的问题不再重复通知）

#### 3.6.3 通知渠道

**MVP（P0）**

| 渠道 | 说明 |
|------|------|
| Web 站内通知 | 实时弹窗 + 通知中心 |
| Webhook（通用） | 万能接口，用户自行对接任何系统 |
| 邮件 (SMTP) | 最基础的通知方式 |
| 企业微信 | Webhook 机器人 + 应用消息推送 |
| 飞书 | Webhook 机器人 |
| 钉钉 | Webhook 机器人 |

**P1 — 扩展渠道**

| 渠道 | 说明 |
|------|------|
| 微信推送 | 通过 Server酱 / PushPlus 等第三方推送到个人微信 |
| 短信 | 阿里云 / 腾讯云短信 API，用于严重告警 |
| 电话语音 | 严重故障自动拨打电话，确保人被叫醒 |

**P2 — 海外 / 社区**

| 渠道 | 说明 |
|------|------|
| Slack | 海外团队 |
| Telegram | 开发者社区 |
| Discord | 开源社区 |

**告警升级策略（可配置）**

```
Warning   → 站内通知 + IM（企微/飞书/钉钉）
Critical  → 站内 + IM + 邮件
Fatal / 长时间未确认 → IM + 邮件 + 短信 + 电话
```

用户可自定义每个告警级别的通知渠道组合。

#### 3.6.4 告警管理

- 告警列表（状态：触发中 / 已确认 / 已恢复）
- 告警详情（触发时间、恢复时间、关联指标、关联日志）
- 告警历史和统计
- 值班排班（后续）

### 3.7 用户认证与权限

#### 3.7.1 认证

- 邮箱 + 密码注册登录
- JWT 认证（access token + refresh token）
- 首个注册用户自动成为 Admin

#### 3.7.2 RBAC

| 角色 | 权限 |
|------|------|
| **Admin** | 所有操作：管理用户、服务器、告警规则、系统设置 |
| **Member** | 查看仪表盘、查看日志、查看告警（只读） |

### 3.8 系统设置

- Agent Token 管理（生成、吊销）
- 告警全局配置（默认通知渠道、静默时段）
- 数据保留策略（指标保留天数、日志保留天数、归档策略）
- AI 配置（LLM Provider 选择、API Key、分析频率）
- 系统信息（版本、资源使用、许可证）

---

## 4. 页面清单

### 4.1 公开页面

| 页面 | 说明 |
|------|------|
| 登录 | 邮箱 + 密码 |
| 注册 | 邮箱 + 密码 + 名称 |
| 状态页（可选） | 公开的服务状态展示 |

### 4.2 主要页面

| 页面 | 说明 |
|------|------|
| **全局仪表盘** | 所有服务器/服务/数据库/LLM 的概览 |
| **服务器列表** | 所有服务器卡片/列表，状态和关键指标 |
| **服务器详情** | 单台服务器的指标图表、日志、服务、数据库 |
| **服务列表** | 所有被监控服务的状态和可用率 |
| **服务详情** | 单个服务的可用率趋势、响应时间、检查记录 |
| **日志中心** | 实时日志流 + 搜索 + 筛选 + AI 分析入口 |
| **AI 分析** | AI 日志分析结果、根因报告、自然语言查询 |
| **数据库列表** | 所有数据库实例状态 |
| **数据库详情** | 连接数、慢查询列表、性能指标 |
| **LLM 管理** | Provider 密钥、模型配置、费用仪表盘 |
| **告警中心** | 告警列表、告警规则管理、通知配置 |
| **用户管理** | 用户列表、角色管理（Admin） |
| **系统设置** | Agent Token、数据保留、AI 配置等 |

---

## 5. 非功能需求

### 5.1 性能

- Agent 资源占用：< 50MB 内存，< 1% CPU
- Server API 响应：< 200ms（p95）
- 支持管理 50 台服务器 / 100 个服务（单实例 Server）
- 日志搜索：100 万条日志内 < 3 秒返回结果
- 仪表盘页面加载：< 2 秒

### 5.2 安全

- Agent 与 Server 之间通信加密（HTTPS）
- Agent Token 认证，防止未授权数据上报
- 数据库密码等敏感信息加密存储（AES-256）
- JWT 认证（access token 2h，refresh token 7d）
- AI 分析不发送原始日志到第三方（支持本地 LLM）

### 5.3 可靠性

- Agent 断线自动重连 + 本地缓存
- Server 数据持久化（PostgreSQL）
- 告警通知失败自动重试

### 5.4 部署

- Docker Compose 一键部署（Server 端）
- Agent 一键安装脚本
- 支持 Linux（Ubuntu 20.04+、CentOS 7+、Debian 10+）
- 支持 macOS（开发环境）

---

## 6. 技术栈

| 层级 | 技术 |
|------|------|
| **Server 后端** | Python 3.12 + FastAPI |
| **Server 前端** | React + TypeScript + Ant Design + ECharts |
| **Agent** | Python（轻量，后续可用 Go/Rust 重写提升性能） |
| **数据库** | PostgreSQL 16（主存储）+ Redis 7（缓存/实时） |
| **时序存储** | PostgreSQL（MVP）→ ClickHouse（后续大规模） |
| **AI 引擎** | 支持多 LLM Provider（DeepSeek / OpenAI / Anthropic / 本地 Ollama） |
| **通信协议** | HTTPS + WebSocket |
| **部署** | Docker Compose |
| **认证** | JWT (python-jose) |
| **加密** | AES-256 (cryptography) |

---

## 7. 开发阶段

### Phase 1 — MVP（核心监控）

> 目标：跑通 "安装 Agent → 看到服务器数据 → 收到告警" 的核心链路

| 模块 | 功能 |
|------|------|
| Server 骨架 | FastAPI + PostgreSQL + Redis + Docker Compose |
| 认证 | 注册 / 登录 / JWT |
| Agent（基础） | 服务器指标采集 + 上报 |
| 服务器监控 | 服务器列表 + 详情 + 实时指标图表 |
| 服务监控 | HTTP/TCP 拨测 + 可用率 |
| 告警（基础） | 内置规则 + Webhook 通知 |
| 前端 | 仪表盘 + 服务器页 + 服务页 + 告警页 |

### Phase 2 — 日志与数据库

| 模块 | 功能 |
|------|------|
| 日志采集 | Agent tail 日志 + 推送到 Server |
| 日志存储 | 热存储 + 归档 + 搜索 |
| 日志查看 | 实时日志流 + 全文搜索 + 筛选 |
| 数据库监控 | PostgreSQL + MySQL 连接数、慢查询 |
| 告警增强 | 日志关键字告警 + 数据库告警规则 |

### Phase 3 — AI 智能分析

| 模块 | 功能 |
|------|------|
| AI 日志分析 | 异常检测 + 错误归类 + 根因定位 |
| 自然语言查询 | 用自然语言搜索和分析日志 |
| AI 告警降噪 | 告警合并 + 优先级分类 |
| 修复建议 | 基于错误上下文给出修复方案 |
| 运维摘要 | 每日/每周自动生成运维报告 |

### Phase 4 — LLM API 管理

| 模块 | 功能 |
|------|------|
| 代理网关 | OpenAI 兼容 API + 多 Provider 路由 |
| Provider 管理 | 密钥管理 + 模型发现 |
| 费用管理 | Token 追踪 + 费用仪表盘 + 多维分析 |

### Phase 5 — 增强

| 模块 | 功能 |
|------|------|
| 更多通知渠道 | 飞书 / 钉钉 / 企业微信 / 邮件 |
| 数据库扩展 | Redis / MongoDB 监控 |
| 故障预测 | AI 基于趋势预测故障 |
| 公开状态页 | 可分享的服务状态页面 |
| Agent 增强 | Go/Rust 重写，降低资源占用 |

---

## 8. MVP 端点清单

### 认证（4 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| /api/v1/auth/register | POST | 注册 |
| /api/v1/auth/login | POST | 登录 |
| /api/v1/auth/refresh | POST | Token 刷新 |
| /api/v1/auth/me | GET | 当前用户信息 |

### Agent 通信（4 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| /api/v1/agent/register | POST | Agent 注册/心跳 |
| /api/v1/agent/metrics | POST | 上报服务器指标 |
| /api/v1/agent/services | POST | 上报服务检查结果 |
| /api/v1/agent/heartbeat | POST | Agent 心跳 |

### 服务器管理（3 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| /api/v1/hosts | GET | 服务器列表 |
| /api/v1/hosts/{id} | GET | 服务器详情 |
| /api/v1/hosts/{id}/metrics | GET | 服务器历史指标 |

### 服务管理（3 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| /api/v1/services | GET | 服务列表 |
| /api/v1/services/{id} | GET | 服务详情 |
| /api/v1/services/{id}/checks | GET | 服务检查历史 |

### 告警（4 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| /api/v1/alerts | GET | 告警列表 |
| /api/v1/alerts/{id} | GET | 告警详情 |
| /api/v1/alerts/{id}/ack | POST | 确认告警 |
| /api/v1/alert-rules | GET/POST | 告警规则管理 |

### 系统（2 个）

| 端点 | 方法 | 说明 |
|------|------|------|
| /api/v1/settings | GET/PUT | 系统设置 |
| /health | GET | 健康检查 |

**MVP 合计：20 个端点**

---

## 9. 数据模型（核心）

### hosts（服务器）
```
id, name, ip, os, arch, agent_version, tags, group,
status (online/offline), last_heartbeat, created_at
```

### host_metrics（服务器指标）
```
id, host_id, timestamp,
cpu_usage, cpu_load_1m, cpu_load_5m, cpu_load_15m,
mem_total, mem_used, mem_usage,
disk_total, disk_used, disk_usage,
net_rx_bytes, net_tx_bytes, net_connections
```

### services（被监控服务）
```
id, host_id, name, type (http/tcp), config (json),
status (up/down/unknown), uptime_percent,
last_check_at, created_at
```

### service_checks（服务检查记录）
```
id, service_id, timestamp,
status (up/down/timeout), response_time_ms,
status_code, error_message
```

### logs（日志）
```
id, host_id, service, file_path,
timestamp, level (info/warn/error/fatal),
message, raw_line
```

### db_instances（数据库实例）
```
id, host_id, name, type (postgresql/mysql),
host, port, status, created_at
```

### db_metrics（数据库指标）
```
id, instance_id, timestamp,
connections_active, connections_idle, connections_max,
qps, tps, cache_hit_ratio, deadlocks
```

### slow_queries（慢查询）
```
id, instance_id, timestamp,
query_text, duration_ms, rows_scanned, rows_returned
```

### alerts（告警）
```
id, rule_id, host_id, service_id,
status (firing/acknowledged/resolved),
severity (critical/warning/info),
message, detail, fired_at, resolved_at
```

### alert_rules（告警规则）
```
id, name, type (metric/log/db),
condition (json), severity, enabled,
notification_channels (json)
```

---

## 10. 未来规划

### SaaS 版本（商业化）
- 多租户 / 团队隔离
- 更多数据库支持（Oracle、SQL Server、ClickHouse）
- SSO / LDAP 集成
- 高可用部署
- 更强的 AI 分析（自训练模型、知识库积累）
- Prometheus / Grafana 数据导入
- 移动端 App（告警推送）
- 专业技术支持

### 开源生态
- 插件系统（自定义 Agent 采集器、通知渠道）
- 社区贡献的告警规则模板
- Helm Chart（Kubernetes 部署）
- Terraform Provider

---

## 附录

### A. 项目信息

| 项目 | 信息 |
|------|------|
| 名称 | VigilOps |
| 定位 | 开源 AI 智能运维监控平台 |
| 仓库 | https://gitlab.lchuangnet.com/lchuangnet/vigilops.git |
| 技术栈 | FastAPI + React + PostgreSQL + Redis + Docker |
| 开源协议 | Apache 2.0（待定） |
| 作者 | Patrick Wang |
