# VigilOps v1.0 产品路线图

> **版本**: v1.0 | **制定日期**: 2026-03-14 | **制定人**: 产品官-小P
>
> **当前版本**: v2026.03.14 | **目标**: 持续迭代（版本号已改为日期制 vYYYY.MM.DD）

---

## 一、路线图概览

本路线图基于三份评估报告制定：

- **产品评估** (CMP-10)：综合评分 3.9/5，AI 差异化 5/5
- **竞品分析** (CMP-11)：PromQL 和 K8s 监控是最大功能缺失
- **增长策略** (CMP-13)：Demo 体验和分发执行严重滞后

### 里程碑总览

| 里程碑 | 主题 | 核心目标 | 预计版本周期 |
|--------|------|----------|-------------|
| **v0.9.2** | Demo 体验优化 | 提升首次用户转化率 | 2-3 周 |
| **v0.9.5** | 数据源扩展 | 补齐核心功能 Gap | 4-6 周 |
| **v1.0** | 生产就绪 | 规模化 + 标准化部署 | 4-6 周 |

### 优先级排序原则

1. **用户获取优先** — Demo 是当前唯一获客入口，必须先优化
2. **差异化增强** — PromQL + 自定义 Runbook 让 AI 能力覆盖更多场景
3. **生态融入** — Prometheus 对接 + Helm Chart 降低采用门槛
4. **规模突破** — >50 主机支持打开中型企业市场

---

## 二、v0.9.2 — Demo 体验优化

**目标**: 让首次访问用户在 30 秒内理解产品价值，并完成注册体验。

### F1: Landing Page（产品展示页）

**问题**: 当前 demo.lchuangnet.com 直接跳转到登录页。用户第一眼看到的是登录表单而非产品价值，转化率极低。增长审计评分仅 5/10。

**技术方案**:

- 在 React 前端新增 `/landing` 路由作为默认首页
- 页面结构：Hero 区（一句话 + GIF 动画）→ 三大特性卡片（AI 分析 / 自动修复 / MCP）→ 竞品对比表 → CTA 按钮
- 未登录用户访问 `/` 时重定向到 `/landing`，已登录用户直接进 Dashboard
- 静态页面，无需后端 API

**工作量**: 前端 3-5 人天

**依赖**: 需要 GIF/截图素材（可从现有 `docs/screenshots/` 提取）

**验收标准**:
- 未登录访问 demo 站首先看到 Landing Page
- 页面加载 < 2s（首屏）
- 包含「开始体验」和「查看文档」两个 CTA

---

### F2: 新手引导（Onboarding Tour）

**问题**: 登录后用户面对 Dashboard 不知该看什么、该做什么。缺乏引导导致用户快速流失。

**技术方案**:

- 采用 `react-joyride` 或 `intro.js` 实现步骤式引导
- 引导流程（5 步）：
  1. Dashboard 概览 — 健康分含义
  2. 主机列表 — 查看已监控服务器
  3. 告警中心 — 当前活跃告警
  4. AI 分析 — 点击告警查看 AI 根因分析
  5. 自动修复 — Runbook 审批与执行
- 后端新增 `user_preferences` 字段（或 localStorage），记录用户是否已完成引导
- 首次登录自动触发，可通过菜单「帮助 → 重新引导」再次触发

**工作量**: 前端 2-3 人天

**依赖**: 无

**验收标准**:
- 新用户首次登录自动弹出引导
- 引导覆盖核心功能路径
- 可跳过、可重新触发

---

### F3: HTML 元数据优化

**问题**: 前端 `<title>` 仅有中文，无 `<meta description>`、无 OG 标签。在社交平台分享链接时无预览信息，SEO 评分 3/10。

**技术方案**:

- 修改 `frontend/index.html`：
  - `<title>`: "VigilOps - AI-Powered Monitoring & Auto-Remediation"
  - `<meta name="description">`: 产品一句话描述
  - `<meta property="og:title/description/image">`: Open Graph 标签
  - `<meta name="twitter:card/title/description">`: Twitter Card
  - `<link rel="icon">`: favicon（当前可能缺失或默认）
- 为 Landing Page 添加结构化数据（JSON-LD）

**工作量**: 前端 0.5 人天

**依赖**: 需要 OG 图片素材（1200x630px）

**验收标准**:
- 在微信/Slack/Twitter 分享链接时显示预览卡片
- Google Lighthouse SEO 评分 > 80

---

### F4: 自定义 Runbook

**问题**: 当前仅有 6 个内置 Runbook（disk_cleanup / service_restart / memory_pressure / log_rotation / zombie_killer / connection_reset），用户无法针对自己的业务场景编写修复脚本。竞品中 PagerDuty 和 Datadog 均支持自定义工作流。

**技术方案**:

- **数据模型**: 新增 `custom_runbooks` 表
  ```
  id, name, description, trigger_keywords[], risk_level (auto/manual/critical),
  steps[{name, command, timeout_sec, rollback_command}],
  safety_checks[], created_by, is_active, created_at, updated_at
  ```
- **后端 API**: CRUD 端点 `/api/v1/runbooks/custom`
  - POST 创建、GET 列表、GET 详情、PUT 更新、DELETE 删除
  - 导入/导出功能（JSON 格式）
- **Runbook Registry 扩展**: 修改现有 `runbook_registry.py`，在加载内置 Runbook 后从数据库加载自定义 Runbook
- **安全控制**:
  - 命令白名单/黑名单机制（禁止 `rm -rf /`、`dd` 等危险命令）
  - 所有自定义 Runbook 默认 risk_level=manual（需人工审批）
  - 沙箱执行：timeout + 资源限制
- **前端**: 新增「Runbook 管理」页面
  - 列表视图：展示所有 Runbook（内置 + 自定义）
  - 编辑器：步骤式编排 UI，每步配置命令 + 超时 + 回滚
  - 测试运行：dry-run 模式（只显示将执行的命令，不实际执行）

**工作量**: 后端 5-7 人天 + 前端 4-5 人天

**依赖**: 现有 `remediation/` 模块的 Registry 模式和 CommandExecutor

**验收标准**:
- 用户可通过 UI 创建自定义 Runbook
- 自定义 Runbook 可被 AI 推荐和触发
- dry-run 模式正常工作
- 危险命令被安全机制拦截

---

### v0.9.2 里程碑总结

| 功能 | 工作量 | 负责角色 | 风险 |
|------|--------|---------|------|
| F1: Landing Page | 3-5 天 | 前端 + 创意 | 低 |
| F2: 新手引导 | 2-3 天 | 前端 | 低 |
| F3: HTML 元数据 | 0.5 天 | 前端 | 无 |
| F4: 自定义 Runbook | 9-12 天 | 后端 + 前端 | 中（安全控制） |
| **合计** | **15-21 天** | | |

**发布标准**: F1-F3 全部完成 + F4 基础功能可用（至少支持创建和手动执行）

---

## 三、v0.9.5 — 数据源扩展

**目标**: 接入 Prometheus 生态，补齐 PromQL 查询和容器监控两个最大功能 Gap。

### F5: Prometheus 数据源对接

**问题**: 大量中小团队已有 Prometheus 部署，不会因为 VigilOps 放弃已有监控数据。竞品夜莺以 Prometheus 适配器起家。当前代码中 `backend/app/routers/prometheus.py` 仅支持**导出**指标到 Prometheus 格式，不支持**读取** Prometheus 数据。

**技术方案**:

- **数据源管理**: 新增 `data_sources` 表
  ```
  id, name, type (prometheus/victoriametrics/thanos),
  url, auth_type (none/basic/bearer), credentials (encrypted),
  scrape_interval_sec, is_active, health_status, created_at
  ```
- **Prometheus Client**: 新增 `backend/app/services/prometheus_client.py`
  - 实现 Prometheus HTTP API 客户端（query、query_range、series、labels）
  - 连接池管理 + 超时控制 + 重试策略
  - 兼容 VictoriaMetrics / Thanos 的 API
- **API 端点**: `/api/v1/datasources`
  - CRUD 管理数据源
  - `/api/v1/datasources/{id}/test` 连通性测试
  - `/api/v1/datasources/{id}/query` 代理查询
- **Dashboard 集成**: 仪表盘组件支持选择数据源，Prometheus 指标可作为图表数据源
- **告警集成**: 告警规则支持基于 Prometheus 指标触发

**工作量**: 后端 7-10 人天 + 前端 3-5 人天

**依赖**: 无外部依赖

**验收标准**:
- 可添加 Prometheus 数据源并验证连通性
- Dashboard 图表可展示 Prometheus 指标数据
- 支持基于 Prometheus 指标的告警规则

---

### F6: PromQL / 自定义指标查询

**问题**: PromQL 是云原生监控的事实标准查询语言。VigilOps 当前仅支持预定义的系统指标（CPU / Memory / Disk / Network），无法查询自定义业务指标。这是竞品分析中标注的「最大功能缺失」。

**技术方案**:

- **方案选择**: 不自行实现 PromQL 解析器（工作量巨大），而是：
  - **外接模式**：通过 F5 的 Prometheus Client 将 PromQL 查询代理到用户已有的 Prometheus/VictoriaMetrics
  - **内置指标增强**：扩展 Agent 上报的自定义指标能力
- **自定义指标收集**: 扩展 Agent 配置
  ```yaml
  custom_metrics:
    - name: "app_request_count"
      type: "counter"
      command: "curl -s localhost:9090/metrics | grep app_request_count"
      interval: 30
    - name: "queue_depth"
      type: "gauge"
      command: "redis-cli llen job_queue"
      interval: 60
  ```
- **指标存储**: 新增 `custom_metrics` 表存储 Agent 上报的自定义指标
- **查询 API**: `/api/v1/metrics/query`
  - 支持简化的指标查询语法（时间范围 + 标签过滤 + 聚合函数）
  - 当配置了 Prometheus 数据源时，支持透传 PromQL
- **前端**: 指标浏览器组件
  - 指标名称自动补全
  - 时间范围选择器
  - 图表渲染（复用现有 ECharts 组件）

**工作量**: 后端 8-10 人天 + Agent 3-4 人天 + 前端 5-7 人天

**依赖**: F5（Prometheus 数据源对接）为前置依赖

**验收标准**:
- Agent 可上报自定义指标
- 通过 Prometheus 数据源执行 PromQL 查询
- 指标浏览器可展示内置 + 自定义 + Prometheus 指标
- 自定义指标可用于告警规则

---

### F7: 容器 / K8s 基础监控

**问题**: 中小团队越来越多使用容器化部署。当前 Agent 仅有 Docker 容器自动发现（`discovery.py`），但不收集容器级指标，更无 Kubernetes 支持。竞品中夜莺、Datadog 均提供完整容器监控。

**技术方案**:

- **Phase 1: Docker 容器指标（v0.9.5）**
  - 扩展 Agent `collector.py`，通过 Docker API 采集容器级指标：
    - CPU 使用率、内存使用/限制、网络 IO、块设备 IO
    - 容器状态（running/stopped/restarting）
    - 重启次数、运行时长
  - 新增 `container_metrics` 表和 API 端点
  - 前端新增「容器」页面：列表 + 详情 + 指标图表
  - 告警规则支持容器级指标（如：容器内存超过 limit 的 80%）

- **Phase 2: K8s 基础监控（v1.0）**
  - 新增 K8s Collector 模块，通过 Kubernetes API 采集：
    - Node 状态和资源使用
    - Pod 状态（Running/Pending/Failed/CrashLoopBackOff）
    - Deployment 副本数和健康状态
    - Service/Ingress 可用性
  - 前端新增 K8s 专用视图（集群概览 → Namespace → Workload → Pod）
  - 与 Prometheus 数据源联动（kube-state-metrics / cadvisor）

**工作量**:
- Phase 1（Docker）: 后端 4-5 天 + Agent 3-4 天 + 前端 3-4 天
- Phase 2（K8s）: 后端 6-8 天 + Agent 5-7 天 + 前端 5-7 天

**依赖**:
- Phase 1: 现有 Docker discovery 模块 (`agent/vigilops_agent/discovery.py`)
- Phase 2: 依赖 F5（Prometheus 对接），建议通过 Prometheus 采集 K8s 指标而非直接调用 K8s API

**验收标准**:
- Phase 1: Docker 容器指标实时展示、容器级告警可配置
- Phase 2: K8s 集群拓扑可视化、Pod 状态监控、关键事件告警

---

### v0.9.5 里程碑总结

| 功能 | 工作量 | 负责角色 | 风险 |
|------|--------|---------|------|
| F5: Prometheus 数据源 | 10-15 天 | 后端 + 前端 | 中（API 兼容性） |
| F6: PromQL/自定义指标 | 16-21 天 | 后端 + Agent + 前端 | 高（查询引擎复杂度） |
| F7: Docker 容器监控 | 10-13 天 | 全栈 + Agent | 中（指标采集稳定性） |
| **合计** | **36-49 天** | | |

**发布标准**: F5 + F6 基础功能 + F7 Phase 1（Docker）完成

**降级方案**: 若进度紧张，F6 可先只支持 Prometheus 代理查询模式，自定义指标收集推迟到 v1.0

---

## 四、v1.0 — 生产就绪

**目标**: 支持 K8s 部署和中型规模（>50 主机），达到生产级可靠性。

### F8: Helm Chart

**问题**: K8s 已成为中小团队的主流部署方式。当前仅支持 Docker Compose 部署，无法满足 K8s 用户的部署需求。竞品夜莺、Prometheus 均提供 Helm Chart。

**技术方案**:

- **Chart 结构**:
  ```
  charts/vigilops/
  ├── Chart.yaml
  ├── values.yaml
  ├── templates/
  │   ├── backend-deployment.yaml
  │   ├── backend-service.yaml
  │   ├── frontend-deployment.yaml
  │   ├── frontend-service.yaml
  │   ├── frontend-ingress.yaml
  │   ├── postgresql-statefulset.yaml  (或依赖 bitnami/postgresql)
  │   ├── redis-deployment.yaml        (或依赖 bitnami/redis)
  │   ├── agent-daemonset.yaml         (每个 Node 运行一个 Agent)
  │   ├── configmap.yaml
  │   ├── secret.yaml
  │   ├── serviceaccount.yaml
  │   ├── hpa.yaml                     (可选: 自动扩缩)
  │   └── _helpers.tpl
  └── README.md
  ```
- **关键设计决策**:
  - PostgreSQL 和 Redis 默认使用 Bitnami subchart（可外接已有实例）
  - Agent 以 DaemonSet 部署，自动在每个 Node 运行
  - Backend 支持多副本 + HPA
  - Ingress 支持 nginx/traefik
  - values.yaml 提供完整的配置覆盖能力
- **CI 集成**: GitHub Actions 自动化 Chart 打包 + 发布到 GitHub Pages（作为 Helm repo）
- **文档**: 提供 Quick Start + 生产配置指南

**工作量**: DevOps 7-10 人天

**依赖**: 后端需支持多副本部署（见 F9 水平扩展）

**验收标准**:
- `helm install vigilops ./charts/vigilops` 一键部署成功
- 支持通过 values.yaml 自定义所有关键配置
- Chart 通过 `helm lint` 和 `helm test` 验证
- Agent DaemonSet 自动注册到 Backend

---

### F9: 支持 >50 主机（水平扩展）

**问题**: 当前架构限制在 <50 台主机。单 PostgreSQL + 单 Backend 实例是瓶颈。数据库连接池 20+10=30 连接，asyncio.Queue 内存队列无持久化。

**技术方案**:

- **数据库优化**:
  - 指标表（host_metrics / db_metrics / container_metrics）按时间分区（月分区）
  - 冷数据自动归档：30 天前的分钟级数据聚合为小时级
  - 连接池扩大到 50 core + 20 overflow
  - 读写分离准备（预留配置，暂不强制要求 replica）

- **Backend 多实例**:
  - 会话状态移至 Redis（当前已使用 Redis，需确认 WebSocket 会话处理）
  - WebSocket 广播通过 Redis Pub/Sub 实现跨实例同步
  - 背景任务使用 Redis 分布式锁（避免多实例重复执行告警检查、清理任务）
  - 健康检查端点（/health + /ready）用于 K8s 探针

- **Agent 端优化**:
  - 批量上报模式：累积 N 条指标后一次性上报（减少 HTTP 连接数）
  - 上报重试 + 本地缓冲（Backend 不可达时不丢数据）
  - Agent 端预聚合（1 分钟内的 CPU 采样取平均值后上报）

- **性能基准**:
  - 目标：支持 200 台主机、1000 个服务、50 条告警规则
  - 指标写入：> 5000 points/sec
  - Dashboard 查询响应：< 500ms（P95）
  - 告警评估延迟：< 120s

**工作量**: 后端 10-15 人天 + Agent 3-5 人天

**依赖**: F8（Helm Chart 用于多实例部署验证）

**验收标准**:
- 压测通过 200 主机并发上报
- Backend 2 副本无状态冲突
- 历史数据自动归档、查询性能不降级
- 告警不漏报、不重复触发

---

### F7-Phase2: K8s 监控（续）

（详见 F7 Phase 2 描述，在 v1.0 阶段交付）

---

### v1.0 里程碑总结

| 功能 | 工作量 | 负责角色 | 风险 |
|------|--------|---------|------|
| F8: Helm Chart | 7-10 天 | DevOps | 低 |
| F9: 水平扩展 | 13-20 天 | 后端 + Agent | 高（分布式状态） |
| F7-P2: K8s 监控 | 16-22 天 | 全栈 + Agent | 中 |
| **合计** | **36-52 天** | | |

**发布标准**: F8 + F9 完成 + F7 Phase 2 基础功能可用

---

## 五、功能依赖关系

```
v0.9.2                    v0.9.5                       v1.0
───────                   ──────                       ────

F3: HTML 元数据 ──────────────────────────────────────────→
      (无依赖)

F1: Landing Page ─────────────────────────────────────────→
      (无依赖)

F2: 新手引导 ─────────────────────────────────────────────→
      (无依赖)

F4: 自定义 Runbook ──→ (AI 推荐自定义 Runbook)
      (依赖: runbook_registry.py)

                      F5: Prometheus 数据源 ──→ F8: Helm Chart
                            │                        │
                            ↓                        ↓
                      F6: PromQL/自定义指标    F9: 水平扩展
                            │
                            ↓
                      F7-P1: Docker 监控 ──→ F7-P2: K8s 监控
```

**关键路径**: F5 → F6 → F7（数据源扩展链路）

**并行机会**:
- F1/F2/F3 可与 F4 并行开发
- F8 可与 F5/F6 并行开发
- F9 的数据库分区优化可提前启动

---

## 六、优先级排序理由

### 为什么 Demo 体验优先于功能扩展？

1. **当前获客漏斗严重泄漏**: 增长审计显示 Demo 体验 5/10，直接跳登录页。每一个到达 Demo 的用户都在第一步流失
2. **成本最低**: Landing Page + 引导 + 元数据总共不到 1 周前端工作量
3. **乘数效应**: 增长策略中已有 8 篇博客待发布、GitHub 优化待执行，但没有好的转化落地页，所有流量都被浪费

### 为什么 Prometheus 对接优先于 K8s 监控？

1. **用户已有数据**: Prometheus 是已有用户最不愿放弃的资产。提供对接能力意味着「零成本迁移」
2. **实现 PromQL 的捷径**: 自行实现 PromQL 解析器需要数月，代理模式只需要 HTTP Client
3. **K8s 监控可借力**: 完成 Prometheus 对接后，K8s 监控可通过 kube-state-metrics + cadvisor 的 Prometheus 指标实现，大幅降低开发量

### 为什么自定义 Runbook 在 v0.9.2？

1. **增强核心差异化**: 自动修复是 VigilOps 的三大差异化之一，但 6 个内置 Runbook 覆盖面有限
2. **用户粘性**: 自定义 Runbook 是用户投入的「沉没成本」，提高留存
3. **社区价值**: 为未来的 Runbook 市场/分享功能打基础

### 为什么水平扩展在最后？

1. **当前用户规模不需要**: <50 主机对早期项目足够
2. **技术风险最高**: 分布式状态管理是最复杂的工程挑战
3. **前置条件多**: 需要 Helm Chart 支持多副本部署验证

---

## 七、风险评估与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| PromQL 查询性能瓶颈 | 用户体验差 | 中 | 代理模式依赖 Prometheus 本身的性能；添加查询缓存 |
| K8s 监控复杂度超预期 | 延期 | 高 | Phase 2 优先使用 Prometheus 数据源而非直接 K8s API |
| 自定义 Runbook 安全漏洞 | 生产事故 | 中 | 命令黑名单 + 强制审批 + 沙箱执行 + dry-run 测试 |
| 水平扩展分布式锁问题 | 数据不一致 | 中 | 使用 Redis Redlock 算法；关键路径保持单 writer |
| Helm Chart 兼容性 | 部署失败 | 低 | CI 中测试多个 K8s 版本（1.26-1.30） |
| 前端 Bundle 膨胀 | 加载慢 | 中 | Landing Page 做代码分割，lazy load 非首屏组件 |

---

## 八、成功指标

### v0.9.2
- Demo 站 Landing → 注册转化率 > 15%
- 新用户完成引导流程比例 > 60%
- 社交平台分享链接有预览卡片

### v0.9.5
- 至少 1 个 Prometheus 数据源成功对接
- 自定义指标查询响应 < 1s
- Docker 容器级告警可配置

### v1.0
- Helm 安装 < 10 分钟一键部署
- 200 主机压测通过（P95 查询 < 500ms）
- K8s Pod 状态监控覆盖

---

## 九、v1.0 后展望（P3 长期）

以下功能不在 v1.0 范围内，但已纳入长期规划：

| 功能 | 价值 | 前置条件 |
|------|------|----------|
| 异常检测 ML 模型 | 从规则告警升级到智能检测 | 足够的历史指标数据 |
| OpenTelemetry 支持 | APM/链路追踪，进入可观测性赛道 | Prometheus 对接完成 |
| 多 LLM 支持 | OpenAI / Claude / 本地模型 | AI 引擎抽象层 |
| 独立官网 (vigilops.io) | 品牌建设 + SEO | Landing Page 验证 |
| Design System 标准化 | 一致的 UI 体验 | UI 审计修复完成 |
| Runbook 市场 | 社区分享修复脚本 | 自定义 Runbook + 用户基数 |
| 多租户 | SaaS 化商业模式 | 水平扩展 + 认证体系增强 |

---

*本路线图将根据 Phase 3 执行进展和用户反馈持续更新。*
