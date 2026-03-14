# MCP 协议遇上运维：当 AI Agent 学会了查告警和修故障

> 作者：VigilOps 团队 | 2026-02

---

## MCP 是什么，为什么运维人应该关注

如果你关注 AI 领域的动态，2025 年下半年开始频繁出现一个词：**MCP（Model Context Protocol）**。简单说，MCP 是 Anthropic 提出的一个开放协议，目的是让 AI 模型（LLM）能够以标准化的方式调用外部工具。

你可以把 MCP 理解为"AI Agent 的 USB 接口"。以前每个 AI 应用要集成一个工具，都需要写一套自定义的代码。MCP 定义了一个通用协议：工具提供方实现 MCP Server（暴露自己的能力），AI Agent 作为 MCP Client（调用这些能力）。协议标准化了工具描述、参数传递、结果返回的格式。

**这和运维有什么关系？**

想象这个场景：你在和 AI 助手对话，说"帮我看看 web-03 服务器最近的告警"。AI 不再需要你复制粘贴告警信息给它——它直接通过 MCP 调用你的监控系统 API，拿到告警数据，分析后告诉你："web-03 在过去 6 小时有 3 条告警，其中 2 条是磁盘相关的，根因是 /var/log 目录增长过快。要不要我执行 log_rotation Runbook？"

这不是科幻场景。这是 MCP 协议让 AI Agent 和运维系统连接后的真实能力。

## VigilOps 的 MCP Server

VigilOps 内置了一个 MCP Server，提供 5 个工具：

| 工具 | 功能 | 使用场景 |
|------|------|---------|
| `query_alerts` | 查询告警列表和详情 | "最近有什么告警？" |
| `query_metrics` | 查询主机和服务的指标数据 | "web-03 的 CPU 趋势是什么？" |
| `run_diagnosis` | 对指定主机或服务运行 AI 诊断 | "帮我诊断一下 db-01 为什么慢" |
| `execute_runbook` | 执行指定的 Runbook | "执行磁盘清理" |
| `query_topology` | 查询服务拓扑和依赖关系 | "这个服务依赖哪些上游？" |

### 这意味着什么

传统的运维工作流是：**人打开监控面板 → 人看告警 → 人判断原因 → 人执行修复**。

有了 MCP，AI Agent 可以参与这个链路的每一步。它不是在旁边给你建议——它直接动手查数据、做分析、执行操作。

**但要注意：** 自动执行操作（比如重启服务）需要审批。VigilOps 的 Runbook 引擎有安全检查机制，不是 AI 说执行就执行。你可以配置哪些操作需要人工审批，哪些可以全自动。

## 一个具体的使用场景

假设你用 Claude Desktop（或任何支持 MCP 的 AI 客户端）连接了 VigilOps 的 MCP Server。

**你：** "检查一下过去 1 小时的所有告警。"

**AI Agent 的执行过程：**
1. 调用 `query_alerts`，获取过去 1 小时的告警列表
2. 返回结果：3 条告警——web-03 磁盘 92%、api-server 响应延迟高、redis 连接数告警

**你：** "分析一下 api-server 的问题。"

**AI Agent 的执行过程：**
1. 调用 `query_metrics`，获取 api-server 的 CPU、内存、响应时间趋势
2. 调用 `query_topology`，查看 api-server 的上下游依赖
3. 发现 api-server 依赖的 redis 也在告警
4. 调用 `run_diagnosis`，综合分析
5. 返回：「api-server 延迟高的原因可能是 Redis 连接数接近上限，导致请求排队。建议执行 `connection_reset` Runbook 重置 Redis 连接池。」

**你：** "执行吧。"

**AI Agent 的执行过程：**
1. 调用 `execute_runbook`，参数：runbook=connection_reset, target=redis-01
2. Runbook 引擎执行安全检查
3. 执行连接池重置
4. 返回执行结果

这整个交互过程，AI Agent 充当了一个"初级 SRE"的角色：收集信息、关联分析、提出建议、执行操作。你作为运维负责人只需要做决策——"执行吧"或"先别动，让我再看看"。

## MCP 对运维的长期影响

### 短期：运维效率工具

目前 MCP 最直接的价值是作为运维效率工具。你不再需要在多个面板之间切换——通过一个 AI 对话界面就能查询告警、分析指标、执行操作。对于日常巡检、告警处理这些高频但不复杂的工作，效率提升是明显的。

### 中期：值班助手

随着 AI Agent 的能力提升和信任度建立，MCP 可以让 AI 承担一部分值班工作。比如：
- 夜间告警先由 AI Agent 初步分析和处理
- 常见问题（磁盘满、服务重启）直接自动修复
- 只有 AI 判断无法处理的问题才叫醒值班人员

这不是取代值班人员，而是给值班人员一个"AI 助手"，过滤掉大部分噪音。

### 长期：自主运维

更远的未来，当 AI Agent 的可靠性足够高、Runbook 覆盖足够全的时候，理论上可以实现更大程度的自主运维。但坦率说，这还很远。行业调研显示，大多数团队尚未实现真正的自主修复。

## 动手试试

### 在 VigilOps 中启用 MCP Server

VigilOps 的 MCP Server 随后端一起部署，默认可用。你可以在任何支持 MCP 协议的客户端中配置：

```json
{
  "mcpServers": {
    "vigilops": {
      "url": "http://your-vigilops-server:8001/mcp",
      "description": "VigilOps monitoring and auto-remediation"
    }
  }
}
```

### 在 Demo 环境中体验

访问 [https://demo.lchuangnet.com](https://demo.lchuangnet.com)（`demo@vigilops.io` / `demo123`），在界面上可以看到 MCP 相关的配置和工具列表。

如果你有 Claude Desktop 或其他 MCP 客户端，可以尝试连接 Demo 的 MCP Server（只读模式，不能执行 Runbook）。

### 部署自己的环境

```bash
git clone https://github.com/LinChuang2008/vigilops.git
cd vigilops
cp .env.example .env  # 填入 DeepSeek API Key
docker compose up -d
```

部署后，MCP Server 在 `http://localhost:8001/mcp` 可用。

## MCP 生态现状

截至 2026 年初，MCP 协议正在快速发展：

- **Anthropic** 发起，Claude Desktop 原生支持
- **多个 AI 平台**开始支持 MCP 客户端
- **开源社区**涌现了大量 MCP Server（数据库、文件系统、API 集成等）
- **运维领域**的 MCP Server 还很少——这也是 VigilOps 做 MCP 集成的原因之一

对运维工具来说，支持 MCP 意味着：你的监控数据和操作能力可以被任何 AI Agent 使用。这比自己做一个 AI 功能更有想象空间——因为 AI Agent 的能力是在不断进化的，而你的工具只需要提供标准化的接口。

## 写在最后

MCP 协议还很年轻，VigilOps 的 MCP 实现也还在早期。但方向很清晰：**运维工具需要从"给人看的面板"进化为"给 AI 用的接口"**。

这不意味着运维人员会被取代。相反，当 AI Agent 可以处理 80% 的日常琐事时，运维人员可以把精力放在架构优化、容量规划、故障预防这些更有价值的工作上。

如果你对 MCP + 运维的方向感兴趣，欢迎在 [GitHub Discussions](https://github.com/LinChuang2008/vigilops/discussions) 和我们交流。我们特别想知道：你希望 AI Agent 能帮你做哪些运维工作？

---

*VigilOps 是一个 Apache 2.0 开源项目。GitHub：[LinChuang2008/vigilops](https://github.com/LinChuang2008/vigilops)*
