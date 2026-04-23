# PromQL 引擎升级计划 (PromQL Engine Upgrade Plan)

> **Status**: 🟢 路线 D 锁定，POC 全绿 — 待评审后开工
> **Owner**: backend team
> **Base commit**: `b2eb0bc`
> **Created**: 2026-04-23
> **Strategy**: 路线 D — 开源 parser（`promql-parser`）+ 自研 evaluator

---

## 0. 战略定调

**底层逻辑**：PromQL 语言层（parser/AST）是通用的，用开源；数据执行层（evaluator）对接自研 PostgreSQL `HostMetric`，必须自研。这是 facade 模式的标准分工。

### 路线对比（已决策）

| 路线 | 决策 | 备注 |
|---|---|---|
| A. 全自研 | ❌ 放弃 | 重复造轮子，维护成本高 |
| B. 外接代理 | ❌ 放弃 | 强依赖用户自建 Prometheus，不符合"自研"意愿 |
| C. 双轨并存 | ❌ 放弃 | 维护两套路径，心智负担高 |
| **D. parser 开源 + evaluator 自研** | **✅ 采纳** | 语法 100% 跟 Prom 官方对齐，只需专注数据侧 |

### 与 `docs/roadmap-v1.0.md:200-207` F6 章节的关系

F6 原文"不自行实现 PromQL 解析器"——**路线 D 与此决策一致**（parser 不自研），但补上 F6 未覆盖的问题：**evaluator 如何对接 NightMend 内置 `HostMetric` 数据源**（F6 假设走外部 Prometheus 代理，但代码已经建了自研数据路径）。

**Action**：本计划通过后，同步更新 `roadmap-v1.0.md` F6 章节，把"查询引擎"拆成"Parser = 开源 / Evaluator = 自研"两段描述。

---

## 1. POC 验证（已通过）

### 1.1 选型证据

| 项 | 结论 |
|---|---|
| 选型 | `promql-parser` 0.8.0（PyPI, 2026-04-06 发布） |
| 实现 | Rust + pyo3 binding（messense/py-promql-parser） |
| License | MIT |
| Prom 版本对齐 | v2.45.0 |
| Python 支持 | 3.8 ~ 3.14，含 PyPy |
| 平台 wheel | manylinux x86_64/aarch64、macOS ARM64/x86_64 全覆盖 |
| 包体积 | 1.4 MB（cp312 manylinux wheel） |

### 1.2 POC 测试结果

在本地 venv (`/tmp/promql_poc/`) 跑 33 个表达式，**全部通过**：

| 类别 | 测试 case 数 | 通过 |
|---|---|---|
| 现有引擎已支持（baseline） | 18 | 18 ✅ |
| Sprint 3-5 规划要补的语法 | 12 | 12 ✅ |
| Grafana 实战表达式（含 `node_cpu_seconds_total`） | 3 | 3 ✅ |
| **合计** | **33** | **33 ✅** |

AST 节点类型：`VectorSelector / MatrixSelector / Call / AggregateExpr / BinaryExpr` — 结构清晰、属性齐全，满足 evaluator 所需：

```
BinaryExpr      .op .lhs .rhs .modifier(.card .matching .return_bool)
VectorSelector  .name .matchers(.matchers[] with MatchOp enum) .offset .at
MatrixSelector  .vs .range
AggregateExpr   .op .expr .param .modifier
Call            .func .args
```

**POC 硬证据**：当前引擎崩溃的嵌套 `sum(rate(...)) / sum(rate(...))` parser 正确解析为 `BinaryExpr`；`histogram_quantile`、`offset`、`@`、subquery `[5m:1m]`、`ms/y` duration **全部开箱可用**。

---

## 2. 现状盘点（Baseline）

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

---

## 3. 目标（KR 对齐）

| KR | 基线 | Sprint 2 后 | Sprint 4 后 |
|---|---|---|---|
| PromQL 语法覆盖率（parser + evaluator 双通道） | 40% | 70% | **90%+** |
| Grafana Node Exporter dashboard 可跑率 | 0% | 60% | 90% |
| 指标白名单可动态扩展 | ❌ 硬编码 8 个 | ✅ 反射 22 个字段 | ✅ 自定义 labels |
| 测试覆盖率（`app.promql`） | 0% | 75% | 85% |
| Prometheus 版本对齐 | ❌ 手工跟进 | ✅ 随 `promql-parser` 版本升级 | ✅ |

---

## 4. Sprint 计划（4 Sprint，颗粒度到单 Task）

### Sprint 1：接入 parser + 测试基线 + 旧路径适配

**底层逻辑**：先冻结行为（测试），再引 parser，再做 AST → 旧 SQL 路径的 adapter，确保零行为变化上线。

| # | Task | 产出 | 验收 |
|---|---|---|---|
| 1.1 | 新建 `backend/tests/test_promql_parser.py` | 冻结当前行为 ≥40 case（走旧 `parse_promql` 函数） | 全绿 |
| 1.2 | 新建 `backend/tests/test_promql_engine.py` | 端到端 ≥20 case（走 `execute_instant_query/execute_range_query`） | 全绿 |
| 1.3 | `requirements.txt` 加 `promql-parser==0.8.0`；Dockerfile 验证 | `pip install` + 容器启动成功 | backend 镜像构建 OK |
| 1.4 | 新建 `backend/app/promql/ast_adapter.py` | `promql_parser.parse(expr)` → 现有 `ParsedQuery` 的适配器 | 1.1/1.2 测试继续全绿 |
| 1.5 | `promql_service.py` 的 `parse_promql` 替换为调用 adapter | 保留旧 `ParsedQuery` 接口 | 测试全绿 |
| 1.6 | 旧正则解析器代码移除 | 删 `_VECTOR_SELECTOR_RE/_AGGREGATION_RE/_RANGE_FUNC_RE/_ARITH_RE` 及相关函数 | 行数 901 → ≈600 |

**关键约束**：1.1 + 1.2 先写（TDD RED），再做 1.3-1.6 重构。

### Sprint 2：Evaluator visitor 重写 + 指标白名单动态化 + Metadata API

**底层逻辑**：Sprint 1 只做 adapter，现在推掉 adapter 这层中间态，改成 AST visitor 直出 SQLAlchemy。

| # | Task | 产出 | 验收 |
|---|---|---|---|
| 2.1 | 新建 `backend/app/promql/evaluator.py`（AST visitor） | `visit_VectorSelector/visit_Call/visit_AggregateExpr/visit_BinaryExpr` 五大节点 | Sprint 1 测试全绿 |
| 2.2 | `execute_instant_query/execute_range_query` 改用 evaluator | 删除 `ast_adapter.py` | 行数进一步下降 |
| 2.3 | `metric_registry` DB 表 + alembic migration | schema + seed 22 个 `HostMetric` 字段 | migration 成功 |
| 2.4 | `HostMetric` 22 字段自动反射 | `app/promql/metric_registry.py` | 新列自动暴露 |
| 2.5 | `/api/v1/label/__name__/values` | 返回所有指标名 | Grafana autocomplete 通 |
| 2.6 | `/api/v1/label/<label>/values` | 返回 label 取值 | 同上 |
| 2.7 | `/api/v1/series` | 返回 series 元数据 | Grafana Explore 通 |
| 2.8 | `/metadata` 改标准 schema | `{metric: [{type, help, unit}]}` | prom client lib 解析 OK |

**闭环验收**：本地起 Grafana 加 Prometheus data source，Explore 面板 metric 下拉可见全部 22 指标。

### Sprint 3：Evaluator 算子补齐

**注意**：parser 已全部支持，本 Sprint 纯补 evaluator 分支。

| # | Task | 新增 evaluator 支持 | Case 数 |
|---|---|---|---|
| 3.1 | 一元数学 | `abs/ceil/floor/round/sqrt/exp/ln/log2/log10` | 9 × 3 |
| 3.2 | 比较运算 | `> < >= <= == !=` + `bool` 修饰符 | 6 × 4 |
| 3.3 | 逻辑集合 | `and / or / unless` | 3 × 3 |
| 3.4 | 额外聚合 | `stddev/stdvar/topk/bottomk/quantile/group` | 6 × 2 |
| 3.5 | Range 函数扩容 | `irate/delta/deriv/resets/changes/sum_over_time/count_over_time/stddev_over_time/quantile_over_time` | 9 × 2 |
| 3.6 | 预测函数 | `predict_linear/holt_winters` | 2 × 2 |
| 3.7 | Duration `ms/y`、offset、`@` 修饰符 | evaluator 侧支持时间偏移 | 3 × 2 |

### Sprint 4：向量-向量算术 + vector matching + Histogram 🔥

| # | Task | 能力 | 难度 |
|---|---|---|---|
| 4.1 | 向量-向量四则运算 | 默认 1:1 label match | ⭐⭐⭐ |
| 4.2 | `on(labels)` / `ignoring(labels)` | 指定 matching labels | ⭐⭐⭐ |
| 4.3 | `group_left / group_right` | 多对一 / 一对多 | ⭐⭐⭐⭐ |
| 4.4 | 向量-向量比较 + 逻辑 | `a > b`、`a and b` | ⭐⭐ |
| 4.5 | Subquery `expr[5m:1m]` 执行 | evaluator 支持嵌套时间窗 | ⭐⭐⭐ |
| 4.6（可选） | Histogram 存储 + `histogram_quantile()` | `host_metric_histogram` 表 + `_bucket/_sum/_count` exporter | ⭐⭐⭐ |

---

## 5. Definition of Done（每 Sprint 必备）

1. ✅ TDD 闭环：RED → GREEN → REFACTOR 三段齐全
2. ✅ `pytest --cov=app.promql --cov-report=term-missing` ≥ 80%
3. ✅ Grafana 冒烟：本地起 Grafana + Node Exporter dashboard 截图对比
4. ✅ 代码行数不膨胀：当前 901 行 → Sprint 1 结束 ≤ 600 → Sprint 4 结束目标 ≤ 800（语义覆盖翻倍但代码减少）
5. ✅ Code Review：`code-reviewer` + `python-reviewer` 双审

---

## 6. 风险与降级

| 风险 | 影响 | 降级预案 |
|---|---|---|
| `promql-parser` 版本锁死与 Prometheus 新特性脱钩 | 语法滞后 | 定期 `pip install -U`；CI 加兼容性冒烟 |
| AST visitor 性能差（每请求 parse） | QPS 下降 | 加 LRU cache 缓存 `parse(expr)` 结果 |
| Vector matching 算法 O(n²) | query_range 超时 | 新增 `max_series` 限制（类比现有 `max_steps=11000`）；label set hashing O(n) |
| Rust wheel 对接特殊 CPU 架构缺失 | 部署阻塞 | 已验证 manylinux x86_64/aarch64 + macOS 全覆盖，无风险；若有 s390x/ppc64le 特殊需求再评估 |
| Histogram 存储膨胀 | DB 压力 | Sprint 4.6 可延期或改 ClickHouse 侧写 |

---

## 7. 下一步（P0 本周）

1. **评审拍板本计划**（30 分钟会议即可）
2. 通过后：
   - 同步更新 `docs/roadmap-v1.0.md` F6 章节（parser 开源 + evaluator 自研的新口径）
   - 新建分支 `feat/promql-v2`
   - 执行 Sprint 1.1 + 1.2（先 RED，不实现）
   - 本地 Grafana 兼容性 baseline 截图，留作前后对比

---

## 8. 附录：当前可用指标清单

### 8.1 已暴露指标（exporter `/api/v1/metrics`）

```
nightmend_host_cpu_percent
nightmend_host_memory_percent
nightmend_host_disk_percent
nightmend_host_cpu_load_1m / 5m / 15m
nightmend_host_network_bytes_sent_total / received_total
nightmend_alerts_total / alerts_by_severity
nightmend_hosts_total / hosts_by_status
nightmend_services_total / service_up / service_response_time_seconds
nightmend_up / nightmend_last_scrape_timestamp_ms
```

### 8.2 可反射但未暴露的 `HostMetric` 字段（Sprint 2 目标）

```
memory_used_mb / disk_used_mb / disk_total_mb
net_send_rate_kb / net_recv_rate_kb / net_packet_loss_rate
agent_cpu_percent / agent_memory_rss_mb / agent_thread_count
agent_uptime_seconds / agent_open_files
```
（共 11 个字段）

---

## 9. 附录：POC 脚本与运行记录

POC 脚本位于 `/tmp/promql_poc/poc.py`（临时，不入库），运行命令：

```bash
python3.12 -m venv /tmp/promql_poc/venv
/tmp/promql_poc/venv/bin/pip install promql-parser==0.8.0
/tmp/promql_poc/venv/bin/python /tmp/promql_poc/poc.py
```

输出摘要：`Passed: 33/33    Failed: 0`

AST 探查样本：

```
Input:  sum by(hostname)(rate(nightmend_host_network_bytes_sent_total[5m]))
Type:   AggregateExpr
Output: sum by (hostname) (rate(nightmend_host_network_bytes_sent_total[5m]))
```

---

## 10. 附录：PromQL 兼容度矩阵

| 子协议 | 基线 | Sprint 4 目标 |
|---|---|---|
| Exporter 协议（`/metrics`） | 85% | 90%（补 histogram/summary） |
| PromQL HTTP API | 40% | 95%（补 labels/series/label values） |
| PromQL 语言 parser | N/A（自研 ~40%） | **100%（promql-parser 对齐 Prom v2.45）** |
| PromQL 语言 evaluator | 40% | 85%+ |
| AlertManager Webhook 入站 | 95% | 95%（已够用，不在本计划） |
| 原生 Prometheus server 能力 | 不适用 | 不做（违背 facade 定位） |
