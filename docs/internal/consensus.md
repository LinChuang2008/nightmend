# VigilOps Consensus

## Last Updated
2026-02-26 22:17

## Current Phase
🎉 **项目完成！** — 所有 P0/P1/P2 任务已完成，Engram 升级已完成，代码已推送远程

## 记忆系统
- **API**: `http://localhost:8002`
- **Namespace**: `vigilops`
- 所有运营循环：开始 recall → 结束 store

---

## CTO 全面评估（2026-02-25）
- **总代码**: 2.5 万行，133 文件
- **综合评分**: 7.2/10
- **亮点**: AI 分析 8/10, 自动修复 8/10, Dashboard/WS 8/10, 通知系统 8/10
- **短板**: 错误处理薄弱, 日志存 PG 不可扩展, API 无限流, 数据无保留策略
- **战略**: 把 AI 做深不做广，先还技术债再推广

## 已完成 Cycle

| Cycle | 内容 | 状态 |
|-------|------|------|
| 1-3 | 核心监控 + AI 分析 | ✅ |
| 4 | 自动修复系统 | ✅ |
| 5 | Dashboard WebSocket + 健康评分 + 拓扑图 | ✅ |
| 5.5 | ECS 部署 | ✅ |
| 6 | AI 记忆增强（Engram 集成） | ✅ |
| 7 | GitHub 开源运营物料 | ✅ |
| 8 | 多服务器拓扑（分层钻取） | ✅ |
| 9 (部分) | Agent 安装脚本、客户文档、CI/CD、获客文章 9 篇 | ✅ |

---

## 🔴 P0 必须做（当前执行中）

| # | 任务 | 工作量 | 状态 |
|---|------|--------|------|
| 1 | 全局错误处理中间件 | 0.5天 | ✅ commit 3974010 |
| 2 | JWT 密钥安全加固 | 0.5天 | ✅ commit 3974010 |
| 3 | 备份/恢复脚本 | 0.5天 | ✅ commit 3974010 |
| 4 | API 限流 + 安全加固 | 1天 | ✅ commit d14338a |
| 5 | 监控数据保留策略（自动清理旧数据） | 1天 | ✅ commit c711a39 |
| 6 | 告警去重/聚合 | 1天 | ✅ commit 6b5852e |
| 7 | MCP Server 接入（FastMCP，暴露核心运维工具给 AI Agent） | 0.5天 | ✅ commit 1a67479 |

## 🟡 P1 应该做（P0 完成后）

| # | 任务 |
|---|------|
| 1 | NotificationLogs 完善（当前仅 57 行半成品） | ✅ commit 277a227 |
| 2 | 告警升级 + 值班排期 | ✅ commit 66daf80 |
| 3 | Dashboard 可定制 | ✅ commit d39209c |
| 4 | AI 反馈闭环 | ✅ commit 0a618fc |
| 5 | 暗色主题 | ✅ commit 5208433 |
| 6 | HTTPS 支持 | ✅ commit f128ef2 |
| 7 | 前端空状态/错误状态优化 | ✅ commit 0eb6911 |
| 8 | Login 页面美化 | ✅ commit dfc9653 |

## ⚡ 董事长指令（CEO 每轮必读，优先级高于默认顺序）
- 如果 Engram recall 超时，等 3 秒重试一次再继续
- **✅ Engram 竞品研究（行动计划已制定，Noise Filter+Adaptive Retrieval 已实现 commit cff61ac）**：
  董事长分析了 https://github.com/win4r/memory-lancedb-pro（OpenClaw 增强记忆插件），与我们的 Engram 做了对比。
  **我们的优势**：实体关系图谱、多命名空间、AI蒸馏引擎（consolidator）、置信度衰减、独立部署不绑定 OpenClaw
  **对方的优势（要借鉴）**：
  1. Noise Filter — store 入口自动过滤垃圾（agent拒绝/打招呼/meta问题），防止记忆堆积垃圾
  2. Adaptive Retrieval — 判断 query 是否需要检索（greeting/emoji/简单确认跳过），省 API 调用
  3. Cross-Encoder Rerank — 用 SiliconFlow/Jina reranker 做二次排序，提升检索精度
  4. RRF 混合评分 — Vector + BM25 融合打分（我们有两路但没融合）
  5. 多维评分管线 — Recency Boost(14天半衰期) + Length Norm + Time Decay + Hard Min Score
  6. MMR Diversity — cosine > 0.85 的近似重复结果降权
  **CEO 的任务**：
  - 读完上面的分析后，结合 Engram 代码（/Volumes/Data/project/gitlab_data/lchuangnet/engram/），给出行动计划
  - 优先做 Noise Filter 和 Adaptive Retrieval（工作量小，ROI 高）
  - 战略定位：保持智能化差异（蒸馏引擎是护城河），不做纯检索工具
  - 下一轮 store 你的行动计划到 Engram
- **✅ 获客文章重写（已完成 commit 7c24d2c）**：docs/blog/ 下 4 篇中文 + 4 篇英文文章修改完成
  ✅ 1. 默认账号：统一为 demo@vigilops.io/demo123
  ✅ 2. 页面数量：统一为 24 个页面  
  ✅ 3. Agent 安装脚本：删除不存在的 install.sh 引用，改为实际配置步骤
  ✅ 4. Datadog 价格：web_search 确认 $15/主机/月 准确
  ✅ 5. 时间描述：统一为 10 分钟部署
  ✅ 6. IBM 报告：未发现虚构引用（实际是行业观察）
  ✅ 7. 对比表诚实：已标注 K8s/APM/社区规模不足
  ✅ 8. "凌晨 3 点"梗：修改为不同表述避免重复  
  ✅ 9. 英文版同步：已同步更新

## 🟢 P2 锦上添花

| # | 任务 | 状态 |
|---|------|------|
| 1 | 日志后端切换（ClickHouse/Loki） | ✅ commit 44821a9 |
| 2 | 移动端适配 | ✅ commit a60bebe |
| 3 | Prometheus 兼容 | ✅ commit b036ed2 |
| 4 | OAuth/LDAP | ✅ commit ddef752 |
| 5 | 国际化 i18n | ✅ commit 87ccc6e |

## ECS 访问策略（董事长决定 2026-02-25）
- **安全策略**: 所有 ECS 只允许从当前环境（Mac 本机/内网）访问，不对外开放 SSH
- ✅ 前端 :3001 → HTTP 200（公网可访问）
- ❌ SSH :22 → 仅限白名单 IP
- **部署方式**: 本地打包 → tar 上传（在允许的网络环境下操作）

## Cycle 9 收尾（P0/P1 完成后）

### 已完成
- ✅ 定价调研报告 + Onboarding SOP + CI/CD 工作流
- ✅ Agent 一键安装脚本（含离线模式）
- ✅ 客户快速部署文档 + Landing Page
- ✅ 获客文章 9 篇
- ✅ Docker Compose 端口变量化 + quickstart 模板
- ✅ Demo 账号 + 自定义 favicon + CHANGELOG.md
- ✅ 代码已 push GitLab + GitHub

### 待做（需董事长操作）
- Docker 镜像推送到 GHCR（需 GitHub PAT）
- GitHub repo 添加 topic 标签（需 PAT 或手动）
- 获客文章正式发布（董事长审核中）
- ECS SSH 白名单（加当前 IP）

## 🧠 Engram 记忆系统升级（最高优先级）

> 董事长指示：优先处理 Engram 改进，VigilOps P0 剩余任务之后做。
> Engram 路径：`/Volumes/Data/project/gitlab_data/lchuangnet/engram/`
> ROADMAP：`/Volumes/Data/project/gitlab_data/lchuangnet/engram/ROADMAP.md`
> Docker: postgres:5434, redis:6381, api:8002

### Engram P0 任务（按顺序执行）

| # | 任务 | 代码量 | 状态 |
|---|------|--------|------|
| E1 | 记忆清洗 + 置信度衰减（confidence 字段 + 指数衰减 + 分层清洗 API） | ~400 行 | ✅ 完成 |
| E2 | pgvector 语义搜索（pgvector/pgvector:pg16 + embedder.py + 混合检索 + backfill） | ~800 行 | ✅ 完成（需配 embedding API） |
| E3 | 智能去重（基于 embedding cosine similarity > 0.95） | ~300 行 | ✅ 完成 commit 419b8e5 |

### ⚠️ 代码审查关键发现（小强 2026-02-25 21:21）
- **91,494 条 fact，平均访问 0 次** — 绝大部分存了就没用过
- consolidator.py **已有** decay_importance() 和 merge_duplicates()，但机制粗糙
- postgres:16-alpine **没有 pgvector 扩展**，E2 需要换镜像为 `pgvector/pgvector:pg16`
- DeepSeek **没有 embedding API**，只有 chat/reasoner

### E1 执行指南（记忆清洗 + 置信度衰减）
1. 先读现有代码：`app/models/memcell.py`, `app/services/consolidator.py`, `app/services/retriever.py`
2. **migration 003_confidence.sql**:
   - `ALTER TABLE memcells ADD COLUMN confidence FLOAT DEFAULT 1.0;`
   - `ALTER TABLE memcells ADD COLUMN last_decayed_at TIMESTAMPTZ;`
   - 初始化: `UPDATE memcells SET confidence = importance / 10.0;`
3. **改造 consolidator.py decay_importance()**:
   - 指数衰减: `confidence = confidence * exp(-decay_rate * days_since_last_access)`
   - 不同类型不同衰减率: fact=0.01/天, episode=0.02/天, lesson=0.005/天
   - 被访问时 boost: `confidence = min(1.0, confidence + 0.15)`
   - confidence < 0.1 的自动标记 is_active=false
4. **新增清洗 API**: `POST /api/v1/memory/cleanup`
   - 批量清洗: access_count=0 + importance<=5 + 创建超过30天 → is_active=false
   - 返回清洗统计
5. **更新 retriever.py 排序公式**: 把 importance/10 替换为 confidence
6. 改完后 `docker compose restart engram-api` 验证
7. 调一次 cleanup API 看清洗效果

### E2 执行指南（pgvector 语义搜索）
1. **docker-compose.yml**: 把 `postgres:16-alpine` 换成 `pgvector/pgvector:pg16`
2. 重建容器: `docker compose down postgres && docker compose up -d postgres`（volume 数据不丢）
3. **migration 004_pgvector.sql**:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ALTER TABLE memcells ADD COLUMN embedding vector(1024);
   CREATE INDEX idx_memcells_embedding ON memcells USING hnsw (embedding vector_cosine_ops);
   ```
4. **Embedding 模型选型（按优先级）**:
   - 方案 A: 硅基流动 SiliconFlow API（国内、便宜、BAAI/bge-m3 1024维）
   - 方案 B: 本地 sentence-transformers（paraphrase-multilingual-MiniLM-L12-v2, 384维）
   - 方案 C: config.py 加 `embedding_provider` 配置，支持多后端切换
   - **推荐方案 C**，先实现接口，默认用 SiliconFlow 或 DeepSeek 兼容 API
5. **config.py 新增**:
   ```python
   embedding_api_base: str = ""  # embedding API 地址，空则禁用语义搜索
   embedding_api_key: str = ""
   embedding_model: str = "BAAI/bge-m3"
   embedding_dim: int = 1024
   ```
6. **新增 app/services/embedder.py**: 生成 embedding 的服务
7. **改造 retriever.py**: keyword_score * 0.4 + semantic_score * 0.4 + confidence * 0.2
8. **批量回填**: 新增 `POST /api/v1/memory/backfill-embeddings`（分批处理，每批100条）

### 约束
- **Python 3.9 兼容**，用 `Optional[X]` 不用 `X | None`
- migration 用 raw SQL 文件放 `migrations/` 目录
- .env 不 commit
- 不改现有 API 接口签名（向后兼容）

---

## MCP Server 接入方案（P0-7）
- **技术方案**: FastMCP (Python) 原生集成，独立模块 `backend/app/mcp/`
- **代码量**: ~150-200 行，1 轮 Coder
- **CEO 评估**: 可行性 9/10，战略价值 10/10
- **核心 Tools（第一版）**:
  1. `get_servers_health` — 服务器健康状态+关键指标
  2. `get_alerts` — 告警列表，支持严重程度过滤
  3. `search_logs` — 日志搜索，支持关键词+时间范围
  4. `analyze_incident` — AI 根因分析（差异化杀手锏）
  5. `get_topology` — 服务拓扑数据
- **P1 扩展**: `trigger_remediation`(自动修复), `get_sla_status`, `generate_report`
- **竞品**: Grafana 有官方 MCP，Zabbix 仅社区版，Prometheus 无。VigilOps 可打"首个原生支持 MCP 的开源运维平台+AI分析"
- **约束**: Python 3.9 兼容，`pip install fastmcp`，不引入重量级依赖

## 决策日志
- **2026-02-25 23:00**: E1+E2 完成。E1: confidence列+指数衰减+分层清洗(aggressive/standard/conservative)+Decimal bug修复+retriever SQL alias修复。E2: Docker镜像换pgvector/pgvector:pg16, pgvector 0.8.1, embedder.py(OpenAI兼容), retriever混合检索(kw*0.4+sem*0.4+conf*0.2), store异步embedding, backfill端点。待配embedding API(.env EMBEDDING_API_BASE/KEY)。推荐SiliconFlow BAAI/bge-m3。
- **2026-02-25 21:25**: Engram 方案技术审查完成。发现：91K fact 访问 0 次、已有粗糙衰减/去重、pgvector 未安装、DeepSeek 无 embedding API。调整优先级为 E1 清洗→E2 pgvector→E3 去重。Embedding 用多后端架构（SiliconFlow/本地/OpenAI 兼容）。
- **2026-02-25 21:18**: 董事长指示优先处理 Engram 记忆系统升级（pgvector 语义搜索 → 置信度衰减 → 去重合并），排在 VigilOps P0 剩余任务之前。
- **2026-02-25 20:50**: 董事长批准 MCP Server 接入方案，排入 P0-7。CEO 评估：可行性 9/10，战略价值 10/10，0.5 天工作量。
- **2026-02-25 16:20**: AI 公司 cron 模型从 opus 切换为 sonnet（省配额、避免 timeout）。CEO 层用 sonnet，遇到复杂架构任务可用 opus 派子 Agent。
- **2026-02-25 15:57**: 董事长确认按 CTO 评估的 P0→P1→P2 清单排期推进，AI 公司 cron 自动执行。
- **2026-02-25 15:55**: P0 第一批完成（JWT/错误处理/备份），commit 3974010。
- **2026-02-25**: Engram 决定不独立开源。GitHub Discussions 开通 + 5 篇种子帖。README 修复。

## Company State
- **Product**: VigilOps (开源, GitHub + ECS 已部署)
- **Revenue**: ¥0
- **Users**: 0
- **Monthly Cost**: ¥388
- **Demo**: http://139.196.210.68:3001 (demo@vigilops.io / demo123)
- **Score**: 7.2/10 (CTO 评估 2026-02-25)
