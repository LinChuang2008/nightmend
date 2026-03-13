# 开源 | 我做了个 AI 监控平台，告警来了它自己修——架构和实现细节

> 上一篇讲了为什么做，这篇讲怎么做的。

---

## 项目背景：几个关键的技术决策

VigilOps 不是从零想出来的，它是从几个工程上的困惑开始的。

**为什么不直接用 Grafana + AlertManager？**

因为 AlertManager 的设计目标是"路由和静默"，不是"分析和修复"。你可以配置"CPU > 90% 发钉钉"，但你没法配置"CPU > 90% 时分析日志、给出根因、执行修复命令"。中间那段逻辑需要自己写。

**为什么不用 Ansible/Runbook 工具？**

那类工具假设你事先知道问题是什么。当问题已知时，自动化很好用。但真实告警中有相当一部分是"我不确定为什么，但某个指标异常了"。AI 的价值正在这里：帮你做那段从"异常"到"可能的原因"的推断。

所以 VigilOps 的核心设计理念是：**监控感知 → AI 推断 → Runbook 执行**，三段式流水线。这个流水线是整个项目的骨架。

---

## 架构概览

项目分三层：

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (React)                   │
│         24 个页面，Ant Design + ECharts              │
└──────────────────────┬──────────────────────────────┘
                       │ REST API / WebSocket
┌──────────────────────▼──────────────────────────────┐
│                  Backend (FastAPI)                   │
│  29 个 Router  │  13 个 Service  │  PostgreSQL/Redis │
│                                                      │
│  ┌─────────────┐  ┌────────────┐  ┌───────────────┐ │
│  │ alert_engine│  │ AI Service │  │ Runbook Engine│ │
│  │ 规则评估循环│  │ 根因分析   │  │ 自动修复执行  │ │
│  └─────────────┘  └────────────┘  └───────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Agent Layer / MCP Server                │
│  指标采集  │  日志聚合  │  MCP 5 个工具              │
└─────────────────────────────────────────────────────┘
```

**为什么选 FastAPI？**

简单：Python 生态对 AI/ML 的支持是最好的，跟 DeepSeek/OpenAI 的 SDK 集成没有阻力。FastAPI 的异步支持足够，性能对于这类监控场景绰绰有余，而且 Pydantic 的类型系统对复杂的告警数据结构很友好。

**为什么选 DeepSeek？**

成本。VigilOps 主要面向中小团队和独立开发者，告警分析会频繁调用 AI，DeepSeek 的单次调用成本是 GPT-4 的十分之一左右。代码里也做了 provider 抽象，换成 OpenAI 只需要改一行配置。

**数据层**：PostgreSQL 存告警历史、Runbook 配置、用户数据；Redis 做告警去重和速率限制缓存。

---

## 核心功能实现

### 1. alert_engine：规则评估循环

alert_engine 是整个系统的心脏。它是一个后台 Service，轮询指标数据，对每条规则进行评估。

核心逻辑大概是这样：

```python
class AlertEngine:
    async def evaluate_rules(self):
        """主评估循环，每 30 秒运行一次"""
        rules = await self.rule_service.get_active_rules()
        
        for rule in rules:
            metric_value = await self.metrics_service.get_latest(
                rule.metric_name, 
                rule.target_host
            )
            
            if metric_value is None:
                continue
                
            # 条件评估：支持 >, <, >=, <=, ==, !=
            triggered = self._evaluate_condition(
                metric_value, rule.operator, rule.threshold
            )
            
            if triggered:
                # 去重：同一规则 5 分钟内不重复触发
                if not await self.is_duplicate(rule.id, window=300):
                    await self.create_alert(rule, metric_value)
                    asyncio.create_task(self.trigger_ai_analysis(rule, metric_value))
```

设计上有几个细节：
- **去重窗口**：用 Redis 的 TTL key 做，避免同一问题在告警期间反复触发，轰炸通知渠道
- **异步非阻塞**：AI 分析是 `asyncio.create_task`，不阻塞主评估循环
- **规则隔离**：每条规则独立评估，一条规则的 AI 调用失败不影响其他规则

### 2. AI 根因分析：Prompt 设计思路

这是整个项目里迭代最多的部分。早期版本的 prompt 太简单，AI 经常给出"请检查服务日志"这种废话建议。

现在的 prompt 结构是这样的：

```python
def build_analysis_prompt(alert, context):
    return f"""你是一个运维专家，正在分析一个生产环境告警。

## 当前告警
- 指标：{alert.metric_name}
- 当前值：{alert.current_value}（阈值：{alert.threshold}）
- 主机：{alert.host}
- 触发时间：{alert.triggered_at}

## 最近 1 小时指标趋势
{context.metric_trend}

## 相关日志（最近 50 条）
{context.recent_logs}

## 历史告警（同指标，最近 7 天）
{context.alert_history}

## 要求
1. 给出 2-3 个可能原因，每个原因注明置信度（高/中/低）
2. 给出立即可执行的处理步骤
3. 如果历史告警中有类似模式，指出来
4. 不要给出"请联系运维团队"这类无效建议

输出格式为 JSON，字段：summary, causes, actions, historical_pattern
"""
```

关键点：
- **给 AI 历史模式**：让它做"这次和上次的对比"
- **强制 JSON 输出**：便于前端结构化展示，避免 AI 输出自由文本导致解析失败
- **禁止废话**：明确说"不要给出无效建议"，这个 prompt 技巧确实有效

### 3. Runbook 自动修复机制

> ⚠️ **安全提示**：自定义 shell 命令会直接执行，无沙箱隔离，生产环境请仔细审查 Runbook 内容。

Runbook 本质上是一个"条件 → 操作"的配置文件。6 个内置 Runbook 覆盖了最常见的场景：

```yaml
# 内置 Runbook 示例：nginx 内存超限自动重载
id: nginx_memory_high
name: "Nginx Memory High - Auto Reload"
trigger:
  metric: nginx_memory_percent
  operator: ">"
  threshold: 85
  
actions:
  - type: shell
    command: "nginx -s reload"
    timeout: 30
    
  - type: notify
    channel: webhook
    message: "Nginx reloaded due to high memory. Memory before: {metric_value}%"
    
  - type: verify
    metric: nginx_memory_percent
    operator: "<"
    threshold: 70
    wait_seconds: 60
    on_fail: escalate  # 执行后指标未改善则升级告警
```

`verify` 步骤是后来加的——执行完修复操作之后，等一分钟看指标有没有回落，没有回落则触发升级告警。否则你重启了服务，以为修好了，其实没改善，这比不重启更危险（你以为处理了）。

执行引擎支持三种模式：
- `auto`：自动执行，适合低风险操作（reload、清日志）
- `confirm`：推送给用户确认后执行，适合生产环境
- `suggest`：只建议，不执行，适合高风险操作或权限受限环境

### 4. MCP Server 实现思路

MCP（Model Context Protocol）是 Anthropic 提出的 AI 工具协议，支持 Claude Desktop 等工具通过标准接口调用外部服务。

VigilOps 实现了 5 个 MCP 工具：

```python
# MCP 工具注册示例
@mcp_server.tool()
async def get_server_status(host: Optional[str] = None) -> dict:
    """获取服务器当前状态，包括 CPU、内存、磁盘使用率"""
    return await metrics_service.get_current_status(host)

@mcp_server.tool()  
async def query_alerts(
    severity: Optional[str] = None,
    hours: int = 24
) -> list:
    """查询告警历史，支持按严重程度和时间范围过滤"""
    return await alert_service.query_recent(severity, hours)

@mcp_server.tool()
async def analyze_alert(alert_id: int) -> dict:
    """对指定告警触发 AI 根因分析并返回结果"""
    return await ai_service.analyze(alert_id)
```

接入 Claude Desktop 后，可以直接用自然语言问："过去 6 小时有哪些严重告警，它们的根因分析结果是什么？" Claude 会自动调用 `query_alerts` 和 `analyze_alert`，把结果整合成自然语言回答。

---

## 部署体验：15 分钟跑起来

```bash
git clone https://github.com/LinChuang2008/vigilops.git
cd vigilops
cp .env.example .env
```

`.env` 里需要填的关键配置：

```bash
# 数据库
POSTGRES_PASSWORD=your_secure_password

# AI 配置（二选一）
AI_PROVIDER=deepseek          # 或 openai
DEEPSEEK_API_KEY=sk-xxx       # DeepSeek API Key
# OPENAI_API_KEY=sk-xxx       # 或者 OpenAI

# 通知渠道（可选）
WEBHOOK_URL=https://...       # 钉钉/飞书 Webhook
```

然后：

```bash
docker compose up -d
```

服务会启动 4 个容器：`backend`（FastAPI:8001）、`frontend`（React:3001）、`postgres`、`redis`。

访问 `http://localhost:3001`，用你配置的管理员账号登录。第一次进去需要手动添加监控目标（填主机 IP 和 Agent 端口），然后配置告警规则，基本就能用了。

Agent 部分当前需要在被监控主机上手动安装，后续计划做一键安装脚本。

---

## 技术债和已知问题（诚实版）

这个项目从 0 到现在功能跑通，但有几个地方我自己都不满意，说出来：

**1. ClickHouse 暂时禁用**

代码里有 ClickHouse 的集成代码，用于大规模日志存储。但 ClickHouse 的 Docker 镜像在 compose 里偶尔会 OOM（需要至少 2G 内存），对小机器不友好，所以默认配置里是禁用的，日志目前走 PostgreSQL。如果你的机器内存够，可以手动开启。

**2. async/sync 混用**

alert_engine 的主循环是 async 的，但部分 Runbook 的 shell 执行是 sync subprocess。目前用 `asyncio.run_in_executor` 包了一层，能跑，但不够优雅。这块计划重构成完全 async。

**3. AI 分析没有缓存**

同一个告警短时间内多次触发时，AI 分析会重复调用 API，浪费 token。计划加 Redis 缓存，相似告警复用分析结果。

**4. Runbook 执行没有沙箱**

自定义 shell 命令目前是直接执行的，没有做权限隔离。生产环境用之前建议仔细审查你配置的 shell 命令，或者只用内置 Runbook。

**5. 前端测试覆盖率低**

后端有基础测试，前端几乎没有。这是历史债，计划在社区稳定后补。

---

## 开源计划和寻求反馈

项目目前是 MIT 协议，代码全部开源。

**现阶段最需要的反馈：**

1. **AI 分析的 Prompt**：你在真实告警场景里，觉得 AI 给的分析有没有用？哪类告警分析效果差？
2. **Runbook 配置语法**：现在的 YAML 结构用起来直觉吗？有没有更好的表达方式？
3. **部署体验**：在你的环境里跑起来有没有问题？什么地方卡住了？
4. **Agent 端**：你更希望 Agent 是 Python 的还是 Go 的（轻量部署）？

GitHub Issue 和 PR 都欢迎。如果觉得方向有意思，Star 一下让我知道这东西有人在用，是对独立开发者最直接的鼓励。

- **GitHub**：https://github.com/LinChuang2008/vigilops
- **在线 Demo**：http://139.196.210.68:3001（demo@vigilops.io / demo123）

---

代码不完美，想法是实用的。欢迎来聊。

---

#开源 #运维 #FastAPI #React #AI #监控 #DevOps
