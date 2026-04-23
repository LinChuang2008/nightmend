# PromQL 引擎升级计划 (PromQL Engine Upgrade Plan)

> **Status**: 🟡 Draft — 待战略方向对齐后再定 Sprint
> **Owner**: backend team
> **Base commit**: `e7aa886`
> **Created**: 2026-04-23

---

## 0. ⚠️ 先对齐的战略冲突

`docs/roadmap-v1.0.md:200-207`（F6 章节）明确决策：

> **方案选择**：不自行实现 PromQL 解析器（工作量巨大），而是：
> **外接模式**：通过 F5 的 Prometheus Client 将 PromQL 查询代理到用户已有的 Prometheus/VictoriaMetrics

**但代码现状已偏离此决策**：`backend/app/services/promql_service.py` 已自研 901 行 PromQL 引擎。

### 三条路线候选

| 路线 | 抓手 | 代价 | 风险 |
|---|---|---|---|
| **A. 继续自研** | 把兼容度从 40% 拉到 75% | 6 个 Sprint 工程投入 | 违背 roadmap F6 决策；重复造轮子 |
| **B. 回归 roadmap F6**（代理模式） | 删自研引擎 → 调外部 Prometheus HTTP API | 10-15 天 | 现有 8 个内置指标迁移成本；强依赖用户自建 Prom |
| **C. 双轨并存** | 内置指标走自研，自定义指标走代理 | A+B 总和 | 维护两套，心智负担高 |

**⚠️ 本文档第 2-6 章默认按路线 A 展开。** 评审会上若拍板 B/C，本文需重写或作废。

---

## 1. 现状盘点（Baseline）

### 1.1 覆盖范围

| 维度 | 现状 | 证据 |
|---|---|---|
| HTTP 端点 | `/query`、`/query_range`、`/metadata` | `backend/app/routers/promql.py` |
| 解析器 | 正则分层（非 AST） | `backend/app/services/promql_service.py:216` |
| 指标白名单 | 硬编码 8 个 | `promql_service.py:38-47` |
| 聚合函数 | `sum/avg/min/max/count` | 共 5 个 |
| Range 函数 | `rate/increase/avg_over_time/max_over_time/min_over_time` | 共 5 个 |
| 标签匹配 | `= != =~ !~` | 全支持 |
| Duration 单位 | `s/m/h/d/w` | 缺 `ms/y` |
| 算术 | `expr OP scalar`（一元） | 不支持向量-向量 |
| 测试覆盖率 | **0%**（无专项测试） | `backend/tests/` 无 `test_promql*` |

### 1.2 关键缺口

| 类别 | 缺失项 | Grafana 阻塞度 |
|---|---|---|
| 算子 | 比较运算 (`> < >= <=`)、逻辑 (`and/or/unless`)、一元数学 (`abs/ceil/sqrt/ln`) | 🔴 高 |
| 聚合 | `stddev/stdvar/topk/bottomk/quantile/group` | 🟡 中 |
| Range 函数 | `irate/delta/deriv/resets/changes/sum_over_time/quantile_over_time/predict_linear` | 🔴 高 |
| 运算 | **向量-向量四则运算**、`on()/ignoring()/group_left/group_right` | 🔴 致命 |
| Metadata API | `/labels`、`/label/<name>/values`、`/series` | 🟡 中 |
| 指标发现 | 白名单硬编码，无法自动暴露 `HostMetric` 22 个字段 | 🟡 中 |
| Histogram | 无存储、无 `histogram_quantile` | 🟡 中 |
| 高级语法 | Subquery `[5m:1m]`、`@` 修饰符、`offset` | 🟢 低 |

---

## 2. 目标（KR 对齐，仅路线 A 适用）

| KR | 基线 | 2 Sprint | 6 Sprint |
|---|---|---|---|
| PromQL 语法覆盖率 | 40% | 60% | 75% |
| Grafana Node Exporter dashboard 可跑率 | 0% | 50% | 85% |
| 指标白名单可动态扩展 | ❌ | ✅ 反射 22 个字段 | ✅ 自定义 labels |
| 测试覆盖率（`app.promql`） | 0% | 70% | 85% |

---

## 3. Sprint 计划（6 Sprint，颗粒度到单 Task）

### Sprint 1：打地基 — 测试基线 + AST 解析器重构 🔴 阻塞项

**底层逻辑**：正则分层解析无法支撑嵌套表达式（如 `sum(rate(a[5m])) / sum(rate(b[5m]))`）。必须先换 AST，否则技术债滚雪球。

| # | Task | 产出 | 验收 |
|---|---|---|---|
| 1.1 | 新建 `backend/tests/test_promql_parser.py` | 冻结当前行为 ≥40 case | 全绿 |
| 1.2 | 新建 `backend/tests/test_promql_engine.py` | 端到端 ≥20 case | 全绿 |
| 1.3 | 引入 AST 节点模块 `app/promql/ast.py` | `NumberLiteral/VectorSelector/MatrixSelector/BinaryOp/AggregateExpr/Call` | 旧测试绿 |
| 1.4 | Tokenizer + Pratt parser | `app/promql/lexer.py` + `app/promql/parser.py` | 支持嵌套 |
| 1.5 | Evaluator visitor 模式 | `app/promql/evaluator.py` | 旧 API adapter |

**关键约束**：1.1 + 1.2 先写（TDD RED），再做 1.3-1.5 重构，避免回归。

### Sprint 2：指标白名单动态化 + Metadata API 对齐

| # | Task | 产出 | 验收 |
|---|---|---|---|
| 2.1 | `metric_registry` DB 表 + alembic migration | schema + seed | migration 成功 |
| 2.2 | `HostMetric` 22 字段自动反射 | `app/promql/metric_registry.py` | 新列自动暴露 |
| 2.3 | `/api/v1/label/__name__/values` | 返回所有指标名 | Grafana autocomplete 通 |
| 2.4 | `/api/v1/label/<label>/values` | 返回 label 取值 | 同上 |
| 2.5 | `/api/v1/series` | 返回 series 元数据 | Grafana Explore 通 |
| 2.6 | `/metadata` 改标准 schema | `{metric: [{type, help, unit}]}` | prom client lib 解析 OK |

**闭环验收**：本地起 Grafana 加 Prometheus data source，Explore 面板 metric 下拉可见完整列表。

### Sprint 3：算子补齐（一元数学 + 比较 + 逻辑）

| # | Task | 算子 | Case 数 |
|---|---|---|---|
| 3.1 | 一元数学 | `abs/ceil/floor/round/sqrt/exp/ln/log2/log10` | 9 × 3 |
| 3.2 | 比较运算 | `> < >= <= == !=` + `bool` 修饰符 | 6 × 4 |
| 3.3 | 逻辑集合 | `and / or / unless` | 3 × 3 |
| 3.4 | 额外聚合 | `stddev/stdvar/topk/bottomk/quantile/group` | 6 × 2 |
| 3.5 | Duration 扩展 | `ms/y` 单位 | 2 |

### Sprint 4：Range 函数大补丁 + Subquery

| # | Task | 能力 |
|---|---|---|
| 4.1 | Range 函数扩容 | `irate/delta/deriv/resets/changes/sum_over_time/count_over_time/stddev_over_time/quantile_over_time`（9 个） |
| 4.2 | 预测函数 | `predict_linear/holt_winters` |
| 4.3 | Subquery `expr[5m:1m]` | 语法 + 执行（依赖 Sprint 1 AST） |
| 4.4 | `@` 修饰符 + `offset` | 时间锚点 |

### Sprint 5：向量 vs 向量算术 + vector matching 🔥

| # | Task | 能力 | 难度 |
|---|---|---|---|
| 5.1 | 向量-向量四则运算 | 默认 1:1 label match | ⭐⭐⭐ |
| 5.2 | `on(labels)` / `ignoring(labels)` | 指定 matching labels | ⭐⭐⭐ |
| 5.3 | `group_left / group_right` | 多对一 / 一对多 | ⭐⭐⭐⭐ |
| 5.4 | 向量-向量比较 + 逻辑 | `a > b`、`a and b` | ⭐⭐ |

### Sprint 6：Histogram + Recording rules 子集（可选）

| # | Task | 说明 |
|---|---|---|
| 6.1 | `host_metric_histogram` 表 | buckets 存储 |
| 6.2 | `histogram_quantile()` | 经典函数 |
| 6.3 | Exporter histogram 类型 | `_bucket / _sum / _count` |
| 6.4 | 轻量 recording rules | DB 表 + 定时调度 |
| ~~6.5~~ | ~~Alerting rules evaluator~~ | **跳过**：与产品定位冲突（由 AlertManager 推进来） |

---

## 4. Definition of Done（每 Sprint 必备）

1. ✅ TDD 闭环：RED → GREEN → REFACTOR 三段齐全
2. ✅ `pytest --cov=app.promql --cov-report=term-missing` ≥ 80%
3. ✅ Grafana 冒烟：本地起 Grafana + Node Exporter dashboard 截图对比
4. ✅ 兼容性测试：取 Prometheus 官方 `promql/testdata/*.test` 子集全绿
5. ✅ Code Review：`code-reviewer` + `python-reviewer` 双审

---

## 5. 风险与降级

| 风险 | 影响 | 降级预案 |
|---|---|---|
| AST 重构周期过长 | Sprint 1 滑点 → 后续全线延期 | 1.1/1.2 先绿，1.3-1.5 灰度独立上线 |
| Vector matching 性能差 | query_range 超时 | 新增 `max_series` 限制（类比 `max_steps=11000`） |
| Histogram 存储膨胀 | DB 压力 | Sprint 6 延期或改 ClickHouse 侧写 |
| 战略方向改判 B/C | 本计划 3-6 章作废 | 保留第 1 章 baseline 作为路线 B 迁移的输入 |

---

## 6. 下一步（P0 本周）

1. **先开评审会拍板路线 A/B/C**（阻塞项）
2. 若选 A：
   - 同步更新 `docs/roadmap-v1.0.md` F6 章节（从"不自研"改为"自研已完成，进入增强阶段"）
   - 新建分支 `feat/promql-v2`
   - 写 Sprint 1.1 + 1.2 测试骨架（先 RED，不实现）
   - 本地 Grafana 兼容性 baseline 截图
3. 若选 B/C：本文档重写

---

## 7. 附录：当前可用指标清单

```
nightmend_host_cpu_percent
nightmend_host_memory_percent
nightmend_host_disk_percent
nightmend_host_cpu_load_1m
nightmend_host_cpu_load_5m
nightmend_host_cpu_load_15m
nightmend_host_network_bytes_sent_total
nightmend_host_network_bytes_received_total
```

**可反射但未暴露的 `HostMetric` 字段（Sprint 2 目标）**：
`memory_used_mb / disk_used_mb / disk_total_mb / net_send_rate_kb / net_recv_rate_kb / net_packet_loss_rate / agent_cpu_percent / agent_memory_rss_mb / agent_thread_count / agent_uptime_seconds / agent_open_files`（共 11 个）

---

## 8. 附录：PromQL 兼容度矩阵（快照）

### 8.1 Exporter 协议 — 约 85%
- ✅ OpenMetrics/Text 格式、Counter/Gauge、双通道认证
- ❌ Histogram/Summary、Exemplars、时间戳列

### 8.2 PromQL HTTP API — 约 40%
- ✅ `/query`、`/query_range`（限流 11000 steps）
- ⚠️ `/metadata`（非标准 schema）
- ❌ `/labels`、`/label/<name>/values`、`/series`、`/targets`、`/rules`、`/alerts`

### 8.3 AlertManager Webhook 入站 — 约 95%
- ✅ status/labels/annotations/startsAt/endsAt、Redis 去重、Bearer 认证、instance→Host 三级映射
- ⚠️ groupLabels/commonLabels/externalURL/receiver 未消费但不报错

### 8.4 原生 Prometheus server 能力 — 不适用
- ❌ TSDB、Recording rules、Service discovery、Scrape 调度、Remote write/read、Federation
- 📌 **不做**：违背 facade 定位
